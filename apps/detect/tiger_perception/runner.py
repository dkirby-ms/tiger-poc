"""Run one manifest-selected local workload: python -m tiger_perception.runner."""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

from .adapters import CameraCapture, QrProvider, YoloProvider
from .config import Workload, load_workload, resolve_source
from .contracts import Frame, RawInference
from .mapping import map_identification, map_presence
from .presence import PresenceRule
from .sinks import LocalJsonlSink, SinkError

logger = logging.getLogger(__name__)


@contextmanager
def output_lock(path: Path):
    """Prevent two local processes from owning the same publication files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("An output is already owned by another workload") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path: Path, content: bytes) -> None:
    """Replace one small status artifact without exposing partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


class WorkloadRuntime:
    """Own rule, publication state, counters, and preview for one workload."""

    def __init__(self, workload: Workload) -> None:
        self.workload = workload
        self.rule = PresenceRule(source_id=workload.spec.source.id,
                                 subject_id=workload.spec.source.subjectId,
                                 policy=workload.policy(),
                                 observation_type=workload.spec.perception.observationType)
        self.sink = LocalJsonlSink(path=workload.spec.destination.path)
        self.latest_event = None
        self.reason = "Starting"
        self.frames = 0
        self.failed_inferences = 0
        self.unusable_frames = 0
        self.dropped_frames = 0
        self.inference_milliseconds = 0.0
        self.frame_age_seconds = 0.0
        self.read_milliseconds = 0.0
        self.started = monotonic()
        self._epoch = None
        self._last_status = 0.0
        self._last_availability = None
        self._detections = []
        self._qr_codes = []
        self._case_rules: dict[str, PresenceRule] = {}

    def accept_frame(self, frame: Frame) -> bool:
        """Invalidate confirmation across reconnects and unusable frames."""
        epoch = frame.metadata.get("epoch")
        if epoch != self._epoch:
            self.rule.reconnect()
            self._case_rules.clear()
            self._epoch = epoch
        self.dropped_frames = frame.metadata.get("droppedFrames", 0)
        self.read_milliseconds = frame.metadata.get("readMilliseconds", 0.0)
        if not frame.metadata.get("usable", False):
            self.rule.unavailable()
            self._invalidate_cases()
            self.reason = "Camera unavailable" if frame.payload is None else "Unusable image"
            self.unusable_frames += 1
            return False
        now = datetime.now(UTC)
        age = (now - datetime.fromisoformat(frame.captured_at)).total_seconds()
        if not 0 <= age < self.rule.policy.stale_seconds:
            self.rule.unavailable()
            self._invalidate_cases()
            self.reason = "Stale frame"
            return False
        return True

    def process(self, inference: RawInference, *, now: datetime) -> None:
        """Apply normalized evidence and publish each confirmed transition once."""
        self.frames += 1
        self.inference_milliseconds = inference.metadata.get("inferenceMilliseconds", 0.0)
        self.frame_age_seconds = (now - datetime.fromisoformat(inference.captured_at)).total_seconds()
        self.failed_inferences += int(not inference.succeeded)
        self._detections = [asdict(detection) for detection in inference.detections]
        self._qr_codes = []
        observation = self.rule.observe(inference, now=now)
        self.reason = "" if self.rule.availability != "unavailable" else "Inference failed or stale"
        if self.workload.spec.perception.provider == "qr":
            self._process_cases(inference, now=now)
        elif observation is not None:
            self._publish_event(map_presence(observation, self.workload))

    def _invalidate_cases(self) -> None:
        self._qr_codes = []
        for rule in self._case_rules.values():
            rule.unavailable()

    def _process_cases(self, inference: RawInference, *, now: datetime) -> None:
        if self.rule.availability == "unavailable":
            self._invalidate_cases()
            return
        matching = [item for item in inference.detections
                    if item.case_id is not None and self.rule.policy.matches(item)]
        self._qr_codes = sorted({item.case_id for item in matching})
        for case_id in self._qr_codes:
            if case_id not in self._case_rules:
                self._case_rules[case_id] = PresenceRule(
                    source_id=self.rule.source_id, subject_id=case_id,
                    policy=self.rule.policy, observation_type="BoxIdentified")
        for case_id, rule in list(self._case_rules.items()):
            evidence = replace(inference, detections=[item for item in matching if item.case_id == case_id])
            observation = rule.observe(evidence, now=now)
            if observation is not None:
                if observation.value:
                    self._publish_event(map_identification(observation, self.workload))
                else:
                    del self._case_rules[case_id]

    def _publish_event(self, event: dict[str, object]) -> None:
        try:
            self.sink.publish(event)
        except SinkError:
            self.rule.unavailable()
            self._invalidate_cases()
            self.reason = "Event publication failed; workload stopped"
            self.write_status(force=True)
            raise
        self.latest_event = event
        logger.info("source=%s subject=%s value=%s event=%s",
                    event["sourceId"], event["subjectId"], event["value"], event["eventId"])

    def write_status(self, *, force: bool = False) -> None:
        """Publish redacted live status with independent freshness timestamps."""
        now = datetime.now(UTC)
        self.rule.expire(now)
        for rule in self._case_rules.values():
            rule.expire(now)
        if self.rule.availability == "unavailable" and not self.reason:
            self.reason = "Waiting for fresh evidence"
        if not force and monotonic() - self._last_status < 0.2:
            return
        self._last_status = monotonic()
        if self.rule.availability != self._last_availability:
            logger.info("source=%s availability=%s", self.rule.source_id, self.rule.availability)
            self._last_availability = self.rule.availability
        status = {
            "name": self.workload.metadata.name,
            "sourceId": self.rule.source_id, "subjectId": self.rule.subject_id,
            "plantName": self.workload.metadata.plantName, "plantId": self.workload.metadata.plantId,
            "observationType": self.rule.observation_type,
            "labels": self.workload.spec.perception.labels,
            "region": self.workload.spec.region.bounds,
            "staleSeconds": self.rule.policy.stale_seconds,
            "availability": self.rule.availability, "lastConfirmed": self.rule.confirmed,
            "reason": self.reason, "writtenAt": now.isoformat(),
            "capturedAt": self.rule.last_captured_at.isoformat() if self.rule.last_captured_at else None,
            "latestEvent": self.latest_event, "detections": self._detections,
            "qrCodes": self._qr_codes,
            "metrics": {
                "processedFrames": self.frames, "failedInferences": self.failed_inferences,
                "unusableFrames": self.unusable_frames, "droppedFrames": self.dropped_frames,
                "inferenceMilliseconds": self.inference_milliseconds,
                "frameAgeSeconds": self.frame_age_seconds, "readMilliseconds": self.read_milliseconds,
                "processedFps": self.frames / max(0.001, monotonic() - self.started),
                "publishedEvents": self.sink.published_count, "failedWrites": self.sink.failed_count,
                "duplicateEvents": self.sink.duplicate_count,
            },
        }
        atomic_write(Path(self.workload.spec.destination.statusPath), json.dumps(status).encode())

    def write_preview(self, frame: Frame, inference: RawInference) -> None:
        """Draw configured region and qualifying detections onto a bounded preview."""
        import cv2

        height, width = frame.payload.shape[:2]
        image = cv2.resize(frame.payload, (960, max(1, int(height * 960 / width))))
        height, width = image.shape[:2]
        for bounds, color in [(self.rule.policy.region, (60, 190, 240))] + [
            (tuple(item.bounding_box[key] for key in ("xMin", "yMin", "xMax", "yMax")), (130, 215, 60))
            for item in inference.detections if self.rule.policy.matches(item)
        ]:
            left, top, right, bottom = bounds
            cv2.rectangle(image, (int(left * width), int(top * height)),
                          (int(right * width), int(bottom * height)), color, 3)
        for item in inference.detections:
            if (self.workload.spec.perception.provider == "qr"
                    and item.case_id and self.rule.policy.matches(item)):
                origin = (min(width - 110, max(0, int(item.bounding_box["xMin"] * width))),
                          max(20, int(item.bounding_box["yMin"] * height) - 8))
                cv2.putText(image, item.case_id, origin, cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 80, 220), 2, cv2.LINE_AA)
        encoded, payload = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if encoded:
            atomic_write(Path(self.workload.spec.destination.statusPath).with_suffix(".jpg"), payload.tobytes())


def create_parser() -> argparse.ArgumentParser:
    """Create the manifest-driven CLI, independent of camera/model imports."""
    parser = argparse.ArgumentParser(description="Run one local perception workload")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--check", action="store_true", help="Validate settings and model labels without camera access")
    return parser


def run(args: argparse.Namespace) -> int:
    """Run real inference until interrupted or the finite test budget completes."""
    if args.max_frames < 0:
        raise ValueError("max-frames must be nonnegative")
    if args.env_file:
        if not args.env_file.is_file():
            raise ValueError("Private environment file is missing")
        load_dotenv(args.env_file, override=False)
    workload = load_workload(args.manifest)
    uri = resolve_source(workload.spec.source)
    provider = (QrProvider() if workload.spec.perception.provider == "qr"
                else YoloProvider(workload.spec.perception, workload.spec.presence.confidence))
    logger.info("source=%s provider=%s model=%s", workload.spec.source.id, provider.provider, provider.identity)
    if args.check:
        return 0
    with ExitStack() as stack:
        for path in (workload.spec.destination.path, workload.spec.destination.statusPath):
            stack.enter_context(output_lock(Path(path)))
        runtime = WorkloadRuntime(workload)
        capture = CameraCapture(workload.spec.source, uri, workload.spec.capture,
                                workload.spec.perception.sampleEveryFrames)
        capture.start()
        try:
            while args.max_frames == 0 or runtime.frames < args.max_frames:
                runtime.write_status()
                frame = capture.read()
                if frame is None:
                    continue
                if not runtime.accept_frame(frame):
                    runtime.write_status(force=True)
                    continue
                inference = provider.infer(frame)
                runtime.process(inference, now=datetime.now(UTC))
                runtime.write_preview(frame, inference)
                runtime.write_status(force=True)
        finally:
            capture.close()
            runtime.rule.unavailable()
            if runtime.reason != "Event publication failed; workload stopped":
                runtime.reason = "Workload stopped"
            runtime.write_status(force=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Map errors to stable exit codes without exposing endpoint-bearing errors."""
    args = create_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except ValueError as error:
        logger.error("Configuration rejected: %s", error)
        return 2
    except (RuntimeError, OSError, ImportError, TypeError, AttributeError):
        logger.error("Workload failed. Check model compatibility, private camera configuration, and output access.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
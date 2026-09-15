"""Read-only observation client, person-in-zone rules, and JSONL decision sink."""

from __future__ import annotations

import json
import math
import os
import re
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_JSON_BYTES = 256 * 1024 + 4096
MAX_JPEG_BYTES = 4 * 1024 * 1024


def finite(value) -> float:
    """Reject booleans, nonnumeric and nonfinite contract values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected finite number")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Expected finite number")
    return float(value)


@dataclass(frozen=True)
class Config:
    """Validated configuration for one camera and normalized rectangle."""

    camera: str = "camera-01"
    zone: tuple[float, float, float, float] = (0, 0, 1, 1)
    confidence: float = 0.5
    enter_frames: int = 2
    exit_frames: int = 3
    dwell_seconds: float = 0
    stale_seconds: float = 5
    poll_seconds: float = 0.5
    vision_url: str = "http://vision:8080"

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.camera):
            raise ValueError("Invalid CAMERA_ID")
        if len(self.zone) != 4:
            raise ValueError("ZONE must contain four coordinates")
        left, top, right, bottom = (finite(v) for v in self.zone)
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError("ZONE must be an ordered normalized rectangle")
        if not 0 <= finite(self.confidence) <= 1:
            raise ValueError("Invalid confidence")
        for count in (self.enter_frames, self.exit_frames):
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
                raise ValueError("Frame counts must be integers in [1,1000]")
        if not 0 <= finite(self.dwell_seconds) <= 300:
            raise ValueError("Invalid dwell")
        if not 0.1 <= finite(self.stale_seconds) <= 300:
            raise ValueError("Invalid stale threshold")
        if not 0.05 <= finite(self.poll_seconds) <= self.stale_seconds:
            raise ValueError("Invalid poll interval")
        parsed = urlsplit(self.vision_url)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or parsed.port == 0):
            raise ValueError("VISION_URL must be a plain private HTTP origin")

    @classmethod
    def from_env(cls, env) -> Config:
        """Load explicit typed environment values; fail closed on invalid settings."""
        return cls(
            camera=env.get("CAMERA_ID", "camera-01"),
            zone=tuple(float(v) for v in env.get("ZONE", "0,0,1,1").split(",")),
            confidence=float(env.get("PERSON_CONFIDENCE", "0.5")),
            enter_frames=int(env.get("ENTER_FRAMES", "2")),
            exit_frames=int(env.get("EXIT_FRAMES", "3")),
            dwell_seconds=float(env.get("DWELL_SECONDS", "0")),
            stale_seconds=float(env.get("STALE_SECONDS", "5")),
            poll_seconds=float(env.get("POLL_SECONDS", "0.5")),
            vision_url=env.get("VISION_URL", "http://vision:8080"),
        )


class NoRedirect(HTTPRedirectHandler):
    """Keep all evidence requests on the configured origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class VisionClient:
    """Bounded, timeout-limited HTTP client with no proxy or redirect forwarding."""

    def __init__(self, origin: str, timeout: float = 2) -> None:
        self.origin = origin.rstrip("/")
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _get(self, path: str, limit: int, content_type: str) -> bytes:
        started = time.monotonic()
        with self.opener.open(Request(self.origin + path), timeout=self.timeout) as response:
            if response.headers.get_content_type() != content_type:
                raise ValueError("Unexpected response type")
            length = response.headers.get("Content-Length")
            expected = None if length is None else int(length)
            if expected is not None and not 0 <= expected <= limit:
                raise ValueError("Response exceeds limit")
            data = bytearray()
            while True:
                if time.monotonic() - started >= self.timeout:
                    raise TimeoutError("Response deadline exceeded")
                chunk = response.read1(min(65536, limit + 1 - len(data)))
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Response exceeds limit")
                if not chunk:
                    if expected is not None and len(data) != expected:
                        raise ValueError("Incomplete response")
                    return bytes(data)

    def latest(self) -> dict:
        """Add transport duration to server capture age conservatively."""
        started = time.monotonic()
        result = json.loads(
            self._get("/v1/observations/latest", MAX_JSON_BYTES, "application/json")
        )
        if not isinstance(result, dict):
            raise ValueError("Invalid envelope")
        if result.get("ageSeconds") is not None:
            result["ageSeconds"] = finite(result["ageSeconds"]) + time.monotonic() - started
        return result

    def matching_image(self, observation: dict) -> tuple[int, bytes | None]:
        """Fetch only the named frame; return 404/410 without substituting latest."""
        frame_id = observation["frameId"]
        if not isinstance(frame_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}/[a-f0-9]{32}/[1-9][0-9]{0,15}", frame_id
        ):
            raise ValueError("Invalid frame ID")
        try:
            return 200, self._get(f"/v1/frames/{frame_id}", MAX_JPEG_BYTES, "image/jpeg")
        except HTTPError as error:
            if error.code in {404, 410}:
                return error.code, None
            raise


def validate_observation(envelope: dict, camera: str) -> tuple[dict, float]:
    """Validate complete detection evidence before treating an empty list as absence."""
    if envelope.get("schemaVersion") != "1.0" or envelope.get("available") is not True:
        raise ValueError("Unavailable observation service")
    obs = envelope.get("observation")
    if not isinstance(obs, dict) or obs.get("schemaVersion") != "1.0":
        raise ValueError("Unsupported observation")
    age = finite(envelope.get("ageSeconds"))
    if age < 0 or obs.get("cameraId") != camera:
        raise ValueError("Invalid observation age or camera")
    session, sequence = obs.get("sessionId"), obs.get("frameNumber")
    if not isinstance(session, str) or not re.fullmatch(r"[a-f0-9]{32}", session):
        raise ValueError("Invalid session")
    if (isinstance(sequence, bool) or not isinstance(sequence, int)
            or not 1 <= sequence < 10**16
            or obs.get("frameId") != f"{camera}/{session}/{sequence}"):
        raise ValueError("Invalid sequence correlation")
    for field in ("capturedAt", "processedAt", "timestamp"):
        stamp = datetime.fromisoformat(obs[field])
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Expected UTC timestamp")
    width, height = finite(obs["frame"]["width"]), finite(obs["frame"]["height"])
    if not 0 < width <= 32768 or not 0 < height <= 32768:
        raise ValueError("Invalid frame dimensions")
    detections = obs.get("detections")
    if not isinstance(detections, list) or len(detections) > 1000:
        raise ValueError("Invalid detections")
    for detection in detections:
        if not isinstance(detection["label"], str) or len(detection["label"]) > 128:
            raise ValueError("Invalid label")
        if not 0 <= finite(detection["confidence"]) <= 1:
            raise ValueError("Invalid confidence")
        box = detection["boundingBox"]
        x1, y1, x2, y2 = (finite(box[k]) for k in ("xMin", "yMin", "xMax", "yMax"))
        if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
            raise ValueError("Invalid bounding box")
    return obs, age


class ZoneRules:
    """Debounce distinct observations, preserving unknown across stale/failed input."""

    def __init__(self, config: Config, clock=time.monotonic) -> None:
        self.config, self.clock = config, clock
        self.state: str | None = None
        self.session: str | None = None
        self.retired: deque[str] = deque(maxlen=16)
        self.sequence = 0
        self.deadline = 0.0
        self.candidate: bool | None = None
        self.count = 0
        self.since = 0.0

    def _transition(self, state: str, reason: str, obs: dict | None = None) -> list[dict]:
        if self.state == state:
            return []
        self.state = state
        evidence = None if obs is None else {
            "frameId": obs["frameId"], "capturedAt": obs["capturedAt"],
            "processedAt": obs["processedAt"],
        }
        return [{
            "schemaVersion": "1.0", "eventType": "ZoneStateChanged",
            "subjectId": f"{self.config.camera}:zone", "state": state, "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(), "source": "tiger-brain/rules-v1",
            "evidence": evidence,
        }]

    def unavailable(self, reason: str = "unavailable") -> list[dict]:
        """Reset confirmation, but keep deduplication across transport failures."""
        self.candidate, self.count = None, 0
        return self._transition("unknown", reason)

    def consume(self, envelope: dict) -> list[dict]:
        """Evaluate at most one fresh distinct frame; duplicates never extend deadlines."""
        try:
            obs, age = validate_observation(envelope, self.config.camera)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return self.unavailable("invalid_or_unavailable")
        now = self.clock()
        events = []
        if self.session is not None and now >= self.deadline:
            events += self.unavailable("stale")
        if age >= self.config.stale_seconds:
            return events + self.unavailable("stale")
        session, sequence = obs["sessionId"], obs["frameNumber"]
        if session in self.retired:
            return events + self.unavailable("retired_session")
        if session != self.session:
            if self.session is not None:
                self.retired.append(self.session)
                events += self.unavailable("session_changed")
            self.session, self.sequence = session, 0
            self.candidate, self.count = None, 0
        if sequence <= self.sequence:
            if sequence < self.sequence:
                return events + self.unavailable("sequence_regressed")
            self.deadline = min(self.deadline, now + self.config.stale_seconds - age)
            return events
        self.sequence = sequence
        self.deadline = now + self.config.stale_seconds - age
        left, top, right, bottom = self.config.zone
        width, height = obs["frame"]["width"], obs["frame"]["height"]
        present = False
        for detection in obs["detections"]:
            if detection["label"] != "person" or detection["confidence"] < self.config.confidence:
                continue
            box = detection["boundingBox"]
            x = (box["xMin"] + box["xMax"]) / (2 * width)
            y = (box["yMin"] + box["yMax"]) / (2 * height)
            present |= left <= x <= right and top <= y <= bottom
        evidence_time = now - age
        if self.candidate != present:
            self.candidate, self.count, self.since = present, 1, evidence_time
        else:
            self.count = min(1000, self.count + 1)
        threshold = self.config.enter_frames if present else self.config.exit_frames
        if self.count >= threshold and evidence_time - self.since >= self.config.dwell_seconds:
            events += self._transition(
                "occupied" if present else "clear",
                "confirmed_presence" if present else "confirmed_absence", obs,
            )
        return events


def poll_once(client: VisionClient, rules: ZoneRules) -> list[dict]:
    """Transport/schema failures mean unknown, not an empty detection record."""
    try:
        return rules.consume(client.latest())
    except (OSError, URLError, HTTPException, ValueError, TypeError):
        return rules.unavailable("transport_failure")


def main() -> int:
    """Run advisory rules until signalled; stdout contains only decision JSONL."""
    try:
        config = Config.from_env(os.environ)
    except (ValueError, TypeError):
        print("Invalid brain configuration; check documented settings.", file=sys.stderr)
        return 2
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    client, rules = VisionClient(config.vision_url), ZoneRules(config)
    try:
        for event in rules.unavailable("starting"):
            print(json.dumps(event, separators=(",", ":")), flush=True)
        while not stopped.is_set():
            for event in poll_once(client, rules):
                print(json.dumps(event, separators=(",", ":")), flush=True)
            stopped.wait(config.poll_seconds)
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

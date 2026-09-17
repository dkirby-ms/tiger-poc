"""Camera-free checks of image usability and normalized provider results."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from tiger_perception.adapters import (
    QrProvider,
    YoloProvider,
    decode_qr_codes,
    frame_quality,
    normalize_detections,
)
from tiger_perception.config import Capture, Perception
from tiger_perception.contracts import Frame


class Array:
    """Small result-array test double for provider normalization."""

    def __init__(self, values):
        self.values = values

    def cpu(self):
        return self

    def int(self):
        return self

    def tolist(self):
        return self.values


def test_given_detection_result_when_normalized_then_use_relative_geometry():
    result = SimpleNamespace(names={0: "chair"}, boxes=SimpleNamespace(
        xyxyn=Array([[0.1, 0.2, 0.8, 0.9]]), conf=Array([0.85]), cls=Array([0])))

    detections = normalize_detections(result)

    assert detections[0].bounding_box == {"xMin": 0.1, "yMin": 0.2, "xMax": 0.8, "yMax": 0.9}
    assert detections[0].label == "chair"


def test_given_successful_empty_result_when_normalized_then_empty_list():
    result = SimpleNamespace(boxes=SimpleNamespace(xyxyn=Array([]), conf=Array([]), cls=Array([])))

    assert normalize_detections(result) == []


def test_given_generated_case_label_when_qr_codes_decoded_then_return_case_id():
    payload = cv2.imread(str(Path(__file__).parents[3] / "docs/inventory-labels/case-001.png"))

    assert decode_qr_codes(payload) == ["CASE-001"]


@pytest.mark.parametrize("case_id", ["CASE-001", "CASE-002", "CASE-003", "https://example.com"])
def test_given_qr_label_when_primary_provider_runs_then_decode_only_case_ids(case_id):
    encoded = cv2.QRCodeEncoder_create().encode(case_id)
    image = cv2.resize(np.pad(encoded, 4, constant_values=255), None, fx=8, fy=8,
                       interpolation=cv2.INTER_NEAREST)
    frame = Frame("cell-c-camera-01", 1, "2026-09-17T12:00:00+00:00", image)

    inference = QrProvider().infer(frame)

    assert inference.succeeded
    assert inference.qr_codes == ([case_id] if case_id.startswith("CASE-") else [])
    for detection in inference.detections:
        assert detection.case_id == case_id
        assert detection.label == "qr"
        assert all(0 <= value <= 1 for value in detection.bounding_box.values())


@pytest.mark.parametrize("payload,succeeded", [(None, False), (np.full((200, 200), 255, dtype=np.uint8), True)])
def test_given_missing_or_blank_frame_when_qr_inferred_then_distinguish_failure(payload, succeeded):
    frame = Frame("cell-c-camera-01", 1, "2026-09-17T12:00:00+00:00", payload)

    inference = QrProvider().infer(frame)

    assert inference.succeeded is succeeded
    assert inference.qr_codes == []


def test_given_three_labels_in_one_frame_when_qr_inferred_then_decode_all():
    tiles = []
    for case_id in ("CASE-001", "CASE-002", "CASE-003"):
        encoded = cv2.QRCodeEncoder_create().encode(case_id)
        tiles.append(cv2.resize(np.pad(encoded, 8, constant_values=255), (300, 300),
                                interpolation=cv2.INTER_NEAREST))
    image = np.concatenate(tiles, axis=1)

    inference = QrProvider().infer(Frame("cell-c-camera-01", 1, "2026-09-17T12:00:00+00:00", image))

    assert sorted(inference.qr_codes) == ["CASE-001", "CASE-002", "CASE-003"]


@pytest.mark.parametrize("payload", [None, np.zeros((8, 8, 3), dtype=np.uint8),
                                   np.full((8, 8, 3), 255, dtype=np.uint8)])
def test_given_unusable_image_when_quality_checked_then_not_empty_evidence(payload):
    assert not frame_quality(payload, Capture())


def test_given_textured_image_when_quality_checked_then_usable():
    payload = np.arange(192, dtype=np.uint8).reshape((8, 8, 3))

    assert frame_quality(payload, Capture())


def test_given_provider_error_when_inferring_then_explicit_failure():
    def fail(*args, **kwargs):
        raise RuntimeError("private provider failure")

    provider = object.__new__(YoloProvider)
    provider._model = SimpleNamespace(predict=fail)
    provider.settings = Perception(provider="ultralytics", model="test.pt", labels=["chair"],
                                     observationType="ObjectPresent", sampleEveryFrames=1)
    provider.confidence = 0.5
    provider.provider = "test-provider"
    provider.identity = "test-model"
    frame = Frame("camera-a", 1, "2026-09-15T12:00:00+00:00", None)

    inference = provider.infer(frame)

    assert inference.succeeded is False
    assert inference.source_id == frame.source_id
    assert inference.detections == []


def test_given_local_clip_when_captured_then_timestamped_frames_and_eof_unavailable(tmp_path):
    from time import monotonic

    import cv2
    from tiger_perception.adapters import CameraCapture
    from tiger_perception.config import Source

    path = tmp_path / "capture.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    try:
        for index in range(10):
            image = np.full((48, 64, 3), 60, dtype=np.uint8)
            image[:, index:32 + index] = 180
            writer.write(image)
    finally:
        writer.release()
    source = Source(id="replay-test", type="replay", uriFrom="TEST_CLIP", subjectId="position")
    capture = CameraCapture(source, str(path), Capture(), 1)
    received = []
    capture.start()
    try:
        deadline = monotonic() + 15
        while monotonic() < deadline:
            frame = capture.read(timeout=0.2)
            if frame is not None:
                received.append(frame)
                if frame.payload is None:
                    break
    finally:
        capture.close()

    assert any(frame.metadata["usable"] for frame in received)
    assert all(frame.source_id == "replay-test" for frame in received)
    assert received[-1].payload is None
    assert received[-1].metadata["usable"] is False


def test_given_stalled_worker_when_deadline_passes_then_reconnect_without_empty(monkeypatch):
    from tiger_perception.adapters import CameraCapture
    from tiger_perception.config import Source

    source = Source(id="camera", type="rtsp", uriFrom="CAMERA", subjectId="position")
    capture = CameraCapture(source, "rtsp://unused", Capture(), 1)
    actions = []
    capture._process = SimpleNamespace(terminate=lambda: actions.append("terminate"),
                                       join=lambda timeout: None)
    capture._heartbeat.value = 0
    monkeypatch.setattr(capture, "start", lambda: actions.append("start"))

    frame = capture.read()
    capture._frames.close()

    assert actions == ["terminate", "start"]
    assert frame.payload is None
    assert frame.metadata["watchdogRestart"] is True
    assert frame.metadata["usable"] is False
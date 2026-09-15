"""RAM retention, exact correlation and optional detector seam tests."""

import importlib.util
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pytest

from observation_service import EvidenceServer, EvidenceStore, run_service


def publish(store, sequence, jpeg=b"jpeg"):
    stamp = datetime.now(UTC).isoformat()
    store.publish(
        {"cameraId": store.camera, "timestamp": stamp,
         "frameNumber": sequence, "detections": []},
        jpeg, 10, 10, stamp, store.clock(),
    )


def test_given_retention_limits_when_evicted_then_exact_frame_is_gone():
    # Arrange
    now = [0.0]
    store = EvidenceStore("cam", "0" * 64, ttl=30, budget=6, clock=lambda: now[0])
    publish(store, 1, b"one")
    publish(store, 2, b"two")

    # Act / Assert
    publish(store, 3, b"tri")
    assert store.image("cam", store.session, 1)[0] == 410
    assert store.image("cam", store.session, 2) == (200, b"two")
    assert store.used == 6
    assert store.image("other", store.session, 2)[0] == 404
    assert store.image("cam", "0" * 32, 2)[0] == 404
    assert store.image("cam", store.session, 4)[0] == 404
    now[0] = 30
    store.sweep()
    assert store.used == 0
    assert store.image("cam", store.session, 3)[0] == 410
    assert store.snapshot()["ageSeconds"] == 30


def test_given_oversized_or_old_image_when_published_then_no_retention():
    # Arrange
    store = EvidenceStore("cam", "0" * 64, budget=2, clock=lambda: 40)
    stamp = datetime.now(UTC).isoformat()
    record = {"cameraId": "cam", "timestamp": stamp, "frameNumber": 1, "detections": []}

    # Act
    store.publish(record, b"abc", 10, 10, stamp, 0)

    # Assert
    assert store.used == 0
    assert not store.snapshot()["observation"]["image"]["retainedAtPublication"]


@pytest.mark.parametrize(("ttl", "budget"), [(0, 10), (float("nan"), 1), (30, 0)])
def test_given_invalid_retention_when_created_then_rejected(ttl, budget):
    # Act / Assert
    with pytest.raises(ValueError):
        EvidenceStore("cam", "0" * 64, ttl, budget)


def test_given_concurrent_reads_when_eviction_occurs_then_no_cross_frame_substitution():
    # Arrange
    store = EvidenceStore("cam", "0" * 64, budget=8)
    publish(store, 1, b"original")

    def read(_):
        return store.image("cam", store.session, 1)

    # Act
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(read, i) for i in range(40)]
        publish(store, 2, b"newimage")
        results = [future.result() for future in pending]

    # Assert
    assert all(status == 410 or (status, data) == (200, b"original")
               for status, data in results)
    store.close()
    assert store.used == 0 and not store.snapshot()["available"]


def test_given_http_service_when_polled_then_immutable_identity_and_exact_status():
    # Arrange
    store = EvidenceStore("cam", "0" * 64)
    publish(store, 1)
    server = EvidenceServer(("127.0.0.1", 0), store)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    # Act / Assert
    try:
        with urlopen(origin + "/v1/observations/latest", timeout=2) as response:
            envelope = json.load(response)
        assert envelope["observation"]["frameId"] == f"cam/{store.session}/1"
        with urlopen(origin + f"/v1/frames/cam/{store.session}/1", timeout=2) as response:
            assert response.read() == b"jpeg"
            assert response.headers["Cache-Control"] == "no-store"
        with pytest.raises(HTTPError) as missing:
            urlopen(origin + f"/v1/frames/cam/{store.session}/2", timeout=2)
        assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_given_optional_observer_when_detector_runs_then_legacy_jsonl_is_unchanged(
    tmp_path, monkeypatch,
):
    # Arrange
    source = Path(__file__).resolve().parents[1] / "src" / "rtsp_yolo.py"
    spec = importlib.util.spec_from_file_location("detector_seam_test", source)
    detector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detector)
    frames = [np.zeros((4, 6, 3), dtype=np.uint8) for _ in range(4)]
    released = []

    class Capture:
        def isOpened(self):
            return True

        def read(self):
            return True, frames.pop(0)

        def release(self):
            released.append(True)

    model = SimpleNamespace(predict=lambda **_: [SimpleNamespace(boxes=None)])
    monkeypatch.setattr(detector, "YOLO", lambda _: model)
    monkeypatch.setattr(detector.cv2, "VideoCapture", lambda _: Capture())
    output = tmp_path / "detections.jsonl"
    args = SimpleNamespace(
        model="inert", rtsp_url="unused", output=output, camera_id="cam",
        confidence=0.5, frame_stride=2, max_frames=2,
    )
    observed = []

    # Act
    detector.run(args, observer=lambda *values: observed.append(values))
    records = [json.loads(line) for line in output.read_text().splitlines()]

    # Assert
    assert [record["frameNumber"] for record in records] == [2, 4]
    assert set(records[0]) == {"cameraId", "timestamp", "frameNumber", "detections"}
    assert [item[0] for item in observed] == records
    assert observed[0][1].shape == (4, 6, 3)
    assert observed[0][2] <= records[0]["timestamp"]
    assert released == [True]


def test_given_service_mode_when_worker_finishes_then_jpeg_and_lifecycle_are_real(monkeypatch):
    # Arrange
    observed = []
    config = SimpleNamespace(camera_id="cam")
    import cv2

    capture_calls = []
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: capture_calls.append(args))

    class Detector:
        def run(self, args, observer, capture_factory):
            capture_factory("rtsp://camera.invalid/")
            stamp = datetime.now(UTC).isoformat()
            import time

            observer(
                {"cameraId": "cam", "timestamp": stamp, "frameNumber": 1, "detections": []},
                np.zeros((16, 16, 3), dtype=np.uint8), stamp, time.monotonic(),
            )
            with urlopen("http://127.0.0.1:8080/v1/observations/latest", timeout=2) as response:
                envelope = json.load(response)
            path = envelope["observation"]["image"]["path"]
            with urlopen("http://127.0.0.1:8080" + path, timeout=2) as response:
                observed.append(response.read())
            return 0

    # Act
    result = run_service(config, Detector(), {"YOLO_MODEL_SHA256": "0" * 64})

    # Assert
    assert result == 0
    assert observed[0].startswith(b"\xff\xd8")
    assert capture_calls == [("rtsp://camera.invalid/", cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000,
    ])]
    assert not any(t.name == "evidence-api" for t in threading.enumerate())

"""Synthetic-only contract integration and isolated Compose smoke support.

No production fixture mode is installed in either image. This file is mounted
read-only only by smoke.compose.yaml; generated pixels never leave memory.
"""

import json
import signal
import sys
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace


def record(number, present=True):
    stamp = datetime.now(UTC).isoformat()
    return {
        "cameraId": "camera-01", "frameNumber": number, "timestamp": stamp,
        "detections": [{
            "classId": 0, "label": "person", "confidence": 0.9,
            "boundingBox": {"xMin": 8, "yMin": 8, "xMax": 40, "yMax": 40},
        }] if present else [],
    }


def serve():
    """Drive the real service wrapper with synthetic pixels, never a camera/model."""
    import numpy as np

    from observation_service import run_service

    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())

    class FixtureDetector:
        def run(self, config, observer, capture_factory):
            number = 0
            while not stopped.is_set():
                for present in (True, False):
                    for _ in range(8):
                        if stopped.is_set():
                            return 0
                        number += 1
                        frame = np.full((48, 64, 3), number % 255, dtype=np.uint8)
                        item = record(number, present)
                        observer(item, frame, item["timestamp"], time.monotonic())
                        stopped.wait(0.2)
                stopped.wait(2)
            return 0

    return run_service(
        SimpleNamespace(camera_id="camera-01"), FixtureDetector(),
        {"YOLO_MODEL_SHA256": "0" * 64, "FRAME_TTL_SECONDS": "1",
         "VISION_BIND_HOST": "0.0.0.0"},
    )


def probe():
    """Check image correlation from the actual brain runtime across Docker DNS."""
    from brain import VisionClient

    client = VisionClient("http://vision:8080")
    for _ in range(30):
        try:
            obs = client.latest()["observation"]
            if obs:
                status, jpeg = client.matching_image(obs)
                if status == 200:
                    assert jpeg[:2] == b"\xff\xd8"
                    print(json.dumps({"matchingJpeg": True, "frameId": obs["frameId"]}))
                    return 0
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError("No exact JPEG available")


def test_given_loopback_vision_when_brain_polls_then_events_and_jpeg_match():
    # Arrange
    import cv2
    import numpy as np
    from brain import Config, VisionClient, ZoneRules, poll_once

    from observation_service import EvidenceServer, EvidenceStore

    store = EvidenceStore("camera-01", "0" * 64, ttl=0.3)
    server = EvidenceServer(("127.0.0.1", 0), store)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    client = VisionClient(f"http://127.0.0.1:{server.server_port}")
    rules = ZoneRules(Config())
    pixels = np.full((48, 64, 3), 96, dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", pixels)
    jpeg = encoded.tobytes()

    # Act / Assert
    try:
        assert poll_once(client, rules)[0]["state"] == "unknown"
        for number in range(1, 3):
            item = record(number)
            store.publish(item, jpeg, 64, 48, item["timestamp"], time.monotonic())
            events = poll_once(client, rules)
        assert events[0]["state"] == "occupied"
        assert poll_once(client, rules) == []
        obs = client.latest()["observation"]
        status, fetched = client.matching_image(obs)
        assert status == 200 and fetched == jpeg
        decoded = cv2.imdecode(np.frombuffer(fetched, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert np.array_equal(decoded, pixels)
        for number in range(3, 6):
            item = record(number, False)
            store.publish(item, jpeg, 64, 48, item["timestamp"], time.monotonic())
            events = poll_once(client, rules)
        assert events[0]["state"] == "clear"
        time.sleep(0.35)
        assert client.matching_image(obs) == (410, None)
        store.close()
        assert poll_once(client, rules)[0]["state"] == "unknown"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert poll_once(client, rules) == []


def test_given_invalid_http_responses_when_fetching_then_transport_is_rejected():
    # Arrange
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import pytest
    from brain import MAX_JSON_BYTES, VisionClient

    class Handler(BaseHTTPRequestHandler):
        case = "oversized"

        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header(
                "Content-Length", str(MAX_JSON_BYTES + 1) if self.case == "oversized" else "4"
            )
            self.end_headers()
            if self.case == "truncated":
                self.wfile.write(b"{}")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    client = VisionClient(f"http://127.0.0.1:{server.server_port}")

    # Act / Assert
    try:
        for case in ("oversized", "truncated"):
            Handler.case = case
            with pytest.raises(ValueError):
                client.latest()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    sys.exit(serve() if sys.argv[1:] == ["serve"] else probe())

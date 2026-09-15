"""Trusted-local latest observations and exact, short-lived RAM JPEG evidence."""

from __future__ import annotations

import json
import math
import re
import socket
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_OBSERVATION_BYTES = 256 * 1024


class EvidenceStore:
    """Retain only the latest observation and bounded immutable JPEG bytes."""

    def __init__(
        self, camera: str, model_hash: str, ttl: float = 30,
        budget: int = 64 * 1024 * 1024, clock=time.monotonic,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", camera):
            raise ValueError("Invalid camera ID")
        if not math.isfinite(ttl) or not 0 < ttl <= 300 or not 1 <= budget <= 256 * 1024 * 1024:
            raise ValueError("Invalid retention limits")
        self.camera, self.model_hash = camera, model_hash
        self.session = uuid4().hex
        self.ttl, self.budget, self.clock = ttl, budget, clock
        self.lock = threading.Lock()
        self.images: OrderedDict[int, tuple[float, bytes]] = OrderedDict()
        self.used = 0
        self.latest: dict | None = None
        self.received = 0.0
        self.sequence = 0
        self.available = True

    def _expire(self, now: float) -> None:
        while self.images:
            _, (created, data) = next(iter(self.images.items()))
            if now - created < self.ttl:
                break
            self.images.popitem(last=False)
            self.used -= len(data)

    def publish(
        self, record: dict, jpeg: bytes | None, width: int, height: int,
        captured_at: str, captured_mono: float,
    ) -> None:
        """Publish an observation and its exact JPEG atomically; never write images."""
        number = record["frameNumber"]
        path = f"/v1/frames/{self.camera}/{self.session}/{number}"
        observation = {
            **record, "schemaVersion": "1.0", "sessionId": self.session,
            "frameId": f"{self.camera}/{self.session}/{number}",
            "capturedAt": captured_at, "processedAt": record["timestamp"],
            "timestampMeaning": "processing-complete-utc",
            "captureTimestampMeaning": "host-frame-received-utc",
            "frame": {"width": width, "height": height},
            "source": {"kind": "rtsp", "cameraId": self.camera},
            "model": {"provider": "ultralytics", "sha256": self.model_hash},
            "image": {"path": path, "mediaType": "image/jpeg"},
        }
        if len(json.dumps(observation).encode()) > MAX_OBSERVATION_BYTES:
            raise ValueError("Observation exceeds limit")
        with self.lock:
            now = self.clock()
            if number <= self.sequence or captured_mono > now:
                raise ValueError("Non-increasing sequence or invalid capture time")
            self._expire(now)
            retained = (
                jpeg is not None and 0 < len(jpeg) <= min(self.budget, MAX_JPEG_BYTES)
                and now - captured_mono < self.ttl
            )
            if retained:
                while self.images and (self.used + len(jpeg) > self.budget
                                       or len(self.images) >= 256):
                    _, (_, removed) = self.images.popitem(last=False)
                    self.used -= len(removed)
                self.images[number] = (captured_mono, jpeg)
                self.used += len(jpeg)
            observation["image"]["retainedAtPublication"] = retained
            self.latest, self.received, self.sequence = observation, captured_mono, number

    def snapshot(self) -> dict:
        """Return age from original capture, never from polling time."""
        with self.lock:
            now = self.clock()
            self._expire(now)
            return {
                "schemaVersion": "1.0", "available": self.available,
                "observation": self.latest,
                "ageSeconds": max(0, now - self.received) if self.latest else None,
            }

    def sweep(self) -> None:
        """Release expired JPEGs even when capture and polling have stopped."""
        with self.lock:
            self._expire(self.clock())

    def image(self, camera: str, session: str, number: int) -> tuple[int, bytes]:
        """Return exact evidence, 410 for unavailable past IDs, or 404 for unknown."""
        with self.lock:
            self._expire(self.clock())
            if camera != self.camera or session != self.session or number > self.sequence:
                return 404, b'{"error":"not_found"}'
            item = self.images.get(number)
            return (200, item[1]) if item else (410, b'{"error":"expired_or_not_retained"}')

    def close(self) -> None:
        """Erase owned image references and mark observations unavailable."""
        with self.lock:
            self.available = False
            self.images.clear()
            self.used = 0


class EvidenceServer(ThreadingHTTPServer):
    """Bound HTTP concurrency, socket lifetime and response sizes on a private network."""

    daemon_threads = False
    allow_reuse_address = True
    request_queue_size = 4

    def __init__(self, address: tuple[str, int], store: EvidenceStore) -> None:
        self.store = store
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, EvidenceHandler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(3)
        return request, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        def expire_request():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(3, expire_request)
        timer.start()
        try:
            super().process_request_thread(request, client_address)
        finally:
            timer.cancel()
            timer.join()
            self.slots.release()

    def service_actions(self):
        self.store.sweep()

    def handle_error(self, request, client_address):
        """Do not echo request data or client addresses to logs."""


class EvidenceHandler(BaseHTTPRequestHandler):
    """Serve only latest JSON and exact JPEG routes; suppress request logging."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if len(self.path) > 256 or sum(len(k) + len(v) for k, v in self.headers.items()) > 8192:
            self.send_error(431)
            return
        status, content_type = 200, "application/json"
        if self.path == "/v1/observations/latest":
            data = json.dumps(self.server.store.snapshot(), separators=(",", ":")).encode()
        else:
            match = re.fullmatch(
                r"/v1/frames/([A-Za-z0-9_-]{1,64})/([a-f0-9]{32})/([1-9][0-9]{0,15})",
                self.path,
            )
            if match:
                camera, session, number = match.groups()
                status, data = self.server.store.image(camera, session, int(number))
                if status == 200:
                    content_type = "image/jpeg"
            else:
                status, data = 404, b'{"error":"not_found"}'
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)


def run_service(config, detector, env) -> int:
    """Wire real detection to evidence service; legacy mode never calls this."""
    import cv2

    ttl = float(env.get("FRAME_TTL_SECONDS", "30"))
    budget = int(env.get("FRAME_BUFFER_BYTES", str(64 * 1024 * 1024)))
    store = EvidenceStore(config.camera_id, env["YOLO_MODEL_SHA256"].lower(), ttl, budget)
    server = EvidenceServer((env.get("VISION_BIND_HOST", "127.0.0.1"), 8080), store)
    thread = threading.Thread(target=server.serve_forever, name="evidence-api")
    thread.start()

    def observe(record, frame, captured_at, captured_mono):
        height, width = frame.shape[:2]
        jpeg = None
        if width * height <= 16_777_216:
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok and encoded.nbytes <= MAX_JPEG_BYTES:
                jpeg = encoded.tobytes()
        store.publish(record, jpeg, width, height, captured_at, captured_mono)

    def capture_factory(url):
        return cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000,
        ])

    try:
        return detector.run(config, observer=observe, capture_factory=capture_factory)
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join()

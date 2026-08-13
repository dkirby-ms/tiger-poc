"""Capture frames from a file or RTSP source and deliver them over HTTP."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Protocol

import cv2
import requests


@dataclass(frozen=True)
class Frame:
    """A sampled JPEG frame and the metadata needed by downstream services."""

    camera_id: str
    sequence: int
    captured_at: str
    width: int
    height: int
    jpeg: bytes


class FrameSink(Protocol):
    def publish(self, frame: Frame) -> None:
        """Deliver one frame to the configured downstream interface."""


@dataclass(frozen=True)
class GrabberConfig:
    source: str
    source_type: str
    camera_id: str
    sample_rate: float
    output_url: str

    @classmethod
    def from_environment(cls) -> "GrabberConfig":
        source_type = os.getenv("VIDEO_SOURCE_TYPE", "rtsp").lower()
        source = os.getenv("VIDEO_SOURCE", "rtsp://rtsp-simulator:8554/camera-1")
        sample_rate = float(os.getenv("FRAME_RATE", "2"))
        if source_type not in {"file", "rtsp"}:
            raise ValueError("VIDEO_SOURCE_TYPE must be 'file' or 'rtsp'")
        if not source.strip():
            raise ValueError("VIDEO_SOURCE must be set to a file path or RTSP URL")
        if sample_rate <= 0:
            raise ValueError("FRAME_RATE must be greater than zero")
        return cls(
            source=source,
            source_type=source_type,
            camera_id=os.getenv("CAMERA_ID", "camera-1"),
            sample_rate=sample_rate,
            output_url=os.getenv("FRAME_OUTPUT_URL", "http://pre-processor:8080/frames"),
        )


class HttpFrameSink:
    """Send JPEG bytes with metadata headers to the pre-processor endpoint."""

    def __init__(self, output_url: str, timeout_seconds: float = 10) -> None:
        self.output_url = output_url
        self.timeout_seconds = timeout_seconds

    def publish(self, frame: Frame) -> None:
        response = requests.post(
            self.output_url,
            data=frame.jpeg,
            headers={
                "Content-Type": "image/jpeg",
                "X-Camera-Id": frame.camera_id,
                "X-Frame-Sequence": str(frame.sequence),
                "X-Captured-At": frame.captured_at,
                "X-Frame-Width": str(frame.width),
                "X-Frame-Height": str(frame.height),
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


def sample_interval(source_fps: float, target_fps: float) -> int:
    """Return the source-frame interval needed to approximate target_fps."""

    if source_fps <= 0 or target_fps <= 0:
        raise ValueError("source_fps and target_fps must be greater than zero")
    return max(1, round(source_fps / target_fps))


def sampled_frames(capture: Any, target_fps: float) -> Iterator[tuple[int, Any]]:
    """Yield selected ``(source_index, image)`` pairs from an OpenCV capture."""

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    interval = sample_interval(source_fps, target_fps)
    source_index = 0
    while True:
        success, image = capture.read()
        if not success:
            break
        if source_index % interval == 0:
            yield source_index, image
        source_index += 1


def open_capture(config: GrabberConfig) -> Any:
    source: str | int = config.source
    if config.source_type == "file" and source.isdigit():
        source = int(source)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open {config.source_type} source: {config.source}")
    return capture


def capture_frames(config: GrabberConfig, sink: FrameSink) -> int:
    """Capture, encode, and publish frames until the source is exhausted."""

    capture = open_capture(config)
    published = 0
    try:
        for source_index, image in sampled_frames(capture, config.sample_rate):
            success, encoded = cv2.imencode(".jpg", image)
            if not success:
                raise RuntimeError(f"Unable to JPEG encode source frame {source_index}")
            height, width = image.shape[:2]
            sink.publish(
                Frame(
                    camera_id=config.camera_id,
                    sequence=published,
                    captured_at=datetime.now(timezone.utc).isoformat(),
                    width=width,
                    height=height,
                    jpeg=encoded.tobytes(),
                )
            )
            published += 1
    finally:
        capture.release()
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Exit after one capture pass")
    args = parser.parse_args()
    config = GrabberConfig.from_environment()
    sink = HttpFrameSink(config.output_url)
    while True:
        try:
            capture_frames(config, sink)
        except (RuntimeError, requests.RequestException) as error:
            print(f"frame-grabber: {error}", file=sys.stderr)
            if config.source_type == "file" or args.once:
                return 1
            time.sleep(5)
        if config.source_type == "file" or args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
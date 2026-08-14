"""Resize, normalize, and batch JPEG frames before they reach inference."""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import tempfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable

import cv2
import numpy as np
import requests


@dataclass(frozen=True)
class PreprocessorConfig:
    """Runtime configuration for the preprocessing stage."""

    target_width: int = 320
    target_height: int = 240
    batch_size: int = 1
    inference_url: str = "http://inference-api:8081/process"

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> "PreprocessorConfig":
        source = os.environ if env is None else env
        target_width = int(source.get("PREPROCESS_TARGET_WIDTH", "320"))
        target_height = int(source.get("PREPROCESS_TARGET_HEIGHT", "240"))
        batch_size = int(source.get("PREPROCESS_BATCH_SIZE", "1"))

        if target_width <= 0:
            raise ValueError("PREPROCESS_TARGET_WIDTH must be greater than zero")
        if target_height <= 0:
            raise ValueError("PREPROCESS_TARGET_HEIGHT must be greater than zero")
        if batch_size <= 0:
            raise ValueError("PREPROCESS_BATCH_SIZE must be greater than zero")

        return cls(
            target_width=target_width,
            target_height=target_height,
            batch_size=batch_size,
            inference_url=source.get(
                "PREPROCESS_INFERENCE_URL",
                "http://inference-api:8081/process",
            ),
        )

    @property
    def target_size(self) -> tuple[int, int]:
        return (self.target_width, self.target_height)


def _decode_jpeg(frame_bytes: bytes) -> np.ndarray:
    encoded = np.frombuffer(frame_bytes, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unable to decode JPEG frame")
    return image


def preprocess_frame(frame_bytes: bytes, target_size: tuple[int, int] | None = None) -> np.ndarray:
    """Return a normalized tensor with shape ``(1, 3, H, W)`` and dtype float32."""

    image = _decode_jpeg(frame_bytes)
    target_width, target_height = target_size or PreprocessorConfig.from_environment().target_size
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
    tensor = resized.astype(np.float32) / 255.0
    channel_first = np.transpose(tensor, (2, 0, 1))[np.newaxis, :, :, :]
    return channel_first.astype(np.float32)


def preprocess_batch(frames: Iterable[bytes], target_size: tuple[int, int] | None = None) -> np.ndarray:
    """Stack multiple frames into a batch with shape ``(N, 3, H, W)``."""

    frame_list = list(frames)
    if not frame_list:
        raise ValueError("No frames were supplied for batching")

    normalized = [preprocess_frame(frame, target_size)[0] for frame in frame_list]
    return np.stack(normalized, axis=0).astype(np.float32)


def _encode_clip(image: np.ndarray) -> bytes:
    """Encode the captured frame as a short browser-compatible MP4 clip."""

    with tempfile.TemporaryDirectory() as directory:
        input_path = os.path.join(directory, "frame.jpg")
        output_path = os.path.join(directory, "clip.mp4")
        if not cv2.imwrite(input_path, image):
            raise ValueError("Unable to encode detection frame")

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    input_path,
                    "-t",
                    "2",
                    "-r",
                    "5",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("Unable to create browser-compatible MP4 detection clip") from error

        with open(output_path, "rb") as clip_file:
            return clip_file.read()


class PreprocessorHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], config: PreprocessorConfig):
        self.config = config
        super().__init__(server_address, handler_class)


class FramePreprocessorHandler(BaseHTTPRequestHandler):
    server_version = "TigerPreprocessor/1.0"

    def do_POST(self) -> None:
        if self.path != "/frames":
            self.send_error(404, "Unknown endpoint")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        frame_bytes = self.rfile.read(content_length)
        try:
            config = getattr(self.server, "config", PreprocessorConfig())
            image = _decode_jpeg(frame_bytes)
            processed = preprocess_frame(frame_bytes, config.target_size)
            requests.post(
                config.inference_url,
                json={
                    "frame_jpeg": base64.b64encode(frame_bytes).decode("ascii"),
                    "clip_base64": base64.b64encode(_encode_clip(image)).decode("ascii"),
                    "model_id": os.getenv("MODEL_ID", "yolo"),
                    "source_id": self.headers.get("X-Camera-Id", "camera-1"),
                },
                timeout=30,
            ).raise_for_status()
        except (ValueError, requests.RequestException) as exc:
            self.send_error(400, str(exc))
            return

        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Processed-Shape", "{}x{}x{}x{}".format(*processed.shape))
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PREPROCESSOR_PORT", "8080")))
    return parser


def main() -> int:
    args = create_parser().parse_args()
    config = PreprocessorConfig.from_environment()
    server = PreprocessorHTTPServer((args.host, args.port), FramePreprocessorHandler, config)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

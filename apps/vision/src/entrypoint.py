"""Guard container configuration before invoking the RTSP detector."""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import os
import re
import signal
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

LOGGER = logging.getLogger(__name__)


class ConfigurationError(ValueError):
    """A safe-to-display container configuration error."""


def create_parser() -> argparse.ArgumentParser:
    """Expose only operational switches, never camera credentials in arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-runtime", action="store_true", help="Import libraries without camera/model access."
    )
    return parser


def load_configuration(env: Mapping[str, str]) -> argparse.Namespace:
    """Validate explicit camera/model settings without probing any network endpoint."""
    secret_path = Path(env.get("RTSP_URL_FILE", "/run/secrets/rtsp_url"))
    try:
        with secret_path.open("r", encoding="utf-8") as secret:
            url = secret.read(4097).strip()
        parsed = urlsplit(url)
        port = parsed.port
    except (OSError, UnicodeError, ValueError):
        raise ConfigurationError(
            "Provide a readable UTF-8 RTSP_URL_FILE with a valid RTSP URL."
        ) from None
    if (
        not url
        or len(url) > 4096
        or any(ord(char) < 32 for char in url)
        or parsed.scheme not in {"rtsp", "rtsps"}
        or not parsed.hostname
        or parsed.fragment
        or port == 0
    ):
        raise ConfigurationError("RTSP_URL_FILE must contain one valid rtsp/rtsps URL.")

    model = Path(env.get("YOLO_MODEL", "/models/model.pt"))
    expected_hash = env.get("YOLO_MODEL_SHA256", "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
        raise ConfigurationError("Set YOLO_MODEL_SHA256 to the trusted model's SHA-256.")
    if model.suffix.lower() != ".pt" or not model.is_file():
        raise ConfigurationError(
            "Mount an existing trusted .pt model at YOLO_MODEL; downloads are disabled."
        )
    try:
        with model.open("rb") as weights:
            actual_hash = hashlib.file_digest(weights, "sha256").hexdigest()
    except OSError:
        raise ConfigurationError("YOLO_MODEL is not readable by the container user.") from None
    if actual_hash != expected_hash.lower():
        raise ConfigurationError("YOLO_MODEL SHA-256 mismatch; refusing to load weights.")

    camera_id = env.get("CAMERA_ID", "camera-01")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", camera_id):
        raise ConfigurationError("CAMERA_ID must use 1-64 letters, digits, underscores or hyphens.")
    try:
        confidence = float(env.get("CONFIDENCE", "0.5"))
        stride = int(env.get("FRAME_STRIDE", "5"))
        max_frames = int(env.get("MAX_FRAMES", "0"))
    except ValueError:
        raise ConfigurationError(
            "CONFIDENCE, FRAME_STRIDE and MAX_FRAMES must be numeric."
        ) from None
    if not math.isfinite(confidence) or not 0 <= confidence <= 1 or stride < 1 or max_frames < 0:
        raise ConfigurationError(
            "Require confidence in [0,1], frame stride >=1 and max frames >=0."
        )
    output_dir = Path(env.get("OUTPUT_DIR", "/output"))
    if not output_dir.is_dir():
        raise ConfigurationError("OUTPUT_DIR must be an existing writable mounted directory.")
    output = output_dir / f"detections-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex}.jsonl"
    return argparse.Namespace(
        rtsp_url=url,
        model=str(model),
        output=output,
        camera_id=camera_id,
        confidence=confidence,
        frame_stride=stride,
        max_frames=max_frames,
        verbose=False,
    )


def stop_requested(_signum: int, _frame: object) -> None:
    """Translate container stop into the detector's existing cleanup path."""
    raise KeyboardInterrupt


def main() -> int:
    """Check the runtime or start real detection; never substitute fake results."""
    args = create_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    signal.signal(signal.SIGTERM, stop_requested)
    try:
        if args.check_runtime:
            import cv2
            import torch
            import ultralytics

            import_module("rtsp_yolo")
            import_module("observation_service")
            LOGGER.info(
                "Runtime ready: OpenCV=%s YOLO=%s PyTorch=%s; camera/model not checked",
                cv2.__version__, ultralytics.__version__, torch.__version__,
            )
            return 0
        config = load_configuration(os.environ)
        import rtsp_yolo

        # Reserve a unique output path before model/camera work; never truncate older runs.
        with config.output.open("x", encoding="utf-8"):
            pass
        mode = os.environ.get("VISION_SERVICE", "false")
        if mode not in {"true", "false"}:
            raise ConfigurationError("VISION_SERVICE must be true or false.")
        if mode == "true":
            from observation_service import run_service

            return run_service(config, rtsp_yolo, os.environ)
        return rtsp_yolo.run(config)
    except ConfigurationError as error:
        LOGGER.error("%s", error)
        return 2
    except KeyboardInterrupt:
        LOGGER.info("Detection stopped")
        return 130
    except (OSError, RuntimeError, ValueError) as error:
        # Third-party exception strings can include camera URLs or credentials.
        LOGGER.error(
            "Detection failed (%s); check local model, stream and output access.",
            type(error).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

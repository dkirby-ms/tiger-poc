from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from pre_processor.service import PreprocessorConfig, preprocess_batch, preprocess_frame


def _jpeg_bytes(image: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        raise RuntimeError("failed to encode test image")
    return encoded.tobytes()


def test_given_rgb_frame_when_preprocess_then_resizes_and_normalizes() -> None:
    image = np.zeros((24, 32, 3), dtype=np.uint8)
    image[:, :, 0] = 255
    image[:, :, 1] = 128
    image[:, :, 2] = 64

    output = preprocess_frame(_jpeg_bytes(image), target_size=(16, 8))

    assert output.shape == (1, 3, 8, 16)
    assert output.dtype == np.float32
    assert output.min() >= 0.0
    assert output.max() <= 1.0


def test_given_multiple_frames_when_preprocess_batch_then_returns_channel_first_batch() -> None:
    image_a = np.full((16, 16, 3), 10, dtype=np.uint8)
    image_b = np.full((16, 16, 3), 200, dtype=np.uint8)

    batch = preprocess_batch([
        _jpeg_bytes(image_a),
        _jpeg_bytes(image_b),
    ], target_size=(8, 8))

    assert batch.shape == (2, 3, 8, 8)
    assert batch.dtype == np.float32
    assert batch[0].mean() > 0.0
    assert batch[1].mean() > batch[0].mean()


def test_given_environment_when_configure_then_reads_size_and_batch() -> None:
    config = PreprocessorConfig.from_environment({
        "PREPROCESS_TARGET_WIDTH": "320",
        "PREPROCESS_TARGET_HEIGHT": "240",
        "PREPROCESS_BATCH_SIZE": "4",
    })

    assert config.target_width == 320
    assert config.target_height == 240
    assert config.batch_size == 4

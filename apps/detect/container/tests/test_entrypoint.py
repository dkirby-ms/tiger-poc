"""Container boundary tests; no real camera, credentials or model execution."""

import argparse
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import entrypoint


@pytest.fixture
def configured_env(tmp_path: Path) -> dict[str, str]:
    """Provide inert test bytes and a reserved example hostname."""
    secret = tmp_path / "camera.txt"
    secret.write_text("rtsp://example.invalid/stream", encoding="utf-8")
    model = tmp_path / "model.pt"
    model.write_bytes(b"inert-test-bytes-not-a-model")
    return {
        "RTSP_URL_FILE": str(secret),
        "YOLO_MODEL": str(model),
        "YOLO_MODEL_SHA256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "OUTPUT_DIR": str(tmp_path),
    }


def test_given_valid_config_when_loaded_then_matches_detector_contract(configured_env):
    # Act
    config = entrypoint.load_configuration(configured_env)

    # Assert
    assert (config.camera_id, config.confidence, config.frame_stride, config.max_frames) == (
        "camera-01", 0.5, 5, 0,
    )
    assert config.rtsp_url == "rtsp://example.invalid/stream"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("YOLO_MODEL_SHA256", ""),
        ("YOLO_MODEL_SHA256", "0" * 64),
        ("YOLO_MODEL", "/missing/model.pt"),
        ("CAMERA_ID", "camera/password"),
        ("CONFIDENCE", "nan"),
        ("CONFIDENCE", "inf"),
        ("CONFIDENCE", "1.1"),
        ("FRAME_STRIDE", "0"),
        ("MAX_FRAMES", "-1"),
        ("MAX_FRAMES", "hello"),
        ("OUTPUT_DIR", "/missing/output"),
    ],
)
def test_given_invalid_setting_when_loaded_then_rejected(configured_env, key, value):
    # Arrange
    configured_env[key] = value

    # Act / Assert
    with pytest.raises(entrypoint.ConfigurationError):
        entrypoint.load_configuration(configured_env)


@pytest.mark.parametrize(
    "url",
    ["", "https://example.invalid", "rtsp:///stream", "rtsp://host:bad/a", "rtsp://host:0/a",
     "rtsp://host/a\nsecond-line", "rtsp://host/a#fragment", "rtsp://host/" + "a" * 4096],
)
def test_given_invalid_url_when_loaded_then_error_omits_input(configured_env, url):
    # Arrange
    Path(configured_env["RTSP_URL_FILE"]).write_text(url, encoding="utf-8")

    # Act / Assert
    with pytest.raises(entrypoint.ConfigurationError, match="RTSP"):
        entrypoint.load_configuration(configured_env)


def test_given_repeated_runs_when_configured_then_output_names_differ(configured_env):
    # Act
    first = entrypoint.load_configuration(configured_env).output
    second = entrypoint.load_configuration(configured_env).output

    # Assert
    assert first != second
    assert not first.exists() and not second.exists()


def test_given_missing_secret_when_starting_then_exit_two_before_detector_import(monkeypatch):
    # Arrange
    monkeypatch.setattr(sys, "argv", ["entrypoint.py"])
    monkeypatch.setenv("RTSP_URL_FILE", "/missing/secret")

    # Act
    result = entrypoint.main()

    # Assert
    assert result == 2
    assert "rtsp_yolo" not in sys.modules


def test_given_valid_settings_when_starting_then_calls_existing_detector(
    configured_env, monkeypatch
):
    # Arrange
    calls: list[argparse.Namespace] = []

    def run(config: argparse.Namespace) -> int:
        calls.append(config)
        assert config.output.exists()
        return 0

    monkeypatch.setattr(sys, "argv", ["entrypoint.py"])
    monkeypatch.setitem(sys.modules, "rtsp_yolo", SimpleNamespace(run=run))
    for key, value in configured_env.items():
        monkeypatch.setenv(key, value)

    # Act
    result = entrypoint.main()

    # Assert
    assert result == 0
    assert len(calls) == 1


def test_given_sigterm_when_received_then_interrupts_for_cleanup():
    # Act / Assert
    with pytest.raises(KeyboardInterrupt):
        entrypoint.stop_requested(15, None)

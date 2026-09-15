"""Ensure packaged execution matches upstream without sample connection defaults."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from package_detector import FUNCTIONS, package


def test_given_upstream_when_packaged_then_execution_asts_are_unchanged(tmp_path):
    # Arrange
    source = Path(__file__).resolve().parents[1] / "src" / "rtsp_yolo.py"
    output = tmp_path / "detector.py"

    # Act
    package(source, output)
    original = ast.parse(source.read_text(encoding="utf-8"))
    packaged = ast.parse(output.read_text(encoding="utf-8"))

    # Assert
    for name in FUNCTIONS:
        before = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == name)
        after = next(n for n in packaged.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(before) == ast.dump(after)
    assert "rtsp://" not in output.read_text(encoding="utf-8").lower()
    assert "DEFAULT_RTSP_URL" not in output.read_text(encoding="utf-8")


def test_given_changed_interface_when_packaged_then_build_fails(tmp_path):
    # Arrange
    source = tmp_path / "source.py"
    source.write_text("def unrelated(): pass\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ValueError, match="interface changed"):
        package(source, tmp_path / "output.py")


def test_given_source_cli_when_help_requested_then_options_remain_available():
    # Arrange
    source = Path(__file__).resolve().parents[1] / "src" / "rtsp_yolo.py"

    # Act
    result = subprocess.run(
        [sys.executable, str(source), "--help"], capture_output=True, text=True, check=True
    )

    # Assert
    for option in (
        "--rtsp-url", "--model", "--output", "--camera-id", "--confidence",
        "--frame-stride", "--max-frames", "--verbose",
    ):
        assert option in result.stdout

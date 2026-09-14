"""Ensure packaged execution matches upstream without sample connection defaults."""

import ast
from pathlib import Path

import pytest

from package_detector import FUNCTIONS, package


def test_given_upstream_when_packaged_then_execution_asts_are_unchanged(tmp_path):
    # Arrange
    source = Path("/source/rtsp_yolo.py")
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

from pathlib import Path

import pytest
from pydantic import BaseModel

from apps.pipeline_framework import ManifestError, StageRegistry, load_pipeline


class EmptyConfig(BaseModel):
    pass


def registry() -> StageRegistry:
    value = StageRegistry()
    value.register("source.test", lambda config: object(), EmptyConfig, accepts=None, emits=int, source=True)
    value.register("transform.text", lambda config: object(), EmptyConfig, accepts=int, emits=str)
    value.register("sink.test", lambda config: object(), EmptyConfig, accepts=str, emits=None)
    return value


def write_manifest(path: Path, stages: str) -> Path:
    path.write_text(
        "apiVersion: tiger.dev/v1\n"
        "kind: Pipeline\n"
        "metadata:\n"
        "  name: test\n"
        "spec:\n"
        "  stages:\n"
        f"{stages}",
        encoding="utf-8",
    )
    return path


def test_given_valid_manifest_when_loaded_then_topological_order_is_returned(tmp_path):
    # Arrange
    path = write_manifest(
        tmp_path / "pipeline.yaml",
        "    - id: source\n"
        "      type: source.test\n"
        "    - id: convert\n"
        "      type: transform.text\n"
        "      inputs: [source]\n"
        "    - id: sink\n"
        "      type: sink.test\n"
        "      inputs: [convert]\n",
    )

    # Act
    pipeline = load_pipeline(path, registry())

    # Assert
    assert pipeline.order == ("source", "convert", "sink")


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        ("    - id: source\n      type: unknown\n", "unknown type"),
        (
            "    - id: source\n      type: source.test\n"
            "    - id: sink\n      type: sink.test\n      inputs: [source]\n",
            "does not accept output",
        ),
        (
            "    - id: source\n      type: source.test\n"
            "    - id: convert\n      type: transform.text\n      inputs: [missing]\n",
            "unknown input",
        ),
    ],
)
def test_given_invalid_graph_when_loaded_then_actionable_error_is_raised(
    tmp_path, stages, message
):
    # Arrange
    path = write_manifest(tmp_path / "pipeline.yaml", stages)

    # Act and Assert
    with pytest.raises(ManifestError, match=message):
        load_pipeline(path, registry())
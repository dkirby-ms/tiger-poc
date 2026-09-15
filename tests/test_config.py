"""Behavior tests for strict pipeline configuration and secret indirection."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tiger_poc.config import PipelineConfig, load_config


def valid_payload() -> dict[str, object]:
    """Return a minimal valid local pipeline configuration."""
    return {
        "schemaVersion": 1,
        "source": {
            "kind": "fixture",
            "path": "observations.json",
            "siteId": "factory-01",
            "deviceId": "camera-01",
            "subjectId": "station-01",
        },
        "inference": {"mode": "edge", "runtime": "foundry-local", "model": "model-v1"},
        "ontology": {
            "version": "1.0",
            "mapper": "line-monitoring",
            "confidenceThreshold": 0.8,
            "consecutiveReadings": 2,
        },
        "destination": {"kind": "local-jsonl", "path": "events.jsonl"},
    }


def test_given_missing_secret_environment_when_loading_then_names_variable_without_value(
    tmp_path: Path,
) -> None:
    # Arrange
    payload = valid_payload()
    payload["destination"] = {
        "kind": "fabric-eventstream",
        "authentication": "connection-string",
        "connectionStringEnv": "FABRIC_EVENTSTREAM_CONNECTION_STRING",
        "partitionKey": "subjectId",
        "outbox": {
            "kind": "sqlite",
            "path": ".data/outbox.db",
            "maxBytes": 1024,
            "maxAgeHours": 1,
        },
    }
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(__import__("yaml").safe_dump(payload), encoding="utf-8")

    # Act and assert
    with pytest.raises(ValueError) as error:
        load_config(config_path, environ={})
    assert str(error.value) == (
        "required environment variables are not set: FABRIC_EVENTSTREAM_CONNECTION_STRING"
    )


def test_given_secret_literal_when_validating_then_unknown_field_is_rejected() -> None:
    # Arrange
    payload = valid_payload()
    payload["destination"] = {
        "kind": "fabric-eventstream",
        "authentication": "connection-string",
        "connectionString": "Endpoint=sb://secret.example/;SharedAccessKey=secret",
        "connectionStringEnv": "FABRIC_EVENTSTREAM_CONNECTION_STRING",
        "outbox": {
            "kind": "sqlite",
            "path": ".data/outbox.db",
            "maxBytes": 1024,
            "maxAgeHours": 1,
        },
    }

    # Act and assert
    with pytest.raises(ValidationError, match="connectionString"):
        PipelineConfig.model_validate(payload)


def test_given_unknown_field_when_validating_then_manifest_is_rejected() -> None:
    # Arrange
    payload = valid_payload()
    payload["source"]["unexpected"] = True  # type: ignore[index]

    # Act and assert
    with pytest.raises(ValidationError, match="unexpected"):
        PipelineConfig.model_validate(payload)


def test_given_wrong_version_when_validating_then_manifest_is_rejected() -> None:
    # Arrange
    payload = valid_payload()
    payload["schemaVersion"] = 2

    # Act and assert
    with pytest.raises(ValidationError, match="schemaVersion"):
        PipelineConfig.model_validate(payload)

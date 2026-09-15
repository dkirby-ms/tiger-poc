"""Contract tests for canonical process events and the external JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from tiger_poc.ontology.event import ProcessEvent

FIXTURES = Path(__file__).parent / "fixtures" / "process-events"
SCHEMA = Path(__file__).parents[1] / "schemas" / "process-event-v1.schema.json"


def load_json(path: Path) -> dict[str, object]:
    """Load one JSON object fixture."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_given_malformed_fixture_when_validating_then_model_and_schema_reject_it() -> None:
    # Arrange
    payload = load_json(FIXTURES / "malformed.json")
    validator = Draft202012Validator(load_json(SCHEMA), format_checker=FormatChecker())

    # Act and assert
    with pytest.raises(ValidationError):
        ProcessEvent.model_validate(payload)
    assert list(validator.iter_errors(payload))


def test_given_non_utc_timestamp_when_validating_then_model_rejects_it() -> None:
    # Arrange
    payload = load_json(FIXTURES / "valid.json")
    payload["observedAt"] = "2026-09-14T12:20:30.123-07:00"

    # Act and assert
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        ProcessEvent.model_validate(payload)


def test_given_valid_fixture_when_round_tripping_then_identity_and_semantics_are_stable() -> None:
    # Arrange
    payload = load_json(FIXTURES / "valid.json")
    validator = Draft202012Validator(load_json(SCHEMA), format_checker=FormatChecker())

    # Act
    event = ProcessEvent.model_validate(payload)
    serialized = json.loads(event.to_json())

    # Assert
    validator.validate(serialized)
    assert serialized == payload


def test_given_valid_event_when_serializing_then_remains_below_fabric_limit() -> None:
    # Arrange
    event = ProcessEvent.model_validate(load_json(FIXTURES / "valid.json"))

    # Act
    payload_size = len(event.to_json().encode("utf-8"))

    # Assert
    assert payload_size < 1_000_000

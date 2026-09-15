"""Offline tests for idempotent Fabric Lakehouse curation decisions."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tiger_poc.fabric.curation import curate_records

REPOSITORY_ROOT = Path(__file__).parents[1]


def _raw_event(*, event_id: str, sequence: int, subject_id: str = "station-01") -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "eventId": event_id,
        "eventType": "ProcessStateChanged",
        "subjectId": subject_id,
        "subjectType": "Station",
        "siteId": "factory-01",
        "deviceId": "camera-01",
        "ontologyVersion": "1.0",
        "sequence": sequence,
        "observedAt": "2026-09-14T19:20:30.123Z",
        "emittedAt": "2026-09-14T19:20:30.456Z",
        "state": "blocked",
        "confidence": 0.94,
        "sourceRuntime": "fixture",
        "sourceModel": "fixture-model",
        "eventstreamEnqueuedAt": "2026-09-14T19:20:30.500Z",
        "eventstreamPartitionId": "0",
        "eventstreamOffset": "42",
    }


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = REPOSITORY_ROOT / "fabric" / "lakehouse" / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_given_station_event_when_curated_then_preserves_subject_and_derives_station_key() -> None:
    # Arrange
    event = _raw_event(event_id="11111111-1111-4111-8111-111111111111", sequence=1)

    # Act
    result = curate_records([event])

    # Assert
    assert result.history_rows[0]["subjectId"] == result.history_rows[0]["stationId"]


def test_given_duplicate_event_when_curated_then_rejects_duplicate() -> None:
    # Arrange
    event = _raw_event(event_id="11111111-1111-4111-8111-111111111111", sequence=2)

    # Act
    result = curate_records([event], existing_event_ids={event["eventId"]})

    # Assert
    assert result.history_rows == result.current_rows == ()
    assert [rejection.reason for rejection in result.rejected_rows] == ["duplicate"]


def test_given_stale_sequence_when_curated_then_does_not_change_current_state() -> None:
    # Arrange
    event = _raw_event(event_id="22222222-2222-4222-8222-222222222222", sequence=4)

    # Act
    result = curate_records([event], current_sequences={"station-01": 5})

    # Assert
    assert result.history_rows == result.current_rows == ()


def test_given_multiple_new_sequences_when_curated_then_selects_latest_current_state() -> None:
    # Arrange
    events: list[Mapping[str, Any]] = [
        _raw_event(event_id="11111111-1111-4111-8111-111111111111", sequence=1),
        _raw_event(event_id="22222222-2222-4222-8222-222222222222", sequence=2),
    ]

    # Act
    result = curate_records(events)

    # Assert
    assert [row["sequence"] for row in result.current_rows] == [2]


def test_given_non_station_subject_when_curated_then_rejects_invalid_mapping() -> None:
    # Arrange
    event = _raw_event(event_id="11111111-1111-4111-8111-111111111111", sequence=1)
    event["subjectType"] = "Line"

    # Act
    result = curate_records([event])

    # Assert
    assert result.rejected_rows[0].reason == "invalid"


def test_given_complete_table_schemas_when_fixture_curated_then_both_rows_validate() -> None:
    # Arrange
    raw_event = _raw_event(event_id="11111111-1111-4111-8111-111111111111", sequence=1)
    raw_validator = Draft202012Validator(_load_schema("raw-process-events-schema.json"))
    curated_validator = Draft202012Validator(_load_schema("process-events-schema.json"))

    # Act
    curated_event = curate_records([raw_event]).history_rows[0]

    # Assert
    raw_validator.validate(raw_event)
    curated_validator.validate(curated_event)

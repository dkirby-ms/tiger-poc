"""Behavior tests for the observation contract and local sink connector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tiger_poc.connectors import LocalSinkConnector, PublicationError
from tiger_poc.perception import Observation
from tiger_poc.types import JsonValue


@dataclass(frozen=True)
class StubEvent:
    """Provide a deterministic event serializer for connector tests."""

    payload: dict[str, JsonValue]

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the configured canonical payload."""
        return self.payload


def test_given_closed_sink_when_publishing_then_raises_unacknowledged_error(tmp_path: Path) -> None:
    # Arrange
    sink = LocalSinkConnector(tmp_path / "events.jsonl")
    sink.close()

    # Act and assert
    with pytest.raises(PublicationError, match="connector is closed"):
        sink.publish(StubEvent({"eventId": "event-1"}))


def test_given_event_when_publishing_then_flushes_deterministic_json_line(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "events.jsonl"
    sink = LocalSinkConnector(output_path)
    event = StubEvent({"state": "blocked", "confidence": 0.91, "eventId": "event-1"})

    # Act
    receipt = sink.publish(event)

    # Assert
    assert output_path.read_text(encoding="utf-8") == (
        '{"confidence":0.91,"eventId":"event-1","state":"blocked"}\n'
    )
    assert receipt.acknowledged is True

    sink.close()


def test_given_existing_sink_when_reopened_then_appends_without_overwrite(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "events.jsonl"
    output_path.write_text('{"eventId":"event-1"}\n', encoding="utf-8")

    # Act
    with LocalSinkConnector(output_path) as sink:
        sink.publish(StubEvent({"eventId": "event-2"}))

    # Assert
    assert output_path.read_text(encoding="utf-8") == (
        '{"eventId":"event-1"}\n{"eventId":"event-2"}\n'
    )


def test_given_naive_timestamp_when_creating_observation_then_rejects_it() -> None:
    # Arrange
    naive_timestamp = datetime(2026, 9, 14, 12, 0)

    # Act and assert
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        Observation(
            subject_id="station-01",
            observation_type="process-state",
            value="blocked",
            timestamp=naive_timestamp,
            confidence=0.91,
            source="foundry-local",
        )


def test_given_utc_observation_when_serializing_then_emits_stable_payload() -> None:
    # Arrange
    observation = Observation(
        subject_id="station-01",
        observation_type="process-state",
        value="blocked",
        timestamp=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        confidence=0.912345,
        source="foundry-local",
    )

    # Act
    payload = observation.to_dict()

    # Assert
    assert payload == {
        "subjectId": "station-01",
        "observationType": "process-state",
        "value": "blocked",
        "timestamp": "2026-09-14T12:00:00Z",
        "confidence": 0.9123,
        "source": "foundry-local",
    }

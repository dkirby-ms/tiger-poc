"""Offline tests for Fabric Eventstream SDK publication behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from azure.eventhub import EventData

from tiger_poc.connectors import PublicationError
from tiger_poc.connectors.fabric_eventstream import FabricEventstreamConnector
from tiger_poc.types import JsonValue

SECRET_CONNECTION = (
    "Endpoint=sb://private.servicebus.windows.net/;"
    "SharedAccessKeyName=send;SharedAccessKey=top-secret;EntityPath=events"
)


@dataclass(frozen=True, slots=True)
class StubEvent:
    """Provide a canonical payload for connector tests."""

    event_id: str
    subject_id: str

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a minimal canonical event payload."""
        return {"eventId": self.event_id, "subjectId": self.subject_id, "sequence": 1}


class FakeBatch:
    """Collect SDK events with an optional item limit."""

    def __init__(self, partition_key: str, *, max_events: int = 100) -> None:
        self.partition_key = partition_key
        self.max_events = max_events
        self.events: list[EventData] = []

    def add(self, event_data: EventData) -> None:
        """Add an event or emulate the SDK's full-batch exception."""
        if len(self.events) >= self.max_events:
            raise ValueError("batch full")
        self.events.append(event_data)


class FakeProducer:
    """Collect created and synchronously sent batches."""

    def __init__(self, *, max_events: int = 100, send_error: Exception | None = None) -> None:
        self.max_events = max_events
        self.send_error = send_error
        self.created: list[FakeBatch] = []
        self.sent: list[FakeBatch] = []
        self.closed = False

    def create_batch(self, *, partition_key: str) -> FakeBatch:
        """Create a fake size-bounded batch."""
        batch = FakeBatch(partition_key, max_events=self.max_events)
        self.created.append(batch)
        return batch

    def send_batch(self, event_data_batch: FakeBatch) -> None:
        """Record synchronous acceptance or raise the configured failure."""
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(event_data_batch)

    def close(self) -> None:
        """Record deterministic shutdown."""
        self.closed = True


def test_given_sas_connection_when_constructing_then_uses_connection_string_factory(
    mocker,
) -> None:
    # Arrange
    producer = FakeProducer()
    factory = mocker.Mock(return_value=producer)

    # Act
    connector = FabricEventstreamConnector.from_connection_string(
        SECRET_CONNECTION, producer_factory=factory
    )

    # Assert
    factory.assert_called_once_with(SECRET_CONNECTION)
    assert connector.destination == "fabric-eventstream://custom-endpoint"


def test_given_entra_settings_when_constructing_then_uses_credential_and_endpoint_factory(
    mocker,
) -> None:
    # Arrange
    credential = object()
    producer = FakeProducer()
    credential_factory = mocker.Mock(return_value=credential)
    producer_factory = mocker.Mock(return_value=producer)

    # Act
    FabricEventstreamConnector.from_entra(
        "private.servicebus.windows.net",
        "events",
        credential_factory=credential_factory,
        producer_factory=producer_factory,
    )

    # Assert
    producer_factory.assert_called_once_with("private.servicebus.windows.net", "events", credential)


def test_given_multiple_subjects_when_publishing_then_subject_is_partition_key() -> None:
    # Arrange
    producer = FakeProducer()
    connector = FabricEventstreamConnector(producer)

    # Act
    receipts = connector.publish_batch(
        [StubEvent("event-1", "station-01"), StubEvent("event-2", "station-02")]
    )

    # Assert
    assert [batch.partition_key for batch in producer.sent] == ["station-01", "station-02"]
    assert len(receipts) == 2


def test_given_batch_limit_when_publishing_then_sends_size_bounded_batches() -> None:
    # Arrange
    producer = FakeProducer(max_events=1)
    connector = FabricEventstreamConnector(producer)

    # Act
    connector.publish_batch(
        [StubEvent("event-1", "station-01"), StubEvent("event-2", "station-01")]
    )

    # Assert
    assert [len(batch.events) for batch in producer.sent] == [1, 1]
    payloads = [json.loads(batch.events[0].body_as_str()) for batch in producer.sent]
    assert [payload["eventId"] for payload in payloads] == ["event-1", "event-2"]


def test_given_sdk_failure_when_publishing_then_error_is_unacknowledged_and_redacted() -> None:
    # Arrange
    producer = FakeProducer(send_error=RuntimeError(SECRET_CONNECTION))
    connector = FabricEventstreamConnector(producer)

    # Act and assert
    with pytest.raises(PublicationError) as error:
        connector.publish(StubEvent("event-1", "station-01"))
    assert SECRET_CONNECTION not in str(error.value)
    assert "private.servicebus.windows.net" not in str(error.value)


def test_given_connector_when_closed_twice_then_producer_closes_once(mocker) -> None:
    # Arrange
    producer = mocker.Mock(spec=FakeProducer)
    connector = FabricEventstreamConnector(producer)

    # Act
    connector.close()
    connector.close()

    # Assert
    producer.close.assert_called_once_with()

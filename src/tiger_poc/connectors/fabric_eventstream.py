"""Microsoft Fabric Eventstream connector using the Event Hubs-compatible SDK."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Protocol

from azure.eventhub import EventData, EventHubProducerClient

from tiger_poc.connectors.base import PublicationError, PublicationReceipt, SerializableEvent

REDACTED_DESTINATION = "fabric-eventstream://custom-endpoint"


class EventBatch(Protocol):
    """Describe the SDK batch surface needed by the connector."""

    def add(self, event_data: EventData) -> None:
        """Add one event or raise ValueError when the batch is full."""
        ...


class EventProducer(Protocol):
    """Describe the injected synchronous Event Hubs producer surface."""

    def create_batch(self, *, partition_key: str) -> EventBatch:
        """Create a size-bounded batch for one partition key."""
        ...

    def send_batch(self, event_data_batch: EventBatch) -> None:
        """Synchronously publish one completed batch."""
        ...

    def close(self) -> None:
        """Release producer resources."""
        ...


class FabricEventstreamConnector:
    """Publish canonical events with subject-based partition affinity."""

    def __init__(self, producer: EventProducer) -> None:
        """Use an injected producer to keep publication testable offline."""
        self._producer = producer
        self._closed = False

    @classmethod
    def from_connection_string(
        cls,
        connection_string: str,
        *,
        producer_factory: Callable[[str], EventProducer] | None = None,
    ) -> FabricEventstreamConnector:
        """Construct a local SAS-authenticated Eventstream producer."""
        try:
            factory = producer_factory or EventHubProducerClient.from_connection_string
            return cls(factory(connection_string))
        except Exception as error:
            raise PublicationError(
                f"failed to initialize producer for {REDACTED_DESTINATION}"
            ) from error

    @classmethod
    def from_entra(
        cls,
        fully_qualified_namespace: str,
        event_hub_name: str,
        *,
        credential_factory: Callable[[], object] | None = None,
        producer_factory: Callable[[str, str, object], EventProducer] | None = None,
    ) -> FabricEventstreamConnector:
        """Construct an Entra-authenticated producer for an identity-capable runtime."""
        try:
            if credential_factory is None:
                from azure.identity import DefaultAzureCredential

                credential_factory = DefaultAzureCredential
            credential = credential_factory()
            if producer_factory is None:
                producer = EventHubProducerClient(
                    fully_qualified_namespace=fully_qualified_namespace,
                    eventhub_name=event_hub_name,
                    credential=credential,
                )
            else:
                producer = producer_factory(
                    fully_qualified_namespace,
                    event_hub_name,
                    credential,
                )
            return cls(producer)
        except Exception as error:
            raise PublicationError(
                f"failed to initialize producer for {REDACTED_DESTINATION}"
            ) from error

    @property
    def destination(self) -> str:
        """Return a diagnostic identifier that exposes no endpoint details."""
        return REDACTED_DESTINATION

    def publish(self, event: SerializableEvent) -> PublicationReceipt:
        """Publish one canonical event and acknowledge synchronous SDK acceptance."""
        self.publish_batch([event])
        return PublicationReceipt(destination=self.destination)

    def publish_batch(self, events: Iterable[SerializableEvent]) -> list[PublicationReceipt]:
        """Publish size-bounded batches grouped by subject partition key."""
        if self._closed:
            raise PublicationError(f"connector is closed: {self.destination}")

        grouped: dict[str, list[SerializableEvent]] = defaultdict(list)
        for event in events:
            payload = event.to_dict()
            subject_id = payload.get("subjectId")
            if not isinstance(subject_id, str) or not subject_id:
                raise PublicationError("canonical event requires a non-empty subjectId")
            grouped[subject_id].append(event)

        acknowledged = 0
        try:
            for subject_id, subject_events in grouped.items():
                batch = self._producer.create_batch(partition_key=subject_id)
                batch_count = 0
                for event in subject_events:
                    event_data = EventData(
                        __import__("json").dumps(
                            event.to_dict(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    )
                    try:
                        batch.add(event_data)
                    except ValueError:
                        if batch_count == 0:
                            raise PublicationError("canonical event exceeds the SDK batch limit")
                        self._producer.send_batch(batch)
                        acknowledged += batch_count
                        batch = self._producer.create_batch(partition_key=subject_id)
                        batch.add(event_data)
                        batch_count = 0
                    batch_count += 1
                if batch_count:
                    self._producer.send_batch(batch)
                    acknowledged += batch_count
        except PublicationError:
            raise
        except Exception as error:
            raise PublicationError(f"publication failed for {self.destination}") from error

        return [PublicationReceipt(destination=self.destination) for _ in range(acknowledged)]

    def close(self) -> None:
        """Close the producer; repeated calls have no effect."""
        if not self._closed:
            self._producer.close()
            self._closed = True


__all__ = ["FabricEventstreamConnector"]

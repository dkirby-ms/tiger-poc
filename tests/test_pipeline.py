"""Deterministic local composition tests across edge and cloud inference modes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from scripts.run_pipeline import FixtureFrame, build_connector, run_pipeline
from tiger_poc.config import PipelineConfig
from tiger_poc.connectors import LocalSinkConnector, PublicationError, PublicationReceipt
from tiger_poc.delivery import OutboxPublisher, OverflowPolicy, SQLiteMapperStateStore
from tiger_poc.ontology.event import ProcessEvent

BASE_TIME = datetime(2026, 9, 14, 19, 20, 30, 123000, tzinfo=UTC)
EVENT_ID = UUID("f7a58ddf-67f0-48e9-a62f-641a1db6119d")


class RecordingConnector:
    """Record accepted events and optionally simulate a disconnect."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[ProcessEvent] = []
        self.closed = False

    @property
    def destination(self) -> str:
        """Return a stable offline destination."""
        return "recording://offline"

    def publish(self, event: ProcessEvent) -> PublicationReceipt:
        """Record an event or raise an unacknowledged failure."""
        if self.fail:
            raise PublicationError("simulated disconnect")
        self.events.append(event)
        return PublicationReceipt(destination=self.destination)

    def close(self) -> None:
        """Record shutdown."""
        self.closed = True


def make_config(path: Path, *, mode: str, runtime: str) -> PipelineConfig:
    """Create one validated local composition configuration."""
    return PipelineConfig.model_validate(
        {
            "schemaVersion": 1,
            "source": {
                "kind": "fixture",
                "path": "unused.json",
                "siteId": "factory-01",
                "deviceId": "camera-01",
                "subjectId": "station-01",
            },
            "inference": {"mode": mode, "runtime": runtime, "model": "line-monitor-v1"},
            "ontology": {
                "version": "1.0",
                "mapper": "line-monitoring",
                "confidenceThreshold": 0.8,
                "consecutiveReadings": 2,
            },
            "destination": {"kind": "local-jsonl", "path": str(path)},
        }
    )


def make_frames() -> list[FixtureFrame]:
    """Return the two readings required to confirm a blocked transition."""
    return [
        FixtureFrame(state="blocked", observed_at=BASE_TIME, confidence=0.94),
        FixtureFrame(
            state="blocked",
            observed_at=BASE_TIME + timedelta(seconds=1),
            confidence=0.95,
        ),
    ]


def make_store(
    path: Path,
    *,
    clock=lambda: BASE_TIME,
) -> SQLiteMapperStateStore:
    """Create a durable store with deterministic Phase 3 bounds."""
    return SQLiteMapperStateStore(
        path,
        max_bytes=100_000,
        max_age=timedelta(hours=1),
        overflow_policy=OverflowPolicy.REJECT,
        clock=clock,
    )


def payload_shape(value: object) -> object:
    """Return nested payload keys and value types without comparing values."""
    if isinstance(value, dict):
        return {key: payload_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [payload_shape(item) for item in value]
    return type(value)


def test_given_local_config_when_running_then_publishes_one_canonical_event(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "events.jsonl"
    config = make_config(output_path, mode="edge", runtime="foundry-local")

    # Act
    events = run_pipeline(
        config,
        make_frames(),
        clock=lambda: BASE_TIME + timedelta(seconds=2),
        event_id_factory=lambda: EVENT_ID,
    )

    # Assert
    assert len(events) == 1
    assert output_path.read_text(encoding="utf-8") == f"{events[0].to_json()}\n"


def test_given_edge_and_cloud_modes_when_running_then_connector_and_shape_are_invariant(
    tmp_path: Path,
) -> None:
    # Arrange
    edge_config = make_config(tmp_path / "edge.jsonl", mode="edge", runtime="foundry-local")
    cloud_config = make_config(tmp_path / "cloud.jsonl", mode="cloud", runtime="foundry-cloud")
    edge_store = make_store(tmp_path / "edge.db")
    cloud_store = make_store(tmp_path / "cloud.db")
    edge_connector = build_connector(edge_config)
    cloud_connector = build_connector(cloud_config)
    edge_publisher = OutboxPublisher(edge_store.outbox, edge_connector, owner="edge")
    cloud_publisher = OutboxPublisher(cloud_store.outbox, cloud_connector, owner="cloud")

    # Act
    edge_events = run_pipeline(
        edge_config,
        make_frames(),
        connector=edge_publisher,
        state_store=edge_store,
        clock=lambda: BASE_TIME + timedelta(seconds=2),
        event_id_factory=lambda: EVENT_ID,
    )
    cloud_events = run_pipeline(
        cloud_config,
        make_frames(),
        connector=cloud_publisher,
        state_store=cloud_store,
        clock=lambda: BASE_TIME + timedelta(seconds=2),
        event_id_factory=lambda: EVENT_ID,
    )

    # Assert
    assert type(edge_connector) is type(cloud_connector) is LocalSinkConnector
    assert type(edge_publisher) is type(cloud_publisher) is OutboxPublisher
    assert edge_store.outbox.metrics().queued_events == 0
    assert cloud_store.outbox.metrics().queued_events == 0
    edge_payload = edge_events[0].to_dict()
    cloud_payload = cloud_events[0].to_dict()
    assert edge_payload["schemaVersion"] == cloud_payload["schemaVersion"] == "1.0"
    assert edge_payload["source"] != cloud_payload["source"]
    assert payload_shape(edge_payload) == payload_shape(cloud_payload)
    edge_publisher.close()
    cloud_publisher.close()
    edge_store.close()
    cloud_store.close()


def test_given_disconnect_when_restarted_then_original_event_is_replayed_and_acknowledged(
    tmp_path: Path,
) -> None:
    # Arrange
    database = tmp_path / "outbox.db"
    config = make_config(tmp_path / "unused.jsonl", mode="edge", runtime="foundry-local")
    first_store = make_store(database)
    disconnected = RecordingConnector(fail=True)
    first_publisher = OutboxPublisher(first_store.outbox, disconnected, owner="first")

    # Act and assert
    with pytest.raises(PublicationError, match="simulated disconnect"):
        run_pipeline(
            config,
            make_frames(),
            connector=first_publisher,
            state_store=first_store,
            clock=lambda: BASE_TIME + timedelta(seconds=2),
            event_id_factory=lambda: EVENT_ID,
        )
    assert first_store.outbox.contains(str(EVENT_ID)) is True
    first_store.close()

    restarted_store = make_store(database)
    connected = RecordingConnector()
    restarted_publisher = OutboxPublisher(restarted_store.outbox, connected, owner="second")
    run_pipeline(config, [], connector=restarted_publisher, state_store=restarted_store)

    assert [event.event_id for event in connected.events] == [EVENT_ID]
    assert restarted_store.outbox.metrics().queued_events == 0
    restarted_store.close()


def test_given_remote_acceptance_without_local_ack_when_restarted_then_identity_is_unchanged(
    tmp_path: Path,
) -> None:
    # Arrange
    database = tmp_path / "outbox.db"
    config = make_config(tmp_path / "unused.jsonl", mode="edge", runtime="foundry-local")
    store = make_store(database)
    disconnected = RecordingConnector(fail=True)
    with pytest.raises(PublicationError):
        run_pipeline(
            config,
            make_frames(),
            connector=OutboxPublisher(store.outbox, disconnected, owner="initial"),
            state_store=store,
            clock=lambda: BASE_TIME + timedelta(seconds=2),
            event_id_factory=lambda: EVENT_ID,
        )
    first_remote = RecordingConnector()
    record = store.outbox.lease(owner="crashed")[0]
    first_remote.publish(record.event())
    store.close()

    # Act
    restarted_store = make_store(database, clock=lambda: BASE_TIME + timedelta(seconds=31))
    second_remote = RecordingConnector()
    restarted_publisher = OutboxPublisher(restarted_store.outbox, second_remote, owner="second")
    restarted_publisher.drain()

    # Assert
    assert [event.event_id for event in first_remote.events + second_remote.events] == [
        EVENT_ID,
        EVENT_ID,
    ]
    restarted_store.close()


def test_given_backlog_and_live_transition_when_running_then_subject_order_is_preserved(
    tmp_path: Path,
) -> None:
    # Arrange
    database = tmp_path / "outbox.db"
    config = make_config(tmp_path / "unused.jsonl", mode="edge", runtime="foundry-local")
    store = make_store(database)
    disconnected = RecordingConnector(fail=True)
    with pytest.raises(PublicationError):
        run_pipeline(
            config,
            make_frames(),
            connector=OutboxPublisher(store.outbox, disconnected, owner="first"),
            state_store=store,
            clock=lambda: BASE_TIME + timedelta(seconds=2),
            event_id_factory=lambda: EVENT_ID,
        )
    live_frames = [
        FixtureFrame("clear", BASE_TIME + timedelta(seconds=3), 0.95),
        FixtureFrame("clear", BASE_TIME + timedelta(seconds=4), 0.95),
    ]
    connected = RecordingConnector()

    # Act
    run_pipeline(
        config,
        live_frames,
        connector=OutboxPublisher(store.outbox, connected, owner="second"),
        state_store=store,
        clock=lambda: BASE_TIME + timedelta(seconds=5),
        event_id_factory=lambda: UUID("db2a1ddc-1d5e-4e41-81b4-e6ad68994948"),
    )

    # Assert
    assert [event.sequence for event in connected.events] == [1, 2]
    store.close()

"""Offline behavior tests for the bounded SQLite delivery store."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from tiger_poc.delivery.outbox import (
    OutboxCorruptionError,
    OutboxFullError,
    OverflowPolicy,
)
from tiger_poc.delivery.sqlite_state import SQLiteMapperStateStore
from tiger_poc.ontology.event import EventSource, ProcessEvent, ProcessStateValue
from tiger_poc.ontology.state import MapperState, MappingProposal

BASE_TIME = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def make_event(*, sequence: int = 1, subject_id: str = "station-01") -> ProcessEvent:
    """Create one deterministic canonical event."""
    return ProcessEvent(
        eventId=uuid5(NAMESPACE_URL, f"{subject_id}:{sequence}"),
        subjectId=subject_id,
        siteId="factory-01",
        deviceId="camera-01",
        ontologyVersion="1.0",
        sequence=sequence,
        observedAt=BASE_TIME + timedelta(seconds=sequence),
        emittedAt=BASE_TIME + timedelta(seconds=sequence + 1),
        value=ProcessStateValue(state="blocked"),
        confidence=0.95,
        source=EventSource(runtime="fixture", model="line-monitor-v1"),
    )


def make_store(
    path: Path,
    *,
    max_bytes: int = 100_000,
    max_age: timedelta = timedelta(hours=1),
    overflow_policy: OverflowPolicy = OverflowPolicy.REJECT,
    clock=lambda: BASE_TIME,
) -> SQLiteMapperStateStore:
    """Create a deterministic SQLite mapper state store."""
    return SQLiteMapperStateStore(
        path,
        max_bytes=max_bytes,
        max_age=max_age,
        overflow_policy=overflow_policy,
        clock=clock,
    )


def make_proposal(event: ProcessEvent) -> MappingProposal:
    """Create a state transition matching one event."""
    previous = MapperState(subject_id=event.subject_id, sequence=event.sequence - 1)
    next_state = MapperState(subject_id=event.subject_id, sequence=event.sequence)
    return MappingProposal(previous_state=previous, next_state=next_state, event=event)


def test_given_committed_event_when_restarted_then_identity_and_sequence_are_preserved(
    tmp_path: Path,
) -> None:
    # Arrange
    database = tmp_path / "outbox.db"
    event = make_event()
    store = make_store(database)
    store.commit(make_proposal(event))
    store.close()

    # Act
    restarted = make_store(database)
    record = restarted.outbox.lease(owner="restart")[0]

    # Assert
    assert (record.event_id, record.subject_id, record.sequence) == (
        str(event.event_id),
        event.subject_id,
        event.sequence,
    )
    assert record.event().to_json() == event.to_json()
    restarted.close()


def test_given_full_outbox_when_atomic_commit_fails_then_state_does_not_advance(
    tmp_path: Path,
) -> None:
    # Arrange
    store = make_store(tmp_path / "outbox.db", max_bytes=1)
    proposal = make_proposal(make_event())

    # Act and assert
    with pytest.raises(OutboxFullError):
        store.commit(proposal)
    assert store.load("station-01").sequence == 0
    store.close()


def test_given_queued_sequence_above_state_when_restarted_then_corruption_is_rejected(
    tmp_path: Path,
) -> None:
    # Arrange
    database = tmp_path / "outbox.db"
    store = make_store(database)
    store.commit(make_proposal(make_event()))
    store.close()
    connection = sqlite3.connect(database)
    connection.execute("UPDATE mapper_states SET sequence = 0 WHERE subject_id = 'station-01'")
    connection.commit()
    connection.close()

    # Act and assert
    with pytest.raises(OutboxCorruptionError, match="high-water mark"):
        make_store(database)


def test_given_failed_publication_when_retried_then_payload_is_unchanged(tmp_path: Path) -> None:
    # Arrange
    event = make_event()
    store = make_store(tmp_path / "outbox.db")
    store.commit(make_proposal(event))
    first = store.outbox.lease(owner="publisher")[0]

    # Act
    store.outbox.retry(first.event_id, owner="publisher")
    second = store.outbox.lease(owner="publisher")[0]

    # Assert
    assert second.payload == first.payload
    assert second.retry_count == 1
    store.close()


def test_given_two_subject_sequences_when_leasing_then_each_subject_stays_ordered(
    tmp_path: Path,
) -> None:
    # Arrange
    store = make_store(tmp_path / "outbox.db")
    for subject_id in ("station-01", "station-02"):
        store.commit(make_proposal(make_event(subject_id=subject_id)))
        store.commit(make_proposal(make_event(sequence=2, subject_id=subject_id)))

    # Act
    first_records = store.outbox.lease(owner="publisher", limit=4)

    # Assert
    assert {(record.subject_id, record.sequence) for record in first_records} == {
        ("station-01", 1),
        ("station-02", 1),
    }
    store.close()


def test_given_expired_lease_when_leasing_then_another_owner_can_recover_it(tmp_path: Path) -> None:
    # Arrange
    now = BASE_TIME
    store = make_store(tmp_path / "outbox.db", clock=lambda: now)
    store.commit(make_proposal(make_event()))
    store.outbox.lease(owner="first", lease_duration=timedelta(seconds=1))
    now += timedelta(seconds=2)

    # Act
    recovered = store.outbox.lease(owner="second")

    # Assert
    assert recovered[0].lease_owner == "second"
    store.close()


def test_given_expired_event_when_metrics_read_then_event_is_removed_and_counted(
    tmp_path: Path,
) -> None:
    # Arrange
    now = BASE_TIME
    store = make_store(tmp_path / "outbox.db", max_age=timedelta(seconds=1), clock=lambda: now)
    store.commit(make_proposal(make_event()))
    now += timedelta(seconds=2)

    # Act
    metrics = store.outbox.metrics()

    # Assert
    assert (metrics.queued_events, metrics.expired_events) == (0, 1)
    store.close()


def test_given_drop_oldest_policy_when_bound_reached_then_loss_is_observable(
    tmp_path: Path,
) -> None:
    # Arrange
    first = make_event()
    second = make_event(subject_id="station-02")
    max_bytes = len(first.to_json().encode("utf-8")) + 1
    store = make_store(
        tmp_path / "outbox.db",
        max_bytes=max_bytes,
        overflow_policy=OverflowPolicy.DROP_OLDEST,
    )
    store.commit(make_proposal(first))

    # Act
    store.commit(make_proposal(second))
    metrics = store.outbox.metrics()

    # Assert
    assert metrics.dropped_events == 1
    assert store.outbox.contains(str(first.event_id)) is False
    assert store.outbox.contains(str(second.event_id)) is True
    store.close()

"""Behavior tests for subject-keyed process-state mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from tiger_poc.ontology.event import ProcessState
from tiger_poc.ontology.mapper import ProcessStateMapper
from tiger_poc.ontology.state import InMemoryMapperStateStore, MapperState
from tiger_poc.perception import Observation

BASE_TIME = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def make_observation(
    subject_id: str,
    *,
    state: str = "blocked",
    offset_seconds: int = 0,
    runtime: str = "foundry-local",
    confidence: float = 0.95,
) -> Observation:
    """Create one deterministic process-state observation."""
    return Observation(
        subject_id=subject_id,
        observation_type="process-state",
        value=state,
        timestamp=BASE_TIME + timedelta(seconds=offset_seconds),
        confidence=confidence,
        source=runtime,
    )


def make_mapper(*, consecutive_readings: int = 2) -> ProcessStateMapper:
    """Create the canonical line-monitoring mapper."""
    return ProcessStateMapper(
        site_id="factory-01",
        device_id="camera-01",
        ontology_version="1.0",
        model="line-monitor-v1",
        consecutive_readings=consecutive_readings,
    )


def test_given_interleaved_subjects_when_mapping_then_debounce_state_is_independent() -> None:
    # Arrange
    mapper = make_mapper()
    store = InMemoryMapperStateStore()
    observations = [
        make_observation("station-01"),
        make_observation("station-02"),
        make_observation("station-01", offset_seconds=1),
        make_observation("station-02", offset_seconds=1),
    ]

    # Act
    events = []
    for observation in observations:
        proposal = mapper.map(observation, store.load(observation.subject_id))
        store.commit(proposal)
        if proposal.event is not None:
            events.append(proposal.event)

    # Assert
    assert [(event.subject_id, event.sequence) for event in events] == [
        ("station-01", 1),
        ("station-02", 1),
    ]


def test_given_restored_pending_state_when_mapping_then_debounce_and_sequence_continue() -> None:
    # Arrange
    mapper = make_mapper()
    restored = MapperState(
        subject_id="station-01",
        current_state=ProcessState.CLEAR,
        candidate_state=ProcessState.BLOCKED,
        candidate_count=1,
        last_observed_at=BASE_TIME,
        sequence=7,
    )

    # Act
    proposal = mapper.map(
        make_observation("station-01", offset_seconds=1),
        restored,
        emitted_at=BASE_TIME + timedelta(seconds=2),
        event_id=UUID("f7a58ddf-67f0-48e9-a62f-641a1db6119d"),
    )

    # Assert
    assert proposal.event is not None
    assert proposal.event.sequence == 8
    assert proposal.next_state.current_state == ProcessState.BLOCKED


def test_given_stale_or_duplicate_observation_when_mapping_then_no_transition_is_proposed() -> None:
    # Arrange
    mapper = make_mapper(consecutive_readings=1)
    state = MapperState(subject_id="station-01", last_observed_at=BASE_TIME, sequence=4)

    # Act
    proposal = mapper.map(make_observation("station-01"), state)

    # Assert
    assert proposal.accepted is False
    assert proposal.event is None
    assert proposal.next_state is state


def test_given_edge_and_cloud_observations_when_mapping_then_only_source_metadata_differs() -> None:
    # Arrange
    mapper = make_mapper(consecutive_readings=1)
    event_id = UUID("f7a58ddf-67f0-48e9-a62f-641a1db6119d")
    emitted_at = BASE_TIME + timedelta(seconds=1)

    # Act
    edge = mapper.map(
        make_observation("station-01", runtime="foundry-local"),
        MapperState(subject_id="station-01"),
        emitted_at=emitted_at,
        event_id=event_id,
    ).event
    cloud = mapper.map(
        make_observation("station-01", runtime="foundry-cloud"),
        MapperState(subject_id="station-01"),
        emitted_at=emitted_at,
        event_id=event_id,
    ).event

    # Assert
    assert edge is not None and cloud is not None
    edge_payload = edge.to_dict()
    cloud_payload = cloud.to_dict()
    edge_payload.pop("source")
    cloud_payload.pop("source")
    assert edge_payload == cloud_payload

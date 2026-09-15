"""Subject-keyed mapping from observations to canonical process events."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from tiger_poc.ontology.event import EventSource, ProcessEvent, ProcessState, ProcessStateValue
from tiger_poc.ontology.state import MapperState, MappingProposal
from tiger_poc.perception.observation import Observation


class ProcessStateMapper:
    """Debounce process observations without mutating durable mapper state."""

    def __init__(
        self,
        *,
        site_id: str,
        device_id: str,
        ontology_version: str,
        model: str,
        confidence_threshold: float = 0.8,
        consecutive_readings: int = 2,
    ) -> None:
        """Configure stable event identity and debounce policy."""
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        if consecutive_readings < 1:
            raise ValueError("consecutive_readings must be at least 1")
        self._site_id = site_id
        self._device_id = device_id
        self._ontology_version = ontology_version
        self._model = model
        self._confidence_threshold = confidence_threshold
        self._consecutive_readings = consecutive_readings

    def map(
        self,
        observation: Observation,
        state: MapperState,
        *,
        emitted_at: datetime | None = None,
        event_id: UUID | None = None,
    ) -> MappingProposal:
        """Propose the next subject state and an optional transition event."""
        if observation.subject_id != state.subject_id:
            raise ValueError("observation subject_id does not match mapper state")
        if state.last_observed_at is not None and observation.timestamp <= state.last_observed_at:
            return MappingProposal(
                previous_state=state,
                next_state=state,
                accepted=False,
            )

        observed_state = self._parse_state(observation)
        if observation.confidence < self._confidence_threshold or observed_state is None:
            next_state = replace(
                state,
                candidate_state=None,
                candidate_count=0,
                last_observed_at=observation.timestamp,
            )
            return MappingProposal(previous_state=state, next_state=next_state)

        candidate_count = (
            state.candidate_count + 1 if state.candidate_state == observed_state else 1
        )
        next_state = replace(
            state,
            candidate_state=observed_state,
            candidate_count=candidate_count,
            last_observed_at=observation.timestamp,
        )
        if observed_state == state.current_state or candidate_count < self._consecutive_readings:
            return MappingProposal(previous_state=state, next_state=next_state)

        sequence = state.sequence + 1
        committed_state = replace(
            next_state,
            current_state=observed_state,
            candidate_state=None,
            candidate_count=0,
            sequence=sequence,
        )
        event = ProcessEvent(
            eventId=event_id or uuid4(),
            subjectId=observation.subject_id,
            siteId=self._site_id,
            deviceId=self._device_id,
            ontologyVersion=self._ontology_version,
            sequence=sequence,
            observedAt=observation.timestamp,
            emittedAt=emitted_at or datetime.now(UTC),
            value=ProcessStateValue(state=observed_state),
            confidence=observation.confidence,
            source=EventSource(runtime=observation.source, model=self._model),
        )
        return MappingProposal(previous_state=state, next_state=committed_state, event=event)

    @staticmethod
    def _parse_state(observation: Observation) -> ProcessState | None:
        if observation.observation_type != "process-state" or not isinstance(
            observation.value, str
        ):
            return None
        try:
            return ProcessState(observation.value)
        except ValueError:
            return None


__all__ = ["ProcessStateMapper"]

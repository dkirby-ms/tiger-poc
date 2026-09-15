"""Immutable mapper state and atomic persistence boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from tiger_poc.ontology.event import ProcessEvent, ProcessState


@dataclass(frozen=True, slots=True)
class MapperState:
    """Capture durable debounce and sequence state for one subject."""

    subject_id: str
    current_state: ProcessState | None = None
    candidate_state: ProcessState | None = None
    candidate_count: int = 0
    last_observed_at: datetime | None = None
    sequence: int = 0


@dataclass(frozen=True, slots=True)
class MappingProposal:
    """Describe a mapper result that has not yet mutated durable state."""

    previous_state: MapperState
    next_state: MapperState
    event: ProcessEvent | None = None
    accepted: bool = True


@runtime_checkable
class MapperStateStore(Protocol):
    """Load state and atomically commit mapper state with any emitted event."""

    def load(self, subject_id: str) -> MapperState:
        """Load durable state or return a new state record for the subject."""
        ...

    def commit(self, proposal: MappingProposal) -> None:
        """Atomically persist next state and enqueue its event when present."""
        ...


class InMemoryMapperStateStore:
    """Provide deterministic non-durable state for local composition tests."""

    def __init__(self) -> None:
        self._states: dict[str, MapperState] = {}

    def load(self, subject_id: str) -> MapperState:
        """Return the latest committed state for one subject."""
        return self._states.get(subject_id, MapperState(subject_id=subject_id))

    def commit(self, proposal: MappingProposal) -> None:
        """Commit one proposal after verifying its subject boundary."""
        if proposal.previous_state.subject_id != proposal.next_state.subject_id:
            raise ValueError("mapping proposal cannot change subject_id")
        self._states[proposal.next_state.subject_id] = proposal.next_state


__all__ = [
    "InMemoryMapperStateStore",
    "MapperState",
    "MapperStateStore",
    "MappingProposal",
]

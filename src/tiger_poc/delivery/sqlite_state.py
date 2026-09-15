"""SQLite mapper state and atomic state/event unit of work."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tiger_poc.delivery.outbox import OutboxCorruptionError, OverflowPolicy, SQLiteOutbox
from tiger_poc.ontology.event import ProcessState
from tiger_poc.ontology.state import MapperState, MappingProposal


class ConcurrentStateError(RuntimeError):
    """Report an attempt to commit a stale mapping proposal."""


class SQLiteMapperStateStore:
    """Persist mapper state and emitted events in one SQLite transaction."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int,
        max_age: timedelta,
        overflow_policy: OverflowPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Open the database, configure WAL durability, and reconcile state."""
        database_path = Path(path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema()
        self.outbox = SQLiteOutbox(
            self._connection,
            max_bytes=max_bytes,
            max_age=max_age,
            overflow_policy=overflow_policy,
            clock=clock,
        )
        self._reconcile()

    def load(self, subject_id: str) -> MapperState:
        """Load durable state or return an initial state for the subject."""
        row = self._connection.execute(
            """
            SELECT subject_id, current_state, candidate_state, candidate_count,
                   last_observed_at, sequence
            FROM mapper_states
            WHERE subject_id = ?
            """,
            (subject_id,),
        ).fetchone()
        if row is None:
            return MapperState(subject_id=subject_id)
        return self._state(row)

    def commit(self, proposal: MappingProposal) -> None:
        """Atomically compare-and-set mapper state and enqueue its event."""
        if proposal.previous_state.subject_id != proposal.next_state.subject_id:
            raise ValueError("mapping proposal cannot change subject_id")
        if proposal.event is not None:
            if proposal.event.subject_id != proposal.next_state.subject_id:
                raise ValueError("event subject_id does not match mapper state")
            if proposal.event.sequence != proposal.next_state.sequence:
                raise ValueError("event sequence does not match mapper state")

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            current = self.load(proposal.previous_state.subject_id)
            if current != proposal.previous_state:
                raise ConcurrentStateError(
                    f"stale mapper state for subject: {proposal.previous_state.subject_id}"
                )
            self._connection.execute(
                """
                INSERT INTO mapper_states (
                    subject_id, current_state, candidate_state, candidate_count,
                    last_observed_at, sequence
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject_id) DO UPDATE SET
                    current_state = excluded.current_state,
                    candidate_state = excluded.candidate_state,
                    candidate_count = excluded.candidate_count,
                    last_observed_at = excluded.last_observed_at,
                    sequence = excluded.sequence
                """,
                self._state_values(proposal.next_state),
            )
            if proposal.event is not None:
                self.outbox._enqueue_in_transaction(proposal.event)
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def close(self) -> None:
        """Close the SQLite database; repeated calls have no effect."""
        self._connection.close()

    def _initialize_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mapper_states (
                subject_id TEXT PRIMARY KEY,
                current_state TEXT,
                candidate_state TEXT,
                candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
                last_observed_at TEXT,
                sequence INTEGER NOT NULL CHECK (sequence >= 0)
            )
            """
        )

    def _reconcile(self) -> None:
        rows = self._connection.execute(
            """
            SELECT queued.subject_id, MAX(queued.sequence), states.sequence
            FROM outbox_events AS queued
            LEFT JOIN mapper_states AS states ON states.subject_id = queued.subject_id
            GROUP BY queued.subject_id
            """
        ).fetchall()
        for subject_id, queued_sequence, state_sequence in rows:
            if state_sequence is None or int(queued_sequence) > int(state_sequence):
                raise OutboxCorruptionError(
                    "queued event sequence exceeds mapper high-water mark for "
                    f"subject: {subject_id}"
                )

    @staticmethod
    def _state(row: tuple[object, ...]) -> MapperState:
        return MapperState(
            subject_id=str(row[0]),
            current_state=None if row[1] is None else ProcessState(str(row[1])),
            candidate_state=None if row[2] is None else ProcessState(str(row[2])),
            candidate_count=int(row[3]),
            last_observed_at=(None if row[4] is None else datetime.fromisoformat(str(row[4]))),
            sequence=int(row[5]),
        )

    @staticmethod
    def _state_values(state: MapperState) -> tuple[object, ...]:
        return (
            state.subject_id,
            None if state.current_state is None else state.current_state.value,
            None if state.candidate_state is None else state.candidate_state.value,
            state.candidate_count,
            None if state.last_observed_at is None else state.last_observed_at.isoformat(),
            state.sequence,
        )


__all__ = ["ConcurrentStateError", "SQLiteMapperStateStore"]

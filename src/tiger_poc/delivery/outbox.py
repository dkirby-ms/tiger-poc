"""Bounded SQLite outbox with leases, retries, and restart-safe replay."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from tiger_poc.connectors.base import PublicationError, PublicationReceipt, TwinConnector
from tiger_poc.ontology.event import ProcessEvent


class OutboxError(RuntimeError):
    """Base class for durable outbox failures."""


class OutboxFullError(OutboxError):
    """Report that the configured loss policy rejected an event."""


class OutboxCorruptionError(OutboxError):
    """Report inconsistent durable state or event metadata."""


class OverflowPolicy(StrEnum):
    """Define deterministic behavior when the byte bound is reached."""

    REJECT = "reject"
    DROP_OLDEST = "drop-oldest"


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    """Represent one leased or pending canonical event."""

    event_id: str
    subject_id: str
    sequence: int
    payload: str
    payload_size: int
    retry_count: int
    next_attempt_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    created_at: datetime

    def event(self) -> ProcessEvent:
        """Restore the frozen canonical event from its durable payload."""
        return ProcessEvent.model_validate_json(self.payload)


@dataclass(frozen=True, slots=True)
class OutboxMetrics:
    """Expose queue pressure and cumulative loss counters."""

    queued_events: int
    queued_bytes: int
    oldest_age_seconds: float
    retry_count: int
    dropped_events: int
    expired_events: int


class SQLiteOutbox:
    """Persist canonical events in a bounded SQLite queue."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        max_bytes: int,
        max_age: timedelta,
        overflow_policy: OverflowPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Configure queue bounds on an existing shared SQLite connection."""
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        self._connection = connection
        self._max_bytes = max_bytes
        self._max_age = max_age
        self._overflow_policy = overflow_policy
        self._clock = clock
        self._initialize_schema()

    def enqueue(self, event: ProcessEvent) -> None:
        """Persist one event in its own transaction."""
        with self._transaction():
            self._enqueue_in_transaction(event)

    def lease(
        self,
        *,
        owner: str,
        limit: int = 1,
        lease_duration: timedelta = timedelta(seconds=30),
    ) -> list[OutboxRecord]:
        """Lease ready rows while preserving ordering within each subject."""
        if not owner:
            raise ValueError("lease owner must not be empty")
        if limit < 1:
            raise ValueError("lease limit must be at least 1")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")

        now = self._now()
        with self._transaction():
            self._expire_in_transaction(now)
            rows = self._connection.execute(
                """
                SELECT event_id
                FROM outbox_events AS candidate
                WHERE candidate.next_attempt_at <= ?
                  AND (candidate.lease_owner IS NULL OR candidate.lease_expires_at <= ?)
                  AND NOT EXISTS (
                      SELECT 1
                      FROM outbox_events AS earlier
                      WHERE earlier.subject_id = candidate.subject_id
                        AND earlier.sequence < candidate.sequence
                  )
                ORDER BY candidate.created_at, candidate.subject_id, candidate.sequence
                LIMIT ?
                """,
                (now.timestamp(), now.timestamp(), limit),
            ).fetchall()
            event_ids = [str(row[0]) for row in rows]
            if not event_ids:
                return []
            placeholders = ",".join("?" for _ in event_ids)
            self._connection.execute(
                f"""
                UPDATE outbox_events
                SET lease_owner = ?, lease_expires_at = ?
                WHERE event_id IN ({placeholders})
                """,  # noqa: S608 - placeholders are generated, not user-controlled.
                (owner, (now + lease_duration).timestamp(), *event_ids),
            )
            leased_rows = self._connection.execute(
                f"""
                SELECT event_id, subject_id, sequence, payload, payload_size,
                       retry_count, next_attempt_at, lease_owner, lease_expires_at, created_at
                FROM outbox_events
                WHERE event_id IN ({placeholders})
                ORDER BY created_at, subject_id, sequence
                """,  # noqa: S608 - placeholders are generated, not user-controlled.
                event_ids,
            ).fetchall()
        return [self._record(row) for row in leased_rows]

    def acknowledge(self, event_id: str, *, owner: str) -> None:
        """Delete one row only when it is held by the acknowledging owner."""
        with self._transaction():
            cursor = self._connection.execute(
                "DELETE FROM outbox_events WHERE event_id = ? AND lease_owner = ?",
                (event_id, owner),
            )
            if cursor.rowcount != 1:
                raise OutboxError(f"event is not leased by owner: {event_id}")

    def retry(
        self,
        event_id: str,
        *,
        owner: str,
        delay: timedelta = timedelta(0),
    ) -> None:
        """Return a leased row to the queue without changing its payload."""
        if delay < timedelta(0):
            raise ValueError("retry delay cannot be negative")
        next_attempt = self._now() + delay
        with self._transaction():
            cursor = self._connection.execute(
                """
                UPDATE outbox_events
                SET retry_count = retry_count + 1,
                    next_attempt_at = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL
                WHERE event_id = ? AND lease_owner = ?
                """,
                (next_attempt.timestamp(), event_id, owner),
            )
            if cursor.rowcount != 1:
                raise OutboxError(f"event is not leased by owner: {event_id}")

    def contains(self, event_id: str) -> bool:
        """Return whether an event remains unacknowledged."""
        row = self._connection.execute(
            "SELECT 1 FROM outbox_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def metrics(self) -> OutboxMetrics:
        """Return current queue pressure and cumulative retry/loss metrics."""
        now = self._now()
        with self._transaction():
            self._expire_in_transaction(now)
            queued = self._connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(payload_size), 0), MIN(created_at),
                       COALESCE(SUM(retry_count), 0)
                FROM outbox_events
                """
            ).fetchone()
            counters = dict(
                self._connection.execute("SELECT name, value FROM outbox_counters").fetchall()
            )
        oldest_age = 0.0 if queued[2] is None else max(0.0, now.timestamp() - float(queued[2]))
        return OutboxMetrics(
            queued_events=int(queued[0]),
            queued_bytes=int(queued[1]),
            oldest_age_seconds=oldest_age,
            retry_count=int(queued[3]),
            dropped_events=int(counters.get("dropped_events", 0)),
            expired_events=int(counters.get("expired_events", 0)),
        )

    def _enqueue_in_transaction(self, event: ProcessEvent) -> None:
        now = self._now()
        self._expire_in_transaction(now)
        payload = event.to_json()
        payload_size = len(payload.encode("utf-8"))
        if payload_size > self._max_bytes:
            raise OutboxFullError(
                f"event payload requires {payload_size} bytes; outbox limit is {self._max_bytes}"
            )
        queued_bytes = int(
            self._connection.execute(
                "SELECT COALESCE(SUM(payload_size), 0) FROM outbox_events"
            ).fetchone()[0]
        )
        while queued_bytes + payload_size > self._max_bytes:
            if self._overflow_policy is OverflowPolicy.REJECT:
                raise OutboxFullError(
                    f"outbox byte limit would be exceeded: {queued_bytes + payload_size}"
                )
            oldest = self._connection.execute(
                "SELECT event_id, payload_size FROM outbox_events ORDER BY created_at LIMIT 1"
            ).fetchone()
            if oldest is None:
                raise OutboxFullError("outbox cannot make room for event")
            self._connection.execute("DELETE FROM outbox_events WHERE event_id = ?", (oldest[0],))
            self._increment_counter("dropped_events")
            queued_bytes -= int(oldest[1])

        try:
            self._connection.execute(
                """
                INSERT INTO outbox_events (
                    event_id, subject_id, sequence, payload, payload_size,
                    retry_count, next_attempt_at, lease_owner, lease_expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?)
                """,
                (
                    str(event.event_id),
                    event.subject_id,
                    event.sequence,
                    payload,
                    payload_size,
                    now.timestamp(),
                    now.timestamp(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise OutboxCorruptionError(
                f"duplicate event identity or subject sequence: {event.event_id}"
            ) from error

    def _expire_in_transaction(self, now: datetime) -> None:
        cutoff = (now - self._max_age).timestamp()
        expired = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE created_at < ?", (cutoff,)
            ).fetchone()[0]
        )
        if expired:
            self._connection.execute("DELETE FROM outbox_events WHERE created_at < ?", (cutoff,))
            self._increment_counter("expired_events", expired)

    def _increment_counter(self, name: str, amount: int = 1) -> None:
        self._connection.execute(
            "UPDATE outbox_counters SET value = value + ? WHERE name = ?", (amount, name)
        )

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS outbox_events (
                event_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                payload TEXT NOT NULL,
                payload_size INTEGER NOT NULL CHECK (payload_size > 0),
                retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
                next_attempt_at REAL NOT NULL,
                lease_owner TEXT,
                lease_expires_at REAL,
                created_at REAL NOT NULL,
                UNIQUE (subject_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS ix_outbox_ready
                ON outbox_events (next_attempt_at, created_at);
            CREATE TABLE IF NOT EXISTS outbox_counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO outbox_counters (name, value)
                VALUES ('dropped_events', 0), ('expired_events', 0);
            """
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("outbox clock must return timezone-aware UTC")
        return now

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @staticmethod
    def _record(row: sqlite3.Row | tuple[object, ...]) -> OutboxRecord:
        lease_expires_at = row[8]
        return OutboxRecord(
            event_id=str(row[0]),
            subject_id=str(row[1]),
            sequence=int(row[2]),
            payload=str(row[3]),
            payload_size=int(row[4]),
            retry_count=int(row[5]),
            next_attempt_at=datetime.fromtimestamp(float(row[6]), UTC),
            lease_owner=None if row[7] is None else str(row[7]),
            lease_expires_at=(
                None
                if lease_expires_at is None
                else datetime.fromtimestamp(float(lease_expires_at), UTC)
            ),
            created_at=datetime.fromtimestamp(float(row[9]), UTC),
        )


class OutboxPublisher:
    """Drain persisted events through a remote connector with stable identities."""

    def __init__(
        self,
        outbox: SQLiteOutbox,
        connector: TwinConnector,
        *,
        owner: str | None = None,
        retry_delay: timedelta = timedelta(0),
    ) -> None:
        """Configure one synchronous, single-owner publisher."""
        self._outbox = outbox
        self._connector = connector
        self._owner = owner or f"publisher-{uuid4()}"
        self._retry_delay = retry_delay

    @property
    def destination(self) -> str:
        """Return the redacted remote destination."""
        return self._connector.destination

    def publish(self, event: ProcessEvent) -> PublicationReceipt:
        """Drain through the supplied event and require its acknowledgement."""
        event_id = str(event.event_id)
        if not self._outbox.contains(event_id):
            raise PublicationError(f"event was not durably enqueued: {event_id}")
        while self._outbox.contains(event_id):
            if self.drain(max_events=1) == 0:
                raise PublicationError(f"event is not ready for publication: {event_id}")
        return PublicationReceipt(destination=self.destination)

    def drain(self, *, max_events: int | None = None) -> int:
        """Publish ready backlog rows and acknowledge only successful sends."""
        published = 0
        while max_events is None or published < max_events:
            records = self._outbox.lease(owner=self._owner, limit=1)
            if not records:
                break
            record = records[0]
            try:
                self._connector.publish(record.event())
            except Exception as error:
                self._outbox.retry(
                    record.event_id,
                    owner=self._owner,
                    delay=self._retry_delay,
                )
                if isinstance(error, PublicationError):
                    raise
                raise PublicationError(f"publication failed for {self.destination}") from error
            self._outbox.acknowledge(record.event_id, owner=self._owner)
            published += 1
        return published

    def close(self) -> None:
        """Close the remote producer without discarding queued rows."""
        self._connector.close()


__all__ = [
    "OutboxCorruptionError",
    "OutboxError",
    "OutboxFullError",
    "OutboxMetrics",
    "OutboxPublisher",
    "OutboxRecord",
    "OverflowPolicy",
    "SQLiteOutbox",
]

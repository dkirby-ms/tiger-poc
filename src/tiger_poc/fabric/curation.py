"""Dependency-free decisions for raw-to-curated Fabric process events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

Scalar: TypeAlias = str | int | float | bool | None
RawRecord: TypeAlias = Mapping[str, Scalar]
CuratedRecord: TypeAlias = dict[str, Scalar]
RejectionReason: TypeAlias = Literal["duplicate", "invalid", "stale"]

REQUIRED_FIELDS = (
    "schemaVersion",
    "eventId",
    "eventType",
    "subjectId",
    "subjectType",
    "siteId",
    "deviceId",
    "ontologyVersion",
    "sequence",
    "observedAt",
    "emittedAt",
    "state",
    "confidence",
    "sourceRuntime",
    "sourceModel",
)


@dataclass(frozen=True)
class RejectedRecord:
    """Describe a raw row excluded from curated Fabric tables."""

    reason: RejectionReason
    event_id: str | None
    subject_id: str | None
    detail: str


@dataclass(frozen=True)
class CurationResult:
    """Hold deterministic Delta merge inputs and classified rejections."""

    history_rows: tuple[CuratedRecord, ...]
    current_rows: tuple[CuratedRecord, ...]
    rejected_rows: tuple[RejectedRecord, ...]


def curate_records(
    records: Iterable[RawRecord],
    *,
    existing_event_ids: Iterable[str] = (),
    current_sequences: Mapping[str, int] | None = None,
) -> CurationResult:
    """Classify flattened rows and produce deterministic history/current merge inputs.

    Duplicate event IDs and station sequences that are not newer than current state are
    rejected. Within a batch, accepted rows advance the station sequence immediately.

    Args:
        records: Flattened Eventstream rows in arrival order.
        existing_event_ids: Event IDs already present in curated history.
        current_sequences: Highest curated sequence by station ID.

    Returns:
        Immutable collections for append-only history, current state, and audit rejection.
    """
    seen_event_ids = set(existing_event_ids)
    highest_sequences = dict(current_sequences or {})
    history_rows: list[CuratedRecord] = []
    current_by_station: dict[str, CuratedRecord] = {}
    rejected_rows: list[RejectedRecord] = []

    for record in records:
        invalid_detail = _invalid_detail(record)
        event_id = _optional_string(record.get("eventId"))
        subject_id = _optional_string(record.get("subjectId"))
        if invalid_detail is not None:
            rejected_rows.append(RejectedRecord("invalid", event_id, subject_id, invalid_detail))
            continue

        assert event_id is not None
        assert subject_id is not None
        if event_id in seen_event_ids:
            rejected_rows.append(
                RejectedRecord("duplicate", event_id, subject_id, "eventId already curated")
            )
            continue

        sequence = record["sequence"]
        assert isinstance(sequence, int) and not isinstance(sequence, bool)
        if sequence <= highest_sequences.get(subject_id, 0):
            rejected_rows.append(
                RejectedRecord(
                    "stale",
                    event_id,
                    subject_id,
                    "sequence does not advance station current state",
                )
            )
            continue

        curated = {field: record[field] for field in REQUIRED_FIELDS if field != "subjectType"}
        curated["stationId"] = subject_id
        traceparent = record.get("traceparent")
        if traceparent is not None:
            curated["traceparent"] = traceparent

        seen_event_ids.add(event_id)
        highest_sequences[subject_id] = sequence
        history_rows.append(curated)
        current_by_station[subject_id] = curated

    current_rows = tuple(current_by_station[key] for key in sorted(current_by_station))
    return CurationResult(tuple(history_rows), current_rows, tuple(rejected_rows))


def _invalid_detail(record: RawRecord) -> str | None:
    missing = [field for field in REQUIRED_FIELDS if record.get(field) is None]
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    if record["schemaVersion"] != "1.0":
        return "schemaVersion must be 1.0"
    if record["eventType"] != "ProcessStateChanged":
        return "eventType cannot map to Station process state"
    if record["subjectType"] != "Station":
        return "subjectType cannot map to Station"
    sequence = record["sequence"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        return "sequence must be a positive integer"
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None

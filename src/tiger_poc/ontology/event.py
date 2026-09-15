"""Canonical process-event contract shared by local and Fabric connectors."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

from tiger_poc.types import JsonValue

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class ProcessState(StrEnum):
    """Define the deliberately narrow line-monitoring state vocabulary."""

    BLOCKED = "blocked"
    CLEAR = "clear"


class ProcessStateValue(BaseModel):
    """Describe the semantic value carried by a process-state transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ProcessState = ProcessState.BLOCKED


class EventSource(BaseModel):
    """Identify the inference runtime and model that produced an observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime: NonEmptyString
    model: NonEmptyString


class ProcessEvent(BaseModel):
    """Represent one immutable, versioned process-state transition."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal["1.0"] = Field(alias="schemaVersion", default="1.0")
    event_id: UUID = Field(alias="eventId", default_factory=uuid4)
    event_type: Literal["ProcessStateChanged"] = Field(
        alias="eventType", default="ProcessStateChanged"
    )
    subject_id: NonEmptyString = Field(alias="subjectId")
    site_id: NonEmptyString = Field(alias="siteId")
    device_id: NonEmptyString = Field(alias="deviceId")
    ontology_version: NonEmptyString = Field(alias="ontologyVersion")
    sequence: int = Field(ge=1)
    observed_at: datetime = Field(alias="observedAt")
    emitted_at: datetime = Field(alias="emittedAt")
    value: ProcessStateValue = Field(default_factory=ProcessStateValue)
    confidence: float = Field(ge=0.0, le=1.0)
    source: EventSource
    traceparent: str | None = Field(
        default=None,
        pattern=r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$",
    )

    @field_validator("observed_at", "emitted_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        """Reject naive and non-UTC timestamps at the wire-contract boundary."""
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value

    @field_serializer("observed_at", "emitted_at", when_used="json")
    def serialize_utc(self, value: datetime) -> str:
        """Emit stable millisecond timestamps with the explicit UTC marker."""
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical JSON-compatible payload with wire aliases."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def to_json(self) -> str:
        """Serialize deterministically for byte-stable connector output."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


__all__ = ["EventSource", "ProcessEvent", "ProcessState", "ProcessStateValue"]

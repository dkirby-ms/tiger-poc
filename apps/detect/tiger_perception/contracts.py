"""Typed contracts shared by perception sources, mappers, and sinks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Self

JsonValue = str | int | float | bool | None
SubjectResolution = Literal["resolved", "unresolved"]


@dataclass(frozen=True)
class Frame:
    """A captured frame or sensor sample presented to an inference provider."""

    source_id: str
    sequence: int
    captured_at: str
    payload: Any
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDetection:
    """A provider-specific detection retained as diagnostic evidence."""

    class_id: int
    label: str
    confidence: float
    bounding_box: dict[str, float]
    case_id: str | None = None


@dataclass(frozen=True)
class RawInference:
    """The raw result produced by an inference provider for one frame."""

    inference_id: str
    source_id: str
    sequence: int
    captured_at: str
    produced_at: str
    provider: str
    model: str
    detections: list[RawDetection] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    succeeded: bool = True
    qr_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Observation:
    """A normalized sensor observation independent of provider or transport."""

    observation_id: str
    source_id: str
    observation_type: str
    value: JsonValue
    confidence: float
    captured_at: str
    produced_at: str
    provider: str
    model: str
    subject_id: str | None = None
    subject_resolution: SubjectResolution = "unresolved"
    unit: str = ""
    raw_inference_id: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessEvent:
    """A versioned process event ready for publication by a sink."""

    event_id: str
    source_id: str
    subject_id: str
    observation_type: str
    value: JsonValue
    unit: str
    confidence: float
    captured_at: str
    produced_at: str
    published_at: str
    provider: str
    model: str
    source: str
    schema_version: str = "1.0"
    event_type: str = "ProcessEvent"
    observation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this event using the wire-format field names."""
        event: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "eventType": self.event_type,
            "sourceId": self.source_id,
            "subjectId": self.subject_id,
            "observationType": self.observation_type,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "capturedAt": self.captured_at,
            "producedAt": self.produced_at,
            "publishedAt": self.published_at,
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
        }
        if self.observation is not None:
            event["observation"] = self.observation
        return event

    @classmethod
    def from_dict(cls, event: dict[str, Any]) -> Self:
        """Create a typed event from the ProcessEvent wire format."""
        return cls(
            schema_version=event["schemaVersion"],
            event_id=event["eventId"],
            event_type=event["eventType"],
            source_id=event["sourceId"],
            subject_id=event["subjectId"],
            observation_type=event["observationType"],
            value=event["value"],
            unit=event["unit"],
            confidence=event["confidence"],
            captured_at=event["capturedAt"],
            produced_at=event["producedAt"],
            published_at=event["publishedAt"],
            provider=event["provider"],
            model=event["model"],
            source=event["source"],
            observation=event.get("observation"),
        )


class Sink(Protocol):
    """Publication boundary shared by local and future remote sinks."""

    def publish(self, event: ProcessEvent | dict[str, Any]) -> bool:
        """Publish an event and return whether a new record was written."""
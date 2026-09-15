"""Immutable observation contract shared by all perception workloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from tiger_poc.types import JsonValue


@dataclass(frozen=True, slots=True)
class Observation:
    """Represent one UTC measurement about a subject at a point in time."""

    subject_id: str
    observation_type: str
    value: JsonValue
    timestamp: datetime
    confidence: float
    source: str

    def __post_init__(self) -> None:
        """Validate fields required by the stable observation boundary."""
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if not self.observation_type:
            raise ValueError("observation_type is required")
        if not self.source:
            raise ValueError("source is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")

    def to_dict(self) -> dict[str, JsonValue]:
        """Serialize with stable camelCase keys and an explicit UTC marker."""
        timestamp = self.timestamp.isoformat().replace("+00:00", "Z")
        return {
            "subjectId": self.subject_id,
            "observationType": self.observation_type,
            "value": self.value,
            "timestamp": timestamp,
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }

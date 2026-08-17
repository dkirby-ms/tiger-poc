"""Deterministic threshold and continuous-presence dwell rules."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import BaseModel, ConfigDict, Field

from apps.pipeline_framework.contracts import Envelope, StageBase
from apps.pipeline_framework.payloads import DetectionSet, Event, RuleEvaluation


class ThresholdRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    min_count: int = Field(default=1, gt=0)


class ThresholdRule(StageBase):
    def __init__(self, config: ThresholdRuleConfig) -> None:
        super().__init__()
        self._config = config

    async def process(
        self, envelope: Envelope[DetectionSet]
    ) -> AsyncIterator[Envelope[RuleEvaluation]]:
        matches = tuple(
            item
            for item in envelope.payload.detections
            if item.label == self._config.label
            and item.confidence >= self._config.min_confidence
        )
        yield envelope.derive(
            RuleEvaluation(
                rule=f"threshold:{self._config.label}",
                matched=len(matches) >= self._config.min_count,
                detections=matches,
            )
        )


class DwellRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_dwell_s: float = Field(default=0, ge=0)
    event_type: str


class DwellRule(StageBase):
    def __init__(self, config: DwellRuleConfig) -> None:
        super().__init__()
        self._config = config
        self._started_at: dict[str, float] = {}
        self._emitted: set[str] = set()

    async def process(
        self, envelope: Envelope[RuleEvaluation]
    ) -> AsyncIterator[Envelope[Event]]:
        stream_id = envelope.stream_id
        evaluation = envelope.payload
        if not evaluation.matched:
            self._started_at.pop(stream_id, None)
            self._emitted.discard(stream_id)
            return
        started_at = self._started_at.setdefault(stream_id, envelope.captured_at)
        if stream_id in self._emitted:
            return
        if envelope.captured_at - started_at < self._config.min_dwell_s:
            return
        self._emitted.add(stream_id)
        yield envelope.derive(
            Event(
                event_type=self._config.event_type,
                stream_id=stream_id,
                started_at=started_at,
                occurred_at=envelope.captured_at,
                detections=evaluation.detections,
            )
        )
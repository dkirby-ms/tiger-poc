"""Core data and lifecycle contracts shared by pipeline stages."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

import ulid

T = TypeVar("T")
TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class Envelope(Generic[T]):
    """A payload with stable stream identity, ordering, timing, and trace data."""

    id: str
    stream_id: str
    seq: int
    captured_at: float
    payload: T
    meta: Mapping[str, Any] = field(default_factory=dict)
    traceparent: str | None = None

    def __post_init__(self) -> None:
        if not self.stream_id:
            raise ValueError("stream_id is required")
        if self.seq < 0:
            raise ValueError("seq cannot be negative")
        object.__setattr__(self, "meta", _immutable_mapping(self.meta))

    @classmethod
    def create(
        cls,
        *,
        stream_id: str,
        seq: int,
        captured_at: float,
        payload: T,
        meta: Mapping[str, Any] | None = None,
        traceparent: str | None = None,
    ) -> Envelope[T]:
        return cls(
            id=str(ulid.new()),
            stream_id=stream_id,
            seq=seq,
            captured_at=captured_at,
            payload=payload,
            meta=meta or {},
            traceparent=traceparent,
        )

    def derive(self, payload: TOut, **annotations: Any) -> Envelope[TOut]:
        metadata = dict(self.meta)
        metadata.update(annotations)
        metadata["parent_id"] = self.id
        return Envelope.create(
            stream_id=self.stream_id,
            seq=self.seq,
            captured_at=self.captured_at,
            payload=payload,
            meta=metadata,
            traceparent=self.traceparent,
        )


@dataclass(frozen=True)
class StageHealth:
    """Current stage availability and optional diagnostic message."""

    ready: bool = True
    message: str | None = None


@dataclass(frozen=True)
class StageContext:
    """Dependencies supplied to a stage by the runner."""

    stage_id: str
    services: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "services", _immutable_mapping(self.services))


@runtime_checkable
class Stage(Protocol[TIn, TOut]):
    """A pipeline worker that can filter, map, or fan out envelopes."""

    async def setup(self, context: StageContext) -> None: ...

    def process(self, envelope: Envelope[TIn]) -> AsyncIterator[Envelope[TOut]]: ...

    async def teardown(self) -> None: ...

    def health(self) -> StageHealth: ...


@runtime_checkable
class Source(Protocol[TOut]):
    """A finite or streaming envelope producer."""

    async def setup(self, context: StageContext) -> None: ...

    def produce(self) -> AsyncIterator[Envelope[TOut]]: ...

    async def teardown(self) -> None: ...

    def health(self) -> StageHealth: ...


class StageBase:
    """No-op lifecycle defaults for built-in and third-party stages."""

    def __init__(self) -> None:
        self._health = StageHealth()

    async def setup(self, context: StageContext) -> None:
        self._health = replace(self._health, ready=True, message=None)

    async def teardown(self) -> None:
        return None

    def health(self) -> StageHealth:
        return self._health
"""Bounded in-process channels with explicit overflow accounting."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum

from .contracts import Envelope


class OverflowPolicy(str, Enum):
    BLOCK = "block"
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    SAMPLE = "sample"


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    dropped: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class ChannelStats:
    capacity: int
    depth: int
    sent: int
    received: int
    dropped: int
    closed: bool


_CLOSED = object()


class InProcChannel:
    """An asyncio queue that makes frame loss visible and deterministic."""

    def __init__(
        self,
        capacity: int,
        on_full: OverflowPolicy = OverflowPolicy.BLOCK,
        sample_every: int = 2,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if sample_every <= 0:
            raise ValueError("sample_every must be positive")
        self._queue: asyncio.Queue[Envelope | object] = asyncio.Queue(capacity)
        self._capacity = capacity
        self._on_full = on_full
        self._sample_every = sample_every
        self._pressure_count = 0
        self._sent = 0
        self._received = 0
        self._dropped = 0
        self._closed = False

    async def send(self, envelope: Envelope) -> SendResult:
        if self._closed:
            raise RuntimeError("cannot send to a closed channel")
        if not self._queue.full():
            self._queue.put_nowait(envelope)
            self._sent += 1
            return SendResult(accepted=True)
        if self._on_full is OverflowPolicy.BLOCK:
            await self._queue.put(envelope)
            self._sent += 1
            return SendResult(accepted=True)
        if self._on_full is OverflowPolicy.DROP_NEWEST:
            self._dropped += 1
            return SendResult(accepted=False, dropped=1, reason="drop_newest")
        if self._on_full is OverflowPolicy.SAMPLE:
            self._pressure_count += 1
            if self._pressure_count % self._sample_every:
                self._dropped += 1
                return SendResult(accepted=False, dropped=1, reason="sample")
        self._queue.get_nowait()
        self._dropped += 1
        self._queue.put_nowait(envelope)
        self._sent += 1
        return SendResult(accepted=True, dropped=1, reason=self._on_full.value)

    async def receive(self) -> AsyncIterator[Envelope]:
        while True:
            if self._closed and self._queue.empty():
                return
            item = await self._queue.get()
            if item is _CLOSED:
                return
            self._received += 1
            yield item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._queue.empty():
            self._queue.put_nowait(_CLOSED)

    def stats(self) -> ChannelStats:
        depth = self._queue.qsize()
        if self._closed and depth:
            depth -= 1
        return ChannelStats(
            capacity=self._capacity,
            depth=max(depth, 0),
            sent=self._sent,
            received=self._received,
            dropped=self._dropped,
            closed=self._closed,
        )
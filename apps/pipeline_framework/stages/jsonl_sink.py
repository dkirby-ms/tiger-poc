"""JSON Lines event sink with bounded local retention."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from apps.pipeline_framework.contracts import Envelope, StageBase
from apps.pipeline_framework.payloads import Event


class JsonlSinkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    create_parents: bool = True
    max_bytes: int = Field(default=64 * 1024 * 1024, gt=0)


class JsonlSink(StageBase):
    def __init__(self, config: JsonlSinkConfig) -> None:
        super().__init__()
        self._config = config

    async def setup(self, context) -> None:
        await super().setup(context)
        if self._config.create_parents:
            self._config.path.parent.mkdir(parents=True, exist_ok=True)

    async def process(self, envelope: Envelope[Event]) -> AsyncIterator[Envelope[None]]:
        record = {
            "schema_version": 1,
            "envelope_id": envelope.id,
            "seq": envelope.seq,
            **asdict(envelope.payload),
        }
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        await asyncio.to_thread(_append_bounded, self._config.path, line, self._config.max_bytes)
        if False:
            yield envelope.derive(None)


def _append_bounded(path: Path, line: str, max_bytes: int) -> None:
    encoded = line.encode("utf-8")
    if path.exists() and path.stat().st_size + len(encoded) > max_bytes:
        existing = path.read_bytes()
        keep = existing[-max(0, max_bytes - len(encoded)) :]
        first_newline = keep.find(b"\n")
        keep = keep[first_newline + 1 :] if first_newline >= 0 else b""
        path.write_bytes(keep)
    with path.open("ab") as output:
        output.write(encoded)
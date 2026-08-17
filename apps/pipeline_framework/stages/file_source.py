"""Finite image, folder, and video file source."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from time import time

import av
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from apps.pipeline_framework.contracts import Envelope, StageBase
from apps.pipeline_framework.payloads import Frame

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})


class FileSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path
    stream_id: str = "file"
    target_fps: float | None = Field(default=None, gt=0)


class FileSource(StageBase):
    def __init__(self, config: FileSourceConfig) -> None:
        super().__init__()
        self._config = config

    async def setup(self, context) -> None:
        await super().setup(context)
        if not self._config.path.exists():
            raise FileNotFoundError(self._config.path)

    async def produce(self) -> AsyncIterator[Envelope[Frame]]:
        iterator = iter(_read_frames(self._config.path, self._config.target_fps))
        sequence = 0
        while True:
            item = await asyncio.to_thread(_next_or_none, iterator)
            if item is None:
                return
            image, captured_at = item
            yield Envelope.create(
                stream_id=self._config.stream_id,
                seq=sequence,
                captured_at=captured_at,
                payload=Frame(image=image, source=str(self._config.path)),
            )
            sequence += 1


def _next_or_none(iterator: Iterator[tuple[Image.Image, float]]):
    try:
        return next(iterator)
    except StopIteration:
        return None


def _read_frames(path: Path, target_fps: float | None) -> Iterator[tuple[Image.Image, float]]:
    if path.is_dir():
        for image_path in sorted(item for item in path.iterdir() if item.suffix.lower() in IMAGE_SUFFIXES):
            with Image.open(image_path) as image:
                yield image.convert("RGB"), image_path.stat().st_mtime
        return
    if path.suffix.lower() in IMAGE_SUFFIXES:
        with Image.open(path) as image:
            yield image.convert("RGB"), path.stat().st_mtime
        return
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        minimum_delta = 1.0 / target_fps if target_fps else 0.0
        last_timestamp: float | None = None
        for frame in container.decode(stream):
            timestamp = float(frame.time) if frame.time is not None else time()
            if last_timestamp is not None and timestamp - last_timestamp < minimum_delta:
                continue
            last_timestamp = timestamp
            yield frame.to_image().convert("RGB"), timestamp
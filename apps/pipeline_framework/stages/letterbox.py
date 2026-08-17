"""Aspect-preserving image resize and padding stage."""

from __future__ import annotations

from collections.abc import AsyncIterator

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from apps.pipeline_framework.contracts import Envelope, StageBase
from apps.pipeline_framework.payloads import Frame, PreparedFrame


class LetterboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=640, gt=0)


class Letterbox(StageBase):
    def __init__(self, config: LetterboxConfig) -> None:
        super().__init__()
        self._size = config.size

    async def process(self, envelope: Envelope[Frame]) -> AsyncIterator[Envelope[PreparedFrame]]:
        image = envelope.payload.image
        width, height = image.size
        scale = min(self._size / width, self._size / height)
        resized_size = (round(width * scale), round(height * scale))
        resized = image.resize(resized_size, Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (self._size, self._size), (114, 114, 114))
        pad_x = (self._size - resized.width) // 2
        pad_y = (self._size - resized.height) // 2
        canvas.paste(resized, (pad_x, pad_y))
        yield envelope.derive(
            PreparedFrame(
                image=canvas,
                original_width=width,
                original_height=height,
                scale=scale,
                pad_x=pad_x,
                pad_y=pad_y,
            )
        )
"""Reconnectable RTSP frame source using PyAV."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from time import time
from typing import Any, Literal

import av
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.pipeline_framework.contracts import Envelope, StageBase, StageContext, StageHealth
from apps.pipeline_framework.payloads import Frame


class RtspSourceConfig(BaseModel):
    """Connection, sampling, and reconnect settings for one RTSP stream."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None
    url_env: str = "TIGER_RTSP_URL"
    stream_id: str = "rtsp"
    target_fps: float | None = Field(default=None, gt=0)
    transport: Literal["tcp", "udp"] = "tcp"
    open_timeout_s: float = Field(default=10, gt=0)
    read_timeout_s: float = Field(default=10, gt=0)
    reconnect_backoff_s: tuple[float, ...] = Field(
        default=(1, 2, 5, 15), min_length=1
    )

    @field_validator("url_env", "stream_id")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("reconnect_backoff_s")
    @classmethod
    def require_non_negative_backoff(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(delay < 0 for delay in value):
            raise ValueError("reconnect delays cannot be negative")
        return value


class RtspSource(StageBase):
    """Produces ordered frames from an RTSP stream and reconnects on failure."""

    def __init__(self, config: RtspSourceConfig) -> None:
        super().__init__()
        self._config = config
        self._url: str | None = None
        self._active_container: Any = None

    async def setup(self, context: StageContext) -> None:
        await super().setup(context)
        self._url = self._config.url or os.environ.get(self._config.url_env)
        if not self._url:
            self._health = StageHealth(
                False,
                f"RTSP URL is required in config or ${self._config.url_env}",
            )
            raise ValueError(self._health.message)
        if not self._url.lower().startswith(("rtsp://", "rtsps://")):
            self._health = StageHealth(False, "RTSP URL must use rtsp:// or rtsps://")
            raise ValueError(self._health.message)

    async def produce(self) -> AsyncIterator[Envelope[Frame]]:
        sequence = 0
        reconnect_attempt = 0
        last_captured_at: float | None = None
        while True:
            try:
                container = await asyncio.to_thread(self._open)
                self._active_container = container
                connected_at = time()
                first_media_time: float | None = None
                last_sample_time: float | None = None
                decoder = iter(container.decode(container.streams.video[0]))

                while True:
                    frame = await asyncio.to_thread(_next_or_none, decoder)
                    if frame is None:
                        raise EOFError("RTSP stream ended")
                    media_time = float(frame.time) if frame.time is not None else None
                    sample_time = media_time if media_time is not None else time()
                    if not _should_emit(
                        sample_time,
                        last_sample_time,
                        self._config.target_fps,
                    ):
                        continue
                    last_sample_time = sample_time
                    if media_time is not None:
                        if first_media_time is None:
                            first_media_time = media_time
                        captured_at = connected_at + media_time - first_media_time
                    else:
                        captured_at = time()
                    if last_captured_at is not None:
                        captured_at = max(captured_at, last_captured_at + 0.000001)
                    last_captured_at = captured_at
                    reconnect_attempt = 0
                    self._health = StageHealth()
                    yield Envelope.create(
                        stream_id=self._config.stream_id,
                        seq=sequence,
                        captured_at=captured_at,
                        payload=Frame(
                            image=frame.to_image().convert("RGB"),
                            source=f"rtsp:{self._config.stream_id}",
                        ),
                    )
                    sequence += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self._health = StageHealth(
                    False,
                    "RTSP connection unavailable; reconnecting",
                )
            finally:
                await asyncio.to_thread(self._close_active)

            delay = self._config.reconnect_backoff_s[
                min(reconnect_attempt, len(self._config.reconnect_backoff_s) - 1)
            ]
            reconnect_attempt += 1
            await asyncio.sleep(delay)

    async def teardown(self) -> None:
        await asyncio.to_thread(self._close_active)
        await super().teardown()

    def _open(self):
        return av.open(
            self._url,
            mode="r",
            options={"rtsp_transport": self._config.transport},
            timeout=(self._config.open_timeout_s, self._config.read_timeout_s),
        )

    def _close_active(self) -> None:
        container = self._active_container
        self._active_container = None
        if container is not None:
            container.close()


def _next_or_none(iterator: Iterator[Any]) -> Any | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _should_emit(
    sample_time: float,
    last_sample_time: float | None,
    target_fps: float | None,
) -> bool:
    if target_fps is None or last_sample_time is None:
        return True
    return sample_time - last_sample_time >= 1.0 / target_fps
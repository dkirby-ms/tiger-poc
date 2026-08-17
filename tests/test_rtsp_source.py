from types import SimpleNamespace

import pytest
from PIL import Image

from apps.pipeline_framework import StageContext
from apps.pipeline_framework.stages import rtsp_source
from apps.pipeline_framework.stages.rtsp_source import RtspSource, RtspSourceConfig


class FakeFrame:
    def __init__(self, media_time: float | None) -> None:
        self.time = media_time

    def to_image(self) -> Image.Image:
        return Image.new("RGB", (16, 9), "blue")


class FakeContainer:
    def __init__(self, media_times: list[float | None]) -> None:
        self.frames = [FakeFrame(value) for value in media_times]
        self.streams = SimpleNamespace(video=[object()])
        self.closed = False

    def decode(self, stream):
        return iter(self.frames)

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_given_missing_rtsp_url_when_setup_then_actionable_error_is_raised(monkeypatch):
    # Arrange
    monkeypatch.delenv("TIGER_RTSP_URL", raising=False)
    source = RtspSource(RtspSourceConfig())

    # Act and Assert
    with pytest.raises(ValueError, match="TIGER_RTSP_URL"):
        await source.setup(StageContext("camera"))


@pytest.mark.asyncio
async def test_given_environment_url_when_opened_then_transport_and_timeouts_are_applied(
    monkeypatch,
):
    # Arrange
    secret_url = "rtsp://camera-user:camera-password@camera.local/live"
    monkeypatch.setenv("CAMERA_URL", secret_url)
    container = FakeContainer([0.0])
    calls = []

    def fake_open(url, **kwargs):
        calls.append((url, kwargs))
        return container

    monkeypatch.setattr(rtsp_source.av, "open", fake_open)
    monkeypatch.setattr(rtsp_source, "time", lambda: 1000.0)
    source = RtspSource(
        RtspSourceConfig(
            url_env="CAMERA_URL",
            stream_id="dock-01",
            transport="udp",
            open_timeout_s=3,
            read_timeout_s=7,
        )
    )
    await source.setup(StageContext("camera"))
    producer = source.produce()

    # Act
    result = await anext(producer)
    await producer.aclose()

    # Assert
    assert calls == [
        (
            secret_url,
            {
                "mode": "r",
                "options": {"rtsp_transport": "udp"},
                "timeout": (3.0, 7.0),
            },
        )
    ]
    assert result.payload.source == "rtsp:dock-01"
    assert secret_url not in repr(result)
    assert container.closed is True


@pytest.mark.asyncio
async def test_given_transient_failures_when_producing_then_reconnects_and_preserves_order(
    monkeypatch,
):
    # Arrange
    first_stream = FakeContainer([0.0, 0.1, 0.25])
    second_stream = FakeContainer([0.0])
    attempts = iter([OSError("offline"), first_stream, second_stream])
    delays = []

    def fake_open(url, **kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(rtsp_source.av, "open", fake_open)
    monkeypatch.setattr(rtsp_source.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(rtsp_source, "time", lambda: 1000.0)
    source = RtspSource(
        RtspSourceConfig(
            url="rtsp://localhost/live",
            stream_id="camera-1",
            target_fps=5,
            reconnect_backoff_s=(0.5, 2),
        )
    )
    await source.setup(StageContext("camera"))
    producer = source.produce()

    # Act
    results = [await anext(producer) for _ in range(3)]
    await producer.aclose()

    # Assert
    assert [item.seq for item in results] == [0, 1, 2]
    assert [item.captured_at for item in results] == [1000.0, 1000.25, 1000.250001]
    assert delays == [0.5, 0.5]
    assert first_stream.closed is True
    assert second_stream.closed is True
    assert source.health().ready is True


@pytest.mark.asyncio
async def test_given_connections_without_frames_when_reconnecting_then_backoff_escalates(
    monkeypatch,
):
    # Arrange
    attempts = iter(
        [
            FakeContainer([]),
            FakeContainer([]),
            FakeContainer([0.0]),
        ]
    )
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(rtsp_source.av, "open", lambda *args, **kwargs: next(attempts))
    monkeypatch.setattr(rtsp_source.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(rtsp_source, "time", lambda: 1000.0)
    source = RtspSource(
        RtspSourceConfig(
            url="rtsp://localhost/live",
            reconnect_backoff_s=(0.5, 2),
        )
    )
    await source.setup(StageContext("camera"))
    producer = source.produce()

    # Act
    result = await anext(producer)
    await producer.aclose()

    # Assert
    assert result.seq == 0
    assert delays == [0.5, 2]


@pytest.mark.asyncio
async def test_given_active_container_when_torn_down_then_container_is_closed():
    # Arrange
    container = FakeContainer([])
    source = RtspSource(RtspSourceConfig(url="rtsp://localhost/live"))
    source._active_container = container

    # Act
    await source.teardown()

    # Assert
    assert container.closed is True
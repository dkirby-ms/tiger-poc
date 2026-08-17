from types import MappingProxyType

import pytest

from apps.pipeline_framework import Envelope, InProcChannel, OverflowPolicy


def envelope(sequence: int) -> Envelope[int]:
    return Envelope.create(
        stream_id="camera-1",
        seq=sequence,
        captured_at=float(sequence),
        payload=sequence,
    )


def test_given_envelope_when_derived_then_identity_changes_and_ordering_is_preserved():
    # Arrange
    original = envelope(3)

    # Act
    derived = original.derive("result", stage="detect")

    # Assert
    assert derived.id != original.id
    assert (derived.stream_id, derived.seq, derived.captured_at) == ("camera-1", 3, 3.0)
    assert derived.meta == {"stage": "detect", "parent_id": original.id}
    assert isinstance(derived.meta, MappingProxyType)


@pytest.mark.asyncio
async def test_given_drop_oldest_channel_when_full_then_latest_item_is_retained():
    # Arrange
    channel = InProcChannel(capacity=1, on_full=OverflowPolicy.DROP_OLDEST)

    # Act
    await channel.send(envelope(1))
    result = await channel.send(envelope(2))
    await channel.close()
    received = [item.seq async for item in channel.receive()]

    # Assert
    assert received == [2]
    assert result.dropped == 1
    assert channel.stats().dropped == 1


@pytest.mark.asyncio
async def test_given_drop_newest_channel_when_full_then_existing_item_is_retained():
    # Arrange
    channel = InProcChannel(capacity=1, on_full=OverflowPolicy.DROP_NEWEST)

    # Act
    await channel.send(envelope(1))
    result = await channel.send(envelope(2))
    await channel.close()
    received = [item.seq async for item in channel.receive()]

    # Assert
    assert received == [1]
    assert result.accepted is False
    assert channel.stats().dropped == 1


@pytest.mark.asyncio
async def test_given_closed_channel_when_sent_then_runtime_error_is_raised():
    # Arrange
    channel = InProcChannel(capacity=1)
    await channel.close()

    # Act and Assert
    with pytest.raises(RuntimeError, match="closed"):
        await channel.send(envelope(1))
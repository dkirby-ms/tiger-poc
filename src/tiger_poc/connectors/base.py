"""Transport-neutral connector boundary and publication semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from tiger_poc.types import JsonValue


@runtime_checkable
class SerializableEvent(Protocol):
    """Provide the canonical payload published by every connector."""

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the canonical JSON-compatible event payload."""
        ...


@dataclass(frozen=True, slots=True)
class PublicationReceipt:
    """Confirm that a connector accepted an event for its destination."""

    destination: str
    acknowledged: Literal[True] = True


class PublicationError(RuntimeError):
    """Report that a connector did not acknowledge publication."""


@runtime_checkable
class TwinConnector(Protocol):
    """Publish canonical process events without exposing platform details."""

    @property
    def destination(self) -> str:
        """Return a human-readable target identifier suitable for logs."""
        ...

    def publish(self, event: SerializableEvent) -> PublicationReceipt:
        """Publish one event or raise PublicationError without acknowledging it."""
        ...

    def close(self) -> None:
        """Flush and release connector resources."""
        ...

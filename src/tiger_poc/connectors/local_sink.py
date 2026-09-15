"""Deterministic append-only JSON Lines connector for offline validation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import TracebackType
from typing import TextIO

from tiger_poc.connectors.base import PublicationError, PublicationReceipt, SerializableEvent

logger = logging.getLogger(__name__)


class LocalSinkConnector:
    """Write canonical event payloads to JSON Lines with immediate flushes."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Open an optional append-only destination.

        Args:
            path: JSON Lines path. When omitted, events are emitted only to the log.
        """
        self._path = Path(path) if path is not None else None
        self._handle: TextIO | None = None
        self._published = 0
        self._closed = False

        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8")

    def __enter__(self) -> LocalSinkConnector:
        """Return this connector for context-managed publication."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the sink when leaving a context manager."""
        self.close()

    @property
    def destination(self) -> str:
        """Return the file path or the log-only destination identifier."""
        return str(self._path) if self._path is not None else "local-sink://log"

    @property
    def published(self) -> int:
        """Return the number of acknowledged publications."""
        return self._published

    def publish(self, event: SerializableEvent) -> PublicationReceipt:
        """Append and flush one canonical payload before acknowledging it.

        Raises:
            PublicationError: If the connector is closed, serialization fails, or the
                destination cannot accept the complete payload.
        """
        if self._closed:
            raise PublicationError(f"connector is closed: {self.destination}")

        try:
            payload = json.dumps(
                event.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if self._handle is not None:
                self._handle.write(f"{payload}\n")
                self._handle.flush()
        except (OSError, TypeError, ValueError) as error:
            raise PublicationError(f"publication failed for {self.destination}") from error

        logger.info("published event to %s: %s", self.destination, payload)
        self._published += 1
        return PublicationReceipt(destination=self.destination)

    def close(self) -> None:
        """Close the destination; repeated calls have no effect."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._closed = True

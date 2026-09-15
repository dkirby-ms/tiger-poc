"""Relay ProcessEvents to Fabric independently of the local detection runtime."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import ProcessEvent
from .sinks import (
    LocalJsonlSink,
    SinkError,
    SinkUnavailableError,
    validate_process_event,
)

logger = logging.getLogger(__name__)


class FabricEventstreamSink:
    """Validate with detect, optionally trace locally, and publish to Fabric.

    Local traces are audit copies, not delivery acknowledgments or a durable outbox.
    Azure Event Hubs uses default credentials when a namespace is configured.
    Custom App sources can use their Fabric-provided connection string instead.
    """

    def __init__(
        self,
        *,
        connection_string: str | None = None,
        eventhub_name: str | None = None,
        namespace: str | None = None,
        rest_endpoint: str | None = None,
        dry_run: bool = False,
        fallback_jsonl_path: str | Path | None = None,
    ) -> None:
        self.connection_string = connection_string or os.getenv("FABRIC_EVENTSTREAM_CONNECTION_STRING")
        self.eventhub_name = eventhub_name or os.getenv("FABRIC_EVENTSTREAM_EVENTHUB_NAME")
        self.namespace = namespace or os.getenv("FABRIC_EVENTSTREAM_NAMESPACE")
        self.rest_endpoint = rest_endpoint or os.getenv("FABRIC_EVENTSTREAM_REST_ENDPOINT")
        self.dry_run = dry_run or os.getenv("MOCK_FABRIC", "").lower() in {"1", "true", "yes"}
        if not self.dry_run:
            if not (self.namespace or self.connection_string or self.rest_endpoint):
                raise SinkError("Live publishing requires a Fabric destination; use --dry-run offline.")
            if self.namespace and not self.eventhub_name:
                raise SinkError("Namespace authentication requires FABRIC_EVENTSTREAM_EVENTHUB_NAME.")
            if self.rest_endpoint and not self.rest_endpoint.startswith("https://"):
                raise SinkError("The REST destination must use HTTPS.")
        self.fallback_jsonl = (
            LocalJsonlSink(path=fallback_jsonl_path) if fallback_jsonl_path is not None else None
        )
        self._producer_client: Any = None
        self._credential: Any = None

    def _get_eventhub_producer(self) -> Any:
        if self._producer_client is None:
            from azure.eventhub import EventHubProducerClient

            if self.namespace:
                from azure.identity import DefaultAzureCredential

                self._credential = DefaultAzureCredential()
                self._producer_client = EventHubProducerClient(
                    fully_qualified_namespace=self.namespace,
                    eventhub_name=self.eventhub_name,
                    credential=self._credential,
                )
            else:
                self._producer_client = EventHubProducerClient.from_connection_string(
                    conn_str=self.connection_string,
                    **({"eventhub_name": self.eventhub_name} if self.eventhub_name else {}),
                )
        return self._producer_client

    def publish(self, event: ProcessEvent | Mapping[str, Any]) -> bool:
        """Publish a sanitized event; raise on failure without leaking destination secrets."""
        validated = validate_process_event(event)
        if self.fallback_jsonl is not None:
            self.fallback_jsonl.publish(validated)
        if self.dry_run:
            logger.info("Dry-run eventId=%s subjectId=%s", validated["eventId"], validated["subjectId"])
            return True

        try:
            import requests
            from azure.core.exceptions import AzureError
        except ImportError:
            raise SinkUnavailableError("Install the detect project's 'fabric' extra for live publishing.") from None

        try:
            if self.namespace or self.connection_string:
                from azure.eventhub import EventData

                producer = self._get_eventhub_producer()
                batch = producer.create_batch(partition_key=validated["subjectId"])
                batch.add(EventData(json.dumps(validated)))
                producer.send_batch(batch)
            else:
                if self.rest_endpoint is None:
                    raise SinkError("No REST destination configured.")
                response = requests.post(
                    self.rest_endpoint,
                    json=validated,
                    timeout=5.0,
                    allow_redirects=False,
                )
                response.raise_for_status()
                if not 200 <= response.status_code < 300:
                    raise SinkUnavailableError("REST destination did not accept the event.")
        except (AzureError, requests.RequestException, OSError, ValueError):
            raise SinkUnavailableError(
                "Fabric publication failed; verify destination, credentials, permissions and connectivity."
            ) from None
        return True

    def close(self) -> None:
        """Release the producer and credential, even when producer cleanup fails."""
        if self._producer_client is None and self._credential is None:
            return
        from azure.core.exceptions import AzureError

        try:
            try:
                if self._producer_client is not None:
                    self._producer_client.close()
            finally:
                self._producer_client = None
                if self._credential is not None:
                    credential, self._credential = self._credential, None
                    credential.close()
        except (AzureError, OSError, ValueError):
            raise SinkUnavailableError("Fabric client cleanup failed.") from None


def generate_scenario_events(start_time: datetime | None = None) -> list[dict[str, Any]]:
    """Preserve edge's six-transition demo using detect's object and pallet identities."""
    base_time = start_time or datetime.now(UTC)
    run_id = uuid4().hex
    transitions = [
        (0, "a", False), (0, "b", False), (5, "a", True),
        (12, "b", True), (20, "a", False), (28, "b", False),
    ]
    events = []
    for index, (offset, cell, occupied) in enumerate(transitions):
        timestamp = (base_time + timedelta(seconds=offset)).isoformat()
        object_kind = "object" if cell == "a" else "pallet"
        event = ProcessEvent(
            event_id=f"demo-{run_id}-{index}",
            source_id=f"cell-{cell}-camera-01",
            subject_id=f"cell-{cell}-{object_kind}-position-01",
            observation_type="ObjectPresent" if cell == "a" else "PalletPresent",
            value=occupied,
            unit="boolean",
            confidence=0.94 if occupied else 0.0,
            captured_at=timestamp,
            produced_at=timestamp,
            published_at=timestamp,
            provider="local-replay",
            model="demo-model",
            source="replay",
        )
        events.append(validate_process_event(event))
    return events


def read_events(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    """Read complete JSONL files without changing detection outputs or their event IDs."""
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield validate_process_event(json.loads(line))
                except (ValueError, TypeError):
                    raise SinkError(f"Invalid ProcessEvent at input line {line_number}.") from None


def create_parser() -> argparse.ArgumentParser:
    """Create the offline-first relay and demo CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, nargs="+", help="Completed detect JSONL files.")
    source.add_argument("--demo", action="store_true", help="Generate six multi-cell transitions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live-fabric", action="store_true", help="Publish to the configured endpoint.")
    mode.add_argument("--dry-run", action="store_true", help="Validate without network publication.")
    parser.add_argument("--output", type=Path, help="Optional sanitized local audit trace.")
    parser.add_argument("--interval", type=float, default=0.0, help="Seconds between publications.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of demo cycles.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Relay events and report failure with a nonzero exit status."""
    parser = create_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.interval) or args.interval < 0 or args.iterations < 1:
        parser.error("interval must be finite and nonnegative; iterations must be positive")
    if args.input and args.iterations != 1:
        parser.error("--iterations is only supported with --demo")
    if args.output and args.input and any(
        args.output.resolve() == path.resolve() or (
            args.output.exists() and path.exists() and args.output.samefile(path)
        ) for path in args.input
    ):
        parser.error("audit output must differ from every input file")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sink = None
    try:
        sink = FabricEventstreamSink(
            dry_run=not args.live_fabric, fallback_jsonl_path=args.output
        )
        published = 0
        demo_start = datetime.now(UTC)
        for iteration in range(args.iterations):
            events = (
                generate_scenario_events(demo_start + timedelta(seconds=29 * iteration))
                if args.demo
                else read_events(args.input)
            )
            for event in events:
                sink.publish(event)
                published += 1
                if args.interval:
                    time.sleep(args.interval)
        logger.info("%s %d events", "Validated" if sink.dry_run else "Published", published)
        return 0
    except (SinkError, OSError):
        logger.error("Relay failed; verify input data, file access and Fabric configuration.")
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if sink is not None:
            try:
                sink.close()
            except (SinkError, OSError):
                logger.error("Fabric client cleanup failed.")


if __name__ == "__main__":
    raise SystemExit(main())
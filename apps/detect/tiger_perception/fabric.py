"""Relay ProcessEvents to Fabric independently of the local detection runtime."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import math
import os
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self
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
        dry_run: bool = False,
        fallback_jsonl_path: str | Path | None = None,
    ) -> None:
        self.connection_string = connection_string or os.getenv("FABRIC_EVENTSTREAM_CONNECTION_STRING")
        self.eventhub_name = eventhub_name or os.getenv("FABRIC_EVENTSTREAM_EVENTHUB_NAME")
        self.namespace = namespace or os.getenv("FABRIC_EVENTSTREAM_NAMESPACE")
        self.dry_run = dry_run or os.getenv("MOCK_FABRIC", "").lower() in {"1", "true", "yes"}
        secret_file = os.getenv("FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE")
        if not self.dry_run and not self.namespace and not self.connection_string and secret_file:
            try:
                self.connection_string = Path(secret_file).read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                raise SinkError("Cannot read the Fabric connection string secret file.") from None
        if not self.dry_run:
            if not (self.namespace or self.connection_string):
                raise SinkError("Live publishing requires an Event Hubs destination; use --dry-run offline.")
            if self.namespace and not self.eventhub_name:
                raise SinkError("Namespace authentication requires FABRIC_EVENTSTREAM_EVENTHUB_NAME.")
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
            from azure.core.exceptions import AzureError
            from azure.eventhub import EventData

            producer = self._get_eventhub_producer()
            batch = producer.create_batch(partition_key=validated["subjectId"])
            batch.add(EventData(json.dumps(validated)))
            producer.send_batch(batch)
        except ImportError:
            raise SinkUnavailableError("Install the detect project's 'fabric' extra for live publishing.") from None
        except (AzureError, OSError, ValueError):
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
    """Generate six transitions ending now unless an explicit start is provided."""
    base_time = start_time if start_time is not None else datetime.now(UTC) - timedelta(seconds=28)
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
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        yield validate_process_event(json.loads(line))
                    except (ValueError, TypeError):
                        raise SinkError(f"Invalid ProcessEvent at input line {line_number}.") from None
        except UnicodeError as error:
            raise SinkError("Invalid UTF-8 JSONL input; verify the file encoding before retrying.") from error


class JsonlFollower:
    """Relay append-only JSONL with acknowledged offsets and a single checkpoint owner."""

    MAX_LINE_BYTES = 1024 * 1024

    def __init__(self, paths: Iterable[Path], checkpoint: Path, *, dry_run: bool) -> None:
        self.paths = [path.resolve() for path in paths]
        self.checkpoint = checkpoint.resolve()
        self.expected = {
            "version": 2, "inputs": [str(path) for path in self.paths],
            "mode": "dry-run" if dry_run else "live",
        }
        self.state: dict[str, Any] = {**self.expected, "positions": {}}
        self._lock: Any = None

    def __enter__(self) -> Self:
        """Lock delivery state before loading it; never share a checkpoint."""
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self.checkpoint.with_suffix(self.checkpoint.suffix + ".lock").open("a")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.checkpoint.exists():
                self.state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
                if isinstance(self.state, dict) and self.state.get("version") != self.expected["version"]:
                    raise SinkError("Unsupported delivery checkpoint version; reconcile existing state "
                                    "before retrying (do not delete it).")
                if (not isinstance(self.state, dict)
                        or any(self.state.get(key) != value for key, value in self.expected.items())
                        or not isinstance(self.state.get("positions"), dict)
                        or any(key not in self.expected["inputs"] for key in self.state["positions"])):
                    raise SinkError("Delivery checkpoint does not match inputs or publication mode.")
                for position in self.state["positions"].values():
                    if (not isinstance(position, dict)
                            or type(position.get("offset")) is not int or position["offset"] < 0
                            or type(position.get("inode")) is not int
                            or not isinstance(position.get("prefixHash"), str)):
                        raise SinkError("Invalid delivery checkpoint position.")
        except SinkError:
            self.__exit__()
            raise
        except (OSError, ValueError, TypeError):
            self._lock.close()
            self._lock = None
            raise SinkError("Cannot acquire or load delivery checkpoint; check ownership and state.") from None
        return self

    def __exit__(self, *_args: object) -> None:
        """Release the exclusive delivery lock on shutdown or failure."""
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    @staticmethod
    def _prefix_hash(handle: Any, offset: int) -> Any:
        handle.seek(0)
        digest = hashlib.sha256()
        remaining = offset
        while remaining:
            chunk = handle.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise SinkError("A followed input was replaced or truncated; reconcile its checkpoint before retrying.")
            digest.update(chunk)
            remaining -= len(chunk)
        return digest

    def _save(self) -> None:
        temporary = self.checkpoint.with_suffix(self.checkpoint.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.checkpoint)
        directory = os.open(self.checkpoint.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def poll_once(self, publish: Callable[[dict[str, Any]], Any]) -> int:
        """Publish at most 100 complete records per input; save only acknowledged offsets."""
        if self._lock is None:
            raise SinkError("Acquire the delivery checkpoint before following inputs.")
        published = 0
        for path in self.paths:
            position = self.state["positions"].get(str(path))
            try:
                handle = path.open("rb")
            except FileNotFoundError:
                if position is not None:
                    raise SinkError("A followed input disappeared; retain its file and checkpoint.") from None
                continue
            with handle:
                info = os.fstat(handle.fileno())
                offset = position["offset"] if position else 0
                if position and (
                    info.st_ino != position["inode"] or info.st_size < offset
                ):
                    raise SinkError("A followed input was replaced or truncated; reconcile its checkpoint before retrying.")
                digest = self._prefix_hash(handle, offset)
                if position and digest.hexdigest() != position["prefixHash"]:
                    raise SinkError("A followed input was replaced or truncated; reconcile its checkpoint before retrying.")
                handle.seek(offset)
                for _record in range(100):
                    line = handle.readline(self.MAX_LINE_BYTES + 1)
                    if len(line) > self.MAX_LINE_BYTES:
                        raise SinkError("Followed input exceeds the 1 MiB record limit.")
                    if not line.endswith(b"\n"):
                        break
                    if line.strip():
                        try:
                            event = validate_process_event(json.loads(line.decode("utf-8")))
                        except (ValueError, TypeError):
                            raise SinkError("Invalid ProcessEvent in followed input; checkpoint retained.") from None
                        if publish(event) is False:
                            raise SinkUnavailableError("Publication was not acknowledged; checkpoint retained.")
                        published += 1
                    offset = handle.tell()
                    digest.update(line)
                    self.state["positions"][str(path)] = {
                        "offset": offset, "inode": info.st_ino,
                        "prefixHash": digest.hexdigest(),
                    }
                    self._save()
        return published


def create_parser() -> argparse.ArgumentParser:
    """Create the offline-first relay and demo CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, nargs="+", help="Detect JSONL files (append-only with --follow).")
    source.add_argument("--demo", action="store_true", help="Generate six multi-cell transitions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live-fabric", action="store_true", help="Publish to the configured endpoint.")
    mode.add_argument("--dry-run", action="store_true", help="Validate without network publication.")
    parser.add_argument("--output", type=Path, help="Optional sanitized local audit trace.")
    parser.add_argument("--interval", type=float, default=0.0, help="Seconds between publications.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of demo cycles.")
    parser.add_argument("--follow", action="store_true", help="Continuously publish complete appended records.")
    parser.add_argument("--checkpoint", type=Path, help="Required durable delivery state for --follow.")
    parser.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between follow polls.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Relay events and report failure with a nonzero exit status."""
    parser = create_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.interval) or args.interval < 0 or args.iterations < 1:
        parser.error("interval must be finite and nonnegative; iterations must be positive")
    if args.input and args.iterations != 1:
        parser.error("--iterations is only supported with --demo")
    if args.follow and (not args.input or not args.checkpoint or args.interval):
        parser.error("--follow requires --input and --checkpoint; use --poll-interval instead of --interval")
    if args.checkpoint and not args.follow:
        parser.error("--checkpoint requires --follow")
    if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
        parser.error("--poll-interval must be finite and positive")
    if args.output and args.input and any(
        args.output.resolve() == path.resolve() or (
            args.output.exists() and path.exists() and args.output.samefile(path)
        ) for path in args.input
    ):
        parser.error("audit output must differ from every input file")
    if args.follow:
        paths = [*args.input, args.checkpoint,
                 args.checkpoint.with_suffix(args.checkpoint.suffix + ".lock"),
                 args.checkpoint.with_suffix(args.checkpoint.suffix + ".tmp")]
        if args.output:
            paths.append(args.output)
        for index, path in enumerate(paths):
            if any(path.resolve() == other.resolve() or (
                path.exists() and other.exists() and path.samefile(other)
            ) for other in paths[index + 1:]):
                parser.error("inputs, audit output, checkpoint and checkpoint sidecars must be separate files")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sink = None
    exit_code = 0
    try:
        sink = FabricEventstreamSink(
            dry_run=not args.live_fabric, fallback_jsonl_path=args.output
        )
        if args.follow:
            with JsonlFollower(args.input, args.checkpoint, dry_run=sink.dry_run) as follower:
                logger.info("Following %d append-only event file(s)", len(args.input))
                retries = 0
                while True:
                    try:
                        count = follower.poll_once(sink.publish)
                    except SinkUnavailableError:
                        if retries >= 5:
                            raise
                        delay = 2 ** retries
                        retries += 1
                        logger.warning("Publication unavailable; retry %d/5 in %d seconds", retries, delay)
                        time.sleep(delay)
                        continue
                    retries = 0
                    if count:
                        logger.info("%s %d events", "Validated" if sink.dry_run else "Published", count)
                    time.sleep(args.poll_interval)
        published = 0
        demo_start = datetime.now(UTC) - timedelta(seconds=29 * args.iterations - 1)
        for iteration in range(args.iterations):
            events = (
                generate_scenario_events(demo_start + timedelta(seconds=29 * iteration))
                if args.demo
                else read_events(args.input)
            )
            for event in events:
                if args.interval and published:
                    time.sleep(args.interval)
                sink.publish(event)
                published += 1
        logger.info("%s %d events", "Validated" if sink.dry_run else "Published", published)
    except SinkError as error:
        logger.error("Relay failed: %s", error)
        exit_code = 1
    except (OSError, UnicodeError):
        logger.error("Relay failed; verify input data, file access and Fabric configuration.")
        exit_code = 1
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        if sink is not None:
            try:
                sink.close()
            except (SinkError, OSError):
                logger.error("Fabric client cleanup failed.")
                if exit_code == 0:
                    exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
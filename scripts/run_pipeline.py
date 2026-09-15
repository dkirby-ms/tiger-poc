#!/usr/bin/env python3
"""Run the deterministic Tiger process-event pipeline from strict YAML config."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from tiger_poc.config import (
    FabricEventstreamDestination,
    LocalJsonlDestination,
    PipelineConfig,
    load_config,
)
from tiger_poc.connectors import LocalSinkConnector, TwinConnector
from tiger_poc.connectors.fabric_eventstream import FabricEventstreamConnector
from tiger_poc.delivery import OutboxPublisher, OverflowPolicy, SQLiteMapperStateStore
from tiger_poc.ontology.event import ProcessEvent
from tiger_poc.ontology.mapper import ProcessStateMapper
from tiger_poc.ontology.state import InMemoryMapperStateStore, MapperStateStore
from tiger_poc.perception import Observation, PerceptionWorkload

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2


@dataclass(frozen=True, slots=True)
class FixtureFrame:
    """Represent one deterministic frame-level process-state reading."""

    state: str
    observed_at: datetime
    confidence: float


class FixturePerceptionWorkload:
    """Convert deterministic fixture frames into the stable observation contract."""

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    @property
    def runtime(self) -> str:
        """Return the configured inference runtime."""
        return self._config.inference.runtime

    def observe(self, frame: FixtureFrame) -> list[Observation]:
        """Create one observation for a fixture frame."""
        return [
            Observation(
                subject_id=self._config.source.subject_id,
                observation_type="process-state",
                value=frame.state,
                timestamp=frame.observed_at,
                confidence=frame.confidence,
                source=self.runtime,
            )
        ]

    def reset(self) -> None:
        """Reset fixture state; this workload is stateless."""


def load_fixture_frames(path: str | Path) -> list[FixtureFrame]:
    """Load deterministic fixture frames after configuration validation succeeds."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fixture source must contain a JSON array")
    return [
        FixtureFrame(
            state=str(item["state"]),
            observed_at=datetime.fromisoformat(str(item["observedAt"]).replace("Z", "+00:00")),
            confidence=float(item["confidence"]),
        )
        for item in payload
        if isinstance(item, dict)
    ]


def build_connector(config: PipelineConfig) -> TwinConnector:
    """Build the selected connector after config and environment validation."""
    if isinstance(config.destination, LocalJsonlDestination):
        return LocalSinkConnector(config.destination.path)
    destination = config.destination
    if destination.authentication == "connection-string":
        variable_name = destination.connection_string_env
        if variable_name is None:
            raise ValueError("connection-string authentication is missing its environment name")
        return FabricEventstreamConnector.from_connection_string(os.environ[variable_name])
    namespace_name = destination.fully_qualified_namespace_env
    event_hub_name = destination.event_hub_name_env
    if namespace_name is None or event_hub_name is None:
        raise ValueError("managed-identity authentication is missing environment names")
    return FabricEventstreamConnector.from_entra(
        os.environ[namespace_name],
        os.environ[event_hub_name],
    )


def run_pipeline(
    config: PipelineConfig,
    frames: Iterable[FixtureFrame],
    *,
    workload: PerceptionWorkload[FixtureFrame] | None = None,
    connector: TwinConnector | None = None,
    state_store: MapperStateStore | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    event_id_factory: Callable[[], UUID] = uuid4,
) -> list[ProcessEvent]:
    """Map and publish deterministic frames through injected pipeline boundaries."""
    selected_workload = workload or FixturePerceptionWorkload(config)
    owns_store = False
    if (
        state_store is None
        and connector is None
        and isinstance(config.destination, FabricEventstreamDestination)
    ):
        selected_store: MapperStateStore = SQLiteMapperStateStore(
            config.destination.outbox.path,
            max_bytes=config.destination.outbox.max_bytes,
            max_age=timedelta(hours=config.destination.outbox.max_age_hours),
            overflow_policy=OverflowPolicy.REJECT,
        )
        selected_connector: TwinConnector = OutboxPublisher(
            selected_store.outbox,  # type: ignore[attr-defined]
            build_connector(config),
        )
        owns_store = True
    else:
        selected_store = state_store or InMemoryMapperStateStore()
        selected_connector = connector or build_connector(config)
    owns_connector = connector is None
    mapper = ProcessStateMapper(
        site_id=config.source.site_id,
        device_id=config.source.device_id,
        ontology_version=config.ontology.version,
        model=config.inference.model,
        confidence_threshold=config.ontology.confidence_threshold,
        consecutive_readings=config.ontology.consecutive_readings,
    )
    events: list[ProcessEvent] = []
    try:
        if isinstance(selected_connector, OutboxPublisher):
            selected_connector.drain()
        for frame in frames:
            for observation in selected_workload.observe(frame):
                state = selected_store.load(observation.subject_id)
                proposal = mapper.map(
                    observation,
                    state,
                    emitted_at=clock(),
                    event_id=event_id_factory(),
                )
                selected_store.commit(proposal)
                if proposal.event is not None:
                    selected_connector.publish(proposal.event)
                    events.append(proposal.event)
    finally:
        if owns_connector:
            selected_connector.close()
        if owns_store and isinstance(selected_store, SQLiteMapperStateStore):
            selected_store.close()
    return events


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("pipelines/fabric-eventstream.yaml"),
        help="Path to the strict pipeline YAML configuration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate configuration, load fixture input, and execute the pipeline."""
    args = create_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        frames = load_fixture_frames(config.source.path)
        events = run_pipeline(config, frames)
    except (OSError, ValueError, ValidationError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except Exception as error:
        print(f"Pipeline error: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(f"Published {len(events)} process event(s)")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())

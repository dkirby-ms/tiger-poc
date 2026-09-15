"""Strict versioned configuration and environment-secret boundaries."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class StrictConfigModel(BaseModel):
    """Reject unknown configuration fields throughout the manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class SourceConfig(StrictConfigModel):
    """Select a deterministic fixture or prerecorded source."""

    kind: Literal["fixture", "prerecorded"]
    path: Path
    site_id: NonEmptyString = Field(alias="siteId")
    device_id: NonEmptyString = Field(alias="deviceId")
    subject_id: NonEmptyString = Field(alias="subjectId")


class InferenceConfig(StrictConfigModel):
    """Describe replaceable inference metadata without runtime credentials."""

    mode: Literal["edge", "cloud"]
    runtime: NonEmptyString
    model: NonEmptyString


class OntologyConfig(StrictConfigModel):
    """Configure the narrow process-state mapper and debounce policy."""

    version: Literal["1.0"] = "1.0"
    mapper: Literal["line-monitoring"] = "line-monitoring"
    confidence_threshold: float = Field(alias="confidenceThreshold", ge=0.0, le=1.0)
    consecutive_readings: int = Field(alias="consecutiveReadings", ge=1)


class OutboxConfig(StrictConfigModel):
    """Bound the durable SQLite queue implemented in Phase 3."""

    kind: Literal["sqlite"] = "sqlite"
    path: Path
    max_bytes: int = Field(alias="maxBytes", gt=0)
    max_age_hours: int = Field(alias="maxAgeHours", gt=0)


class LocalJsonlDestination(StrictConfigModel):
    """Write canonical events to an append-only local JSON Lines file."""

    kind: Literal["local-jsonl"]
    path: Path


class FabricEventstreamDestination(StrictConfigModel):
    """Reference Fabric endpoint credentials by environment variable name."""

    kind: Literal["fabric-eventstream"]
    authentication: Literal["connection-string", "managed-identity"]
    connection_string_env: NonEmptyString | None = Field(alias="connectionStringEnv", default=None)
    fully_qualified_namespace_env: NonEmptyString | None = Field(
        alias="fullyQualifiedNamespaceEnv", default=None
    )
    event_hub_name_env: NonEmptyString | None = Field(alias="eventHubNameEnv", default=None)
    partition_key: Literal["subjectId"] = Field(alias="partitionKey", default="subjectId")
    outbox: OutboxConfig

    @model_validator(mode="after")
    def validate_authentication_references(self) -> FabricEventstreamDestination:
        """Require only the environment references needed by the auth mode."""
        if self.authentication == "connection-string":
            if self.connection_string_env is None:
                raise ValueError("connectionStringEnv is required for connection-string auth")
            if self.fully_qualified_namespace_env or self.event_hub_name_env:
                raise ValueError("namespace references are not valid for connection-string auth")
        elif self.fully_qualified_namespace_env is None or self.event_hub_name_env is None:
            raise ValueError(
                "fullyQualifiedNamespaceEnv and eventHubNameEnv are required for managed identity"
            )
        elif self.connection_string_env is not None:
            raise ValueError("connectionStringEnv is not valid for managed-identity auth")
        return self

    def required_environment_variables(self) -> tuple[str, ...]:
        """Return credential variable names without resolving or exposing values."""
        if self.authentication == "connection-string":
            return (self.connection_string_env,) if self.connection_string_env else ()
        return tuple(
            name
            for name in (self.fully_qualified_namespace_env, self.event_hub_name_env)
            if name is not None
        )


DestinationConfig = Annotated[
    LocalJsonlDestination | FabricEventstreamDestination,
    Field(discriminator="kind"),
]


class PipelineConfig(StrictConfigModel):
    """Compose one validated source, mapper, destination, and runtime mode."""

    schema_version: Literal[1] = Field(alias="schemaVersion")
    source: SourceConfig
    inference: InferenceConfig
    ontology: OntologyConfig
    destination: DestinationConfig

    def validate_environment(self, environ: Mapping[str, str]) -> None:
        """Reject missing credential variables without reading or reporting values."""
        if not isinstance(self.destination, FabricEventstreamDestination):
            return
        missing = [
            name
            for name in self.destination.required_environment_variables()
            if not environ.get(name)
        ]
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"required environment variables are not set: {names}")


def load_config(path: str | Path, *, environ: Mapping[str, str] | None = None) -> PipelineConfig:
    """Parse and fully validate YAML before any pipeline resource is opened."""
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pipeline configuration must contain a YAML object")
    config = PipelineConfig.model_validate(payload)
    config.validate_environment(os.environ if environ is None else environ)
    return config


__all__ = [
    "FabricEventstreamDestination",
    "InferenceConfig",
    "LocalJsonlDestination",
    "OntologyConfig",
    "OutboxConfig",
    "PipelineConfig",
    "SourceConfig",
    "load_config",
]

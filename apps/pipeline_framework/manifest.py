"""YAML manifest parsing and registry-aware graph validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .channel import OverflowPolicy
from .registry import StageDefinition, StageRegistry


class ManifestError(ValueError):
    """A pipeline cannot be constructed from the supplied manifest."""


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["inproc"] = "inproc"
    capacity: int = Field(default=8, gt=0)
    on_full: OverflowPolicy = OverflowPolicy.BLOCK
    sample_every: int = Field(default=2, gt=0)


class DefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: ChannelConfig = Field(default_factory=ChannelConfig)


class StageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    inputs: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    channel: ChannelConfig | None = None

    @field_validator("id", "type")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class PipelineMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class PipelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    stages: list[StageSpec] = Field(min_length=1)


class PipelineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["tiger.dev/v1"] = Field(alias="apiVersion")
    kind: Literal["Pipeline"]
    metadata: PipelineMetadata
    spec: PipelineSpec


@dataclass(frozen=True)
class LoadedStage:
    spec: StageSpec
    definition: StageDefinition
    config: BaseModel


@dataclass(frozen=True)
class LoadedPipeline:
    manifest: PipelineManifest
    stages: dict[str, LoadedStage]
    order: tuple[str, ...]


def load_pipeline(path: Path | str, registry: StageRegistry) -> LoadedPipeline:
    manifest_path = Path(path)
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = PipelineManifest.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ManifestError(str(error)) from error
    return validate_pipeline(manifest, registry)


def validate_pipeline(manifest: PipelineManifest, registry: StageRegistry) -> LoadedPipeline:
    specs: dict[str, StageSpec] = {}
    loaded: dict[str, LoadedStage] = {}
    for spec in manifest.spec.stages:
        if spec.id in specs:
            raise ManifestError(f"duplicate stage id '{spec.id}'")
        definition = registry.get(spec.type)
        if definition is None:
            raise ManifestError(f"stage '{spec.id}' uses unknown type '{spec.type}'")
        try:
            config = registry.validate_config(spec.type, spec.config)
        except ValidationError as error:
            raise ManifestError(f"invalid config for stage '{spec.id}': {error}") from error
        specs[spec.id] = spec
        loaded[spec.id] = LoadedStage(spec, definition, config)

    sources = [item for item in loaded.values() if item.definition.source]
    if len(sources) != 1:
        raise ManifestError("a pipeline must contain exactly one source stage")

    for stage_id, item in loaded.items():
        if item.definition.source:
            if item.spec.inputs:
                raise ManifestError(f"source stage '{stage_id}' cannot declare inputs")
            continue
        if len(item.spec.inputs) != 1:
            raise ManifestError(f"stage '{stage_id}' must declare exactly one input")
        upstream_id = item.spec.inputs[0]
        if upstream_id not in loaded:
            raise ManifestError(f"stage '{stage_id}' references unknown input '{upstream_id}'")
        _validate_types(loaded[upstream_id], item)

    order = _topological_order(loaded)
    source_id = sources[0].spec.id
    reachable = _reachable_from(source_id, loaded)
    unreachable = sorted(set(loaded) - reachable)
    if unreachable:
        raise ManifestError(f"unreachable stages: {', '.join(unreachable)}")
    return LoadedPipeline(manifest=manifest, stages=loaded, order=tuple(order))


def _validate_types(upstream: LoadedStage, downstream: LoadedStage) -> None:
    emitted = upstream.definition.emits
    accepted = downstream.definition.accepts
    if emitted is None:
        raise ManifestError(f"sink stage '{upstream.spec.id}' cannot have downstream stages")
    if accepted is None or not issubclass(emitted, accepted):
        raise ManifestError(
            f"stage '{downstream.spec.id}' does not accept output from '{upstream.spec.id}'"
        )


def _topological_order(stages: dict[str, LoadedStage]) -> list[str]:
    indegree = {stage_id: len(item.spec.inputs) for stage_id, item in stages.items()}
    downstream: dict[str, list[str]] = {stage_id: [] for stage_id in stages}
    for stage_id, item in stages.items():
        for upstream_id in item.spec.inputs:
            if upstream_id in downstream:
                downstream[upstream_id].append(stage_id)
    ready = [stage_id for stage_id, degree in indegree.items() if degree == 0]
    order: list[str] = []
    while ready:
        stage_id = ready.pop(0)
        order.append(stage_id)
        for child_id in downstream[stage_id]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                ready.append(child_id)
    if len(order) != len(stages):
        raise ManifestError("pipeline graph contains a cycle")
    return order


def _reachable_from(source_id: str, stages: dict[str, LoadedStage]) -> set[str]:
    downstream: dict[str, list[str]] = {stage_id: [] for stage_id in stages}
    for stage_id, item in stages.items():
        for upstream_id in item.spec.inputs:
            if upstream_id in downstream:
                downstream[upstream_id].append(stage_id)
    reachable: set[str] = set()
    pending = [source_id]
    while pending:
        stage_id = pending.pop()
        if stage_id in reachable:
            continue
        reachable.add(stage_id)
        pending.extend(downstream[stage_id])
    return reachable
"""Validate a single local PerceptionWorkload without exposing secret values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .presence import PresencePolicy


class Settings(BaseModel):
    """Reject misspelled settings and implicit type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True,
                              allow_inf_nan=False)


class Metadata(Settings):
    """Stable deployment identity."""

    name: str = Field(min_length=1)
    plantName: str = Field(min_length=1)
    plantId: str = Field(min_length=1)


class Source(Settings):
    """Resolve connection details outside public configuration."""

    id: str = Field(min_length=1)
    type: Literal["rtsp", "replay"]
    uriFrom: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    subjectId: str = Field(min_length=1)


class Perception(Settings):
    """Local model and normalized detection selection."""

    provider: Literal["ultralytics", "qr"]
    model: str | None = Field(default=None, min_length=1)
    labels: list[str] = Field(default_factory=lambda: ["qr"], min_length=1)
    observationType: Literal["PalletPresent", "ObjectPresent", "BoxIdentified"]
    sampleEveryFrames: int = Field(ge=1)
    device: str = "cpu"
    imageSize: int = Field(default=640, ge=32, le=1920)
    threads: int = Field(default=2, ge=1, le=32)

    @model_validator(mode="after")
    def validate_labels(self) -> Perception:
        """Prevent a household surrogate from claiming pallet detection."""
        if self.provider == "qr":
            if self.model is not None or self.labels != ["qr"] or self.observationType != "BoxIdentified":
                raise ValueError("QR workloads require BoxIdentified, qr labels, and no model")
        elif self.model is None or self.observationType == "BoxIdentified":
            raise ValueError("YOLO workloads require a model and a presence observation type")
        if any(not label.strip() for label in self.labels):
            raise ValueError("labels must be non-empty")
        if self.observationType == "PalletPresent" and self.labels != ["pallet"]:
            raise ValueError("PalletPresent requires the pallet label")
        return self


class Region(Settings):
    """Normalized rectangle and inclusive box-center criterion."""

    coordinates: Literal["normalized-xyxy"]
    bounds: list[float] = Field(min_length=4, max_length=4)
    matching: Literal["box-center"]


class Presence(Settings):
    """Confirmation windows and evidence freshness limits in seconds."""

    confidence: float = Field(ge=0, le=1)
    occupiedSeconds: float = Field(ge=0)
    emptySeconds: float = Field(ge=0)
    staleSeconds: float = Field(gt=0)


class Capture(Settings):
    """Conservative image usability and bounded network-read settings."""

    timeoutMilliseconds: int = Field(default=1500, ge=100, le=10000)
    minBrightness: float = Field(default=5.0, ge=0, le=255)
    maxBrightness: float = Field(default=250.0, ge=0, le=255)
    minContrast: float = Field(default=2.0, ge=0, le=128)

    @model_validator(mode="after")
    def validate_brightness(self) -> Capture:
        """Ensure at least one usable brightness value exists."""
        if self.minBrightness >= self.maxBrightness:
            raise ValueError("minBrightness must be lower than maxBrightness")
        return self


class Destination(Settings):
    """Independent local event and live-view outputs."""

    connector: Literal["local-jsonl"]
    path: str = Field(min_length=1)
    statusPath: str = Field(min_length=1)


class Spec(Settings):
    """One camera and one monitored position per process."""

    source: Source
    perception: Perception
    region: Region
    presence: Presence
    destination: Destination
    capture: Capture = Field(default_factory=Capture)


class Workload(Settings):
    """The local subset of the versioned PerceptionWorkload manifest."""

    apiVersion: Literal["tiger.microsoft.com/v1alpha1"]
    kind: Literal["PerceptionWorkload"]
    metadata: Metadata
    spec: Spec

    def policy(self) -> PresencePolicy:
        """Translate validated settings into the provider-independent rule."""
        settings = self.spec.presence
        return PresencePolicy(tuple(self.spec.region.bounds), tuple(self.spec.perception.labels),
                              settings.confidence, settings.occupiedSeconds,
                              settings.emptySeconds, settings.staleSeconds)


def load_workload(path: Path) -> Workload:
    """Load YAML; resolve file paths relative to the manifest, never the cwd."""
    try:
        workload = Workload.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        workload.policy()
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors())
        raise ValueError(f"Invalid manifest fields: {fields}") from None
    except (yaml.YAMLError, OSError):
        raise ValueError("Cannot read manifest; check file access and YAML syntax") from None
    for owner, field in ((workload.spec.perception, "model"),
                         (workload.spec.destination, "path"),
                         (workload.spec.destination, "statusPath")):
        if getattr(owner, field) is not None:
            setattr(owner, field, str((path.resolve().parent / getattr(owner, field)).resolve()))
    outputs = {workload.spec.destination.path, workload.spec.destination.statusPath,
               str(Path(workload.spec.destination.statusPath).with_suffix(".jpg"))}
    if len(outputs) != 3 or workload.spec.perception.model in outputs or str(path.resolve()) in outputs:
        raise ValueError("Event, status, preview, model, and manifest paths must differ")
    return workload


def resolve_source(source: Source) -> str:
    """Return a private connection value, raising only a redacted error."""
    value = os.environ.get(source.uriFrom, "").strip()
    if not value:
        raise ValueError(f"Set the camera reference {source.uriFrom} privately")
    if source.type == "rtsp" and not value.startswith(("rtsp://", "rtsps://")):
        raise ValueError("Camera reference must resolve to an RTSP URL")
    if source.type == "replay" and not Path(value).is_file():
        raise ValueError("Replay reference must resolve to an existing local video")
    return value
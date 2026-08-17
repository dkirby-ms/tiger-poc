"""Interoperable payload types used by built-in pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class Frame:
    image: Image.Image
    source: str


@dataclass(frozen=True)
class PreparedFrame:
    image: Image.Image
    original_width: int
    original_height: int
    scale: float
    pad_x: int
    pad_y: int


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectionSet:
    detections: tuple[Detection, ...]
    model_id: str


@dataclass(frozen=True)
class RuleEvaluation:
    rule: str
    matched: bool
    detections: tuple[Detection, ...]


@dataclass(frozen=True)
class Event:
    event_type: str
    stream_id: str
    started_at: float
    occurred_at: float
    detections: tuple[Detection, ...]
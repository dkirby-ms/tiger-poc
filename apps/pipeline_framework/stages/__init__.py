"""Built-in stage registration."""

from __future__ import annotations

from apps.pipeline_framework.payloads import (
    DetectionSet,
    Event,
    Frame,
    PreparedFrame,
    RuleEvaluation,
)
from apps.pipeline_framework.registry import StageRegistry

from .file_source import FileSource, FileSourceConfig
from .foundry import LocalFoundryInference, LocalFoundryInferenceConfig
from .jsonl_sink import JsonlSink, JsonlSinkConfig
from .letterbox import Letterbox, LetterboxConfig
from .rtsp_source import RtspSource, RtspSourceConfig
from .rules import DwellRule, DwellRuleConfig, ThresholdRule, ThresholdRuleConfig


def built_in_registry() -> StageRegistry:
    registry = StageRegistry()
    registry.register(
        "source.file",
        FileSource,
        FileSourceConfig,
        accepts=None,
        emits=Frame,
        source=True,
    )
    registry.register(
        "source.rtsp",
        RtspSource,
        RtspSourceConfig,
        accepts=None,
        emits=Frame,
        source=True,
    )
    registry.register(
        "transform.letterbox",
        Letterbox,
        LetterboxConfig,
        accepts=Frame,
        emits=PreparedFrame,
    )
    registry.register(
        "infer.foundry.local",
        LocalFoundryInference,
        LocalFoundryInferenceConfig,
        accepts=PreparedFrame,
        emits=DetectionSet,
    )
    registry.register(
        "rule.threshold",
        ThresholdRule,
        ThresholdRuleConfig,
        accepts=DetectionSet,
        emits=RuleEvaluation,
    )
    registry.register(
        "rule.dwell",
        DwellRule,
        DwellRuleConfig,
        accepts=RuleEvaluation,
        emits=Event,
    )
    registry.register(
        "sink.jsonl",
        JsonlSink,
        JsonlSinkConfig,
        accepts=Event,
        emits=None,
    )
    return registry


__all__ = ["built_in_registry"]
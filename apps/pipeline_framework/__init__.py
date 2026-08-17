"""Composable local video pipeline framework."""

from .channel import ChannelStats, InProcChannel, OverflowPolicy, SendResult
from .contracts import Envelope, StageContext, StageHealth
from .manifest import LoadedPipeline, ManifestError, load_pipeline
from .payloads import Detection, DetectionSet, Event, Frame, PreparedFrame, RuleEvaluation
from .registry import StageRegistry
from .runner import PipelineRunner, RunnerResult

__all__ = [
    "ChannelStats",
    "Detection",
    "DetectionSet",
    "Envelope",
    "Event",
    "Frame",
    "InProcChannel",
    "LoadedPipeline",
    "ManifestError",
    "OverflowPolicy",
    "PipelineRunner",
    "PreparedFrame",
    "RuleEvaluation",
    "RunnerResult",
    "SendResult",
    "StageContext",
    "StageHealth",
    "StageRegistry",
    "load_pipeline",
]
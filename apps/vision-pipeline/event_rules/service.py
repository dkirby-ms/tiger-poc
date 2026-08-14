"""Filter raw detections using confidence and dwell-time event rules."""

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from fastapi import FastAPI
from pydantic import BaseModel


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventRuleConfig:
    """Configuration for the event-rules engine."""

    confidence_threshold: float = 0.75
    dwell_time_seconds: float = 1.0
    cooldown_seconds: float = 10.0
    allowed_zones: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> "EventRuleConfig":
        """Load configuration from environment variables."""
        source = os.environ if env is None else env
        confidence_threshold = float(source.get("EVENT_RULES_CONFIDENCE", "0.75"))
        dwell_time_seconds = float(source.get("EVENT_RULES_DWELL_TIME", "1.0"))
        cooldown_seconds = float(source.get("EVENT_RULES_COOLDOWN_SECONDS", "10.0"))
        allowed_zones_str = source.get("EVENT_RULES_ALLOWED_ZONES", "")
        allowed_zones = tuple(z.strip() for z in allowed_zones_str.split(",") if z.strip()) if allowed_zones_str else ()
        
        return cls(
            confidence_threshold=confidence_threshold,
            dwell_time_seconds=dwell_time_seconds,
            cooldown_seconds=cooldown_seconds,
            allowed_zones=allowed_zones,
        )


def _coerce_detection(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict"):
        value = item.to_dict()
        if isinstance(value, dict):
            return value
    raise TypeError(f"Unsupported detection item: {type(item)!r}")


def apply_event_rules(
    detections: Iterable[Any],
    config: EventRuleConfig | None = None,
) -> list[dict[str, Any]]:
    """Return only detections that satisfy the configured event thresholds."""

    rule_config = config or EventRuleConfig()
    results: list[dict[str, Any]] = []

    for item in detections:
        detection = _coerce_detection(item)
        confidence = float(detection.get("confidence", 0.0))
        dwell_time = float(detection.get("dwell_time_seconds", 0.0))
        zone = detection.get("zone")

        if confidence < rule_config.confidence_threshold:
            continue
        if dwell_time < rule_config.dwell_time_seconds:
            continue
        if rule_config.allowed_zones and zone not in rule_config.allowed_zones:
            continue

        results.append(detection)

    return results


class EventRuleEngine:
    """Apply event rules and suppress repeated events during a cooldown."""

    def __init__(
        self,
        config: EventRuleConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or EventRuleConfig()
        self.clock = clock
        self._last_emitted: dict[tuple[str, str], float] = {}

    def filter(self, detections: Iterable[Any], source_id: str | None = None) -> list[dict[str, Any]]:
        """Return eligible detections that are not in their cooldown window."""
        eligible = apply_event_rules(detections, self.config)
        now = self.clock()
        emitted: list[dict[str, Any]] = []

        for detection in eligible:
            key = (source_id or detection.get("source_id") or "unknown", str(detection.get("label", "unknown")))
            last_emitted = self._last_emitted.get(key)
            if (
                self.config.cooldown_seconds > 0
                and last_emitted is not None
                and now - last_emitted < self.config.cooldown_seconds
            ):
                continue
            self._last_emitted[key] = now
            emitted.append(detection)

        return emitted


class DetectionListRequest(BaseModel):
    """Request payload for event rules filtering."""

    detections: list[dict[str, Any]]
    source_id: str | None = None


class FilteredDetectionsResponse(BaseModel):
    """Response from event rules filtering."""

    detections: list[dict[str, Any]]
    filtered_count: int
    matched_count: int


def create_app(rule_config: EventRuleConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Event Rules", version="0.1.0")
    engine = EventRuleEngine(rule_config)
    
    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "confidence_threshold": rule_config.confidence_threshold,
            "dwell_time_seconds": rule_config.dwell_time_seconds,
            "cooldown_seconds": rule_config.cooldown_seconds,
            "allowed_zones": rule_config.allowed_zones,
        }
    
    @app.post("/filter")
    def filter_detections(request: DetectionListRequest) -> FilteredDetectionsResponse:
        """Apply event rules to a list of detections."""
        logger.info(f"Filtering {len(request.detections)} detections from {request.source_id}")
        
        filtered = engine.filter(request.detections, request.source_id)
        
        logger.info(f"Filtered to {len(filtered)} detections")
        return FilteredDetectionsResponse(
            detections=filtered,
            filtered_count=len(request.detections),
            matched_count=len(filtered),
        )
    
    return app


def main() -> None:
    """Run the event rules server."""
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Event Rules server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("EVENT_RULES_PORT", "8082")),
        help="Port to listen on",
    )
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = EventRuleConfig.from_environment()
    logger.info(f"Starting Event Rules with config: {config}")
    
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

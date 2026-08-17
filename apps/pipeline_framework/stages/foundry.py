"""Readiness-gated inference through the local Foundry deployment runtime."""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.local_model_runtime import LocalFoundryDeploymentRuntime
from apps.pipeline_framework.contracts import Envelope, StageBase, StageContext, StageHealth
from apps.pipeline_framework.payloads import Detection, DetectionSet, PreparedFrame


class LocalFoundryInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    confidence_threshold: float = Field(default=0.35, ge=0, le=1)


class LocalFoundryInference(StageBase):
    def __init__(self, config: LocalFoundryInferenceConfig) -> None:
        super().__init__()
        self._config = config
        self._runtime: Any = None
        self._deployment: Any = None

    async def setup(self, context: StageContext) -> None:
        await super().setup(context)
        self._runtime = context.services.get("foundry") or LocalFoundryDeploymentRuntime()
        self._deployment = next(
            (
                deployment
                for deployment in self._runtime.list_deployments()
                if deployment.model_id == self._config.model_id
            ),
            None,
        )
        if self._deployment is None:
            self._health = StageHealth(False, f"unknown model '{self._config.model_id}'")
            raise ValueError(self._health.message)
        if not self._deployment.ready:
            self._health = StageHealth(False, f"model '{self._config.model_id}' is not ready")
            raise RuntimeError(self._health.message)

    async def process(
        self, envelope: Envelope[PreparedFrame]
    ) -> AsyncIterator[Envelope[DetectionSet]]:
        encoded = await asyncio.to_thread(_encode_jpeg, envelope.payload.image)
        result = await asyncio.to_thread(
            self._runtime.dispatch,
            self._deployment.model_id,
            self._deployment.route,
            self._deployment.secret,
            {
                "items": [
                    {
                        "content_type": "image/jpeg",
                        "encoder": "base64",
                        "data": encoded,
                    }
                ],
                "confidence_threshold": self._config.confidence_threshold,
            },
        )
        if result["status"] != "ok":
            self._health = StageHealth(False, result["status"])
            raise RuntimeError(f"model '{self._config.model_id}' returned {result['status']}")
        detections = tuple(
            _detection_from_response(item, envelope.payload)
            for item in result["response"].get("predictions", [[]])[0]
        )
        yield envelope.derive(DetectionSet(detections, self._config.model_id))


def _encode_jpeg(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _detection_from_response(item: dict[str, Any], frame: PreparedFrame) -> Detection:
    box = item["box"]
    x1 = max(0.0, min(frame.original_width, (float(box["x1"]) - frame.pad_x) / frame.scale))
    y1 = max(0.0, min(frame.original_height, (float(box["y1"]) - frame.pad_y) / frame.scale))
    x2 = max(0.0, min(frame.original_width, (float(box["x2"]) - frame.pad_x) / frame.scale))
    y2 = max(0.0, min(frame.original_height, (float(box["y2"]) - frame.pad_y) / frame.scale))
    return Detection(item["label"], float(item["confidence"]), (x1, y1, x2, y2))
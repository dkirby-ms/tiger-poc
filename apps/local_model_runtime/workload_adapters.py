"""Response and payload adapters, one per workload type.

Adapters are keyed by workload, not by model, so every predictive service
shares one adapter and every generative service shares another.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from .bundle_registry import resolve_bundle_path
from .model_service import WORKLOAD_PROFILES, WorkloadType

# Predictive models with an ONNX Runtime inference path. Other predictive
# bundles (e.g. florence-2, format "transformers") still return a contract-only
# stub until they gain a runtime adapter of their own.
ONNX_INFERENCE_MODELS = frozenset({"yolo"})


@dataclass(frozen=True)
class PayloadError:
    """A contract violation in a request payload."""

    message: str
    param: Optional[str] = None
    type: str = "invalid_request_error"


def _deterministic_id(prefix: str, model_id: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(f"{model_id}:{sorted(payload)}".encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"


class WorkloadAdapter:
    """Payload contract and response shape for one workload type."""

    workload_type: WorkloadType

    def validate(self, payload: Mapping[str, Any]) -> Optional[PayloadError]:
        profile = WORKLOAD_PROFILES[self.workload_type]
        missing = sorted(profile.required_fields - set(payload))
        if missing:
            return PayloadError(
                message=f"Missing required field '{missing[0]}' for a {self.workload_type.value} request",
                param=missing[0],
            )
        rejected = sorted(profile.rejected_fields & set(payload))
        if rejected:
            return PayloadError(
                message=f"Field '{rejected[0]}' is not accepted by a {self.workload_type.value} request",
                param=rejected[0],
            )
        return None

    def build_response(self, model_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class PredictiveAdapter(WorkloadAdapter):
    """`/v1/predict` contract for detection-style models."""

    workload_type = WorkloadType.PREDICTIVE

    def validate(self, payload: Mapping[str, Any]) -> Optional[PayloadError]:
        error = super().validate(payload)
        if error is not None:
            return error

        items = payload["items"]
        if not isinstance(items, list) or not items:
            return PayloadError(message="'items' must be a non-empty array", param="items")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                return PayloadError(message="Each item must be an object", param=f"items[{index}]")
            for field, expected in (
                ("content_type", "image/jpeg"),
                ("encoder", "base64"),
            ):
                if item.get(field) != expected:
                    return PayloadError(
                        message=f"'{field}' must be '{expected}'",
                        param=f"items[{index}].{field}",
                    )
            if not isinstance(item.get("data"), str) or not item["data"]:
                return PayloadError(
                    message="'data' must be a non-empty string",
                    param=f"items[{index}].data",
                )

        threshold = payload.get("confidence_threshold")
        if threshold is not None:
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
                return PayloadError(
                    message="'confidence_threshold' must be a number",
                    param="confidence_threshold",
                )
            if not 0.0 <= float(threshold) <= 1.0:
                return PayloadError(
                    message="'confidence_threshold' must be between 0 and 1",
                    param="confidence_threshold",
                )
        return None

    def build_response(self, model_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        threshold = payload.get("confidence_threshold")
        return {
            "id": _deterministic_id("pred", model_id, payload),
            "object": "prediction",
            "created": int(time.time()),
            "model": model_id,
            "predictions": [
                self._predict(model_id, item["data"], threshold)
                for item in payload["items"]
            ],
            "usage": {"images": len(payload["items"])},
        }

    def _predict(
        self, model_id: str, image: str, threshold: Any
    ) -> List[Dict[str, Any]]:
        if model_id not in ONNX_INFERENCE_MODELS:
            return []
        model_path = resolve_bundle_path(model_id)
        if model_path is None:
            return []

        from .yolo_inference import DEFAULT_CONFIDENCE_THRESHOLD, run_yolo_inference

        confidence = float(threshold or DEFAULT_CONFIDENCE_THRESHOLD)
        return run_yolo_inference(image, model_path, confidence_threshold=confidence)


class GenerativeAdapter(WorkloadAdapter):
    """OpenAI-compatible `/v1/chat/completions` contract."""

    workload_type = WorkloadType.GENERATIVE

    def validate(self, payload: Mapping[str, Any]) -> Optional[PayloadError]:
        error = super().validate(payload)
        if error is not None:
            return error

        messages = payload["messages"]
        if not isinstance(messages, list) or not messages:
            return PayloadError(message="'messages' must be a non-empty array", param="messages")
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                return PayloadError(
                    message="Each message must be an object", param=f"messages[{index}]"
                )
            for required in ("role", "content"):
                if required not in message:
                    return PayloadError(
                        message=f"Message is missing '{required}'",
                        param=f"messages[{index}].{required}",
                    )
        return None

    def build_response(self, model_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = list(payload["messages"])
        prompt_tokens = sum(len(str(message.get("content", "")).split()) for message in messages)
        content = (
            f"Contract response from {model_id}. This service validates the "
            f"chat-completions contract and does not yet run model weights."
        )
        completion_tokens = len(content.split())
        return {
            "id": _deterministic_id("chatcmpl", model_id, payload),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


ADAPTERS: Dict[WorkloadType, WorkloadAdapter] = {
    WorkloadType.PREDICTIVE: PredictiveAdapter(),
    WorkloadType.GENERATIVE: GenerativeAdapter(),
}


def adapter_for(workload_type: WorkloadType) -> WorkloadAdapter:
    return ADAPTERS[workload_type]

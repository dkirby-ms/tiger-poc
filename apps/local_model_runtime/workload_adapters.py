"""Response and payload adapters, one per workload type.

Adapters are keyed by workload, not by model, so every predictive service
shares one adapter and every generative service shares another.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from .model_service import WORKLOAD_PROFILES, WorkloadType


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

        image = payload["image"]
        if not isinstance(image, str) or not image:
            return PayloadError(message="'image' must be a non-empty string", param="image")

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
        return {
            "id": _deterministic_id("pred", model_id, payload),
            "object": "prediction",
            "created": int(time.time()),
            "model": model_id,
            "predictions": [],
            "usage": {"images": 1},
        }


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

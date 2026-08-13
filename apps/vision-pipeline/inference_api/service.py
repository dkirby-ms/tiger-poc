"""Normalize local Foundry responses into a shared detection schema."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    """A normalized detection object used downstream by event rules and storage."""

    label: str
    confidence: float
    bbox: tuple[float, float, float, float]
    zone: str | None = None
    source_id: str | None = None
    model_id: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        model_id: str | None = None,
        source_id: str | None = None,
    ) -> "Detection":
        bbox = payload.get("bbox") or payload.get("box") or (0.0, 0.0, 0.0, 0.0)
        if isinstance(bbox, list):
            bbox = tuple(float(value) for value in bbox)
        if len(bbox) != 4:
            raise ValueError("Detection bbox must contain four values")
        return cls(
            label=str(payload.get("label") or payload.get("name") or "unknown"),
            confidence=float(payload.get("confidence", 0.0)),
            bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            zone=payload.get("zone"),
            source_id=source_id,
            model_id=model_id,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bbox"] = list(self.bbox)
        return data

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


class FrameInferenceRequest(BaseModel):
    """Request payload for frame inference."""

    frame_jpeg: bytes
    model_id: str = "yolo"
    source_id: str | None = None


class InferenceResponse(BaseModel):
    """Response from inference API."""

    source_id: str | None = None
    model_id: str
    detections: list[dict[str, Any]]


class PipelineFrameRequest(BaseModel):
    frame_jpeg: str
    clip_base64: str
    model_id: str = "yolo"
    source_id: str | None = None


def _call_foundry_local(model_id: str, foundry_url: str) -> list[dict[str, Any]]:
    """Call the Foundry Local inference endpoint and parse results."""
    try:
        response = requests.post(
            f"{foundry_url}/v1/chat/completions",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Analyze this image"}],
            },
            timeout=30,
        )
        response.raise_for_status()
        
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "[]")
        
        # Parse the JSON detections from the response
        try:
            detections = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse detections from Foundry response: {content}")
            detections = []
        
        return detections if isinstance(detections, list) else [detections]
    
    except requests.RequestException as e:
        logger.error(f"Failed to call Foundry Local at {foundry_url}: {e}")
        raise HTTPException(status_code=503, detail=f"Foundry inference failed: {str(e)}")


def create_app(
    foundry_url: str,
    event_rules_url: str = "http://event-rules:8082",
    local_store_url: str = "http://local-store:8083",
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Inference API", version="0.1.0")
    
    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {"status": "ok", "foundry_url": foundry_url}
    
    @app.post("/infer")
    def infer(request: FrameInferenceRequest) -> InferenceResponse:
        """Run inference on a frame using the specified model."""
        # Get raw detections from Foundry Local
        raw_detections = _call_foundry_local(request.model_id, foundry_url)
        
        # Normalize to Detection schema
        normalized: list[dict[str, Any]] = []
        for raw in raw_detections:
            try:
                detection = Detection.from_payload(
                    raw,
                    model_id=request.model_id,
                    source_id=request.source_id,
                )
                normalized.append(detection.to_dict())
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to normalize detection {raw}: {e}")
        
        return InferenceResponse(
            source_id=request.source_id,
            model_id=request.model_id,
            detections=normalized,
        )

    @app.post("/process")
    def process_frame(request: PipelineFrameRequest) -> dict[str, Any]:
        """Process a live frame through inference, rules, and local storage."""

        try:
            base64.b64decode(request.clip_base64, validate=True)
            detections = _call_foundry_local(request.model_id, foundry_url)
            normalized = [
                Detection.from_payload(
                    detection,
                    model_id=request.model_id,
                    source_id=request.source_id,
                ).to_dict()
                for detection in detections
            ]
            rules_response = requests.post(
                f"{event_rules_url}/filter",
                json={
                    "detections": [
                        {**detection, "dwell_time_seconds": 1.0}
                        for detection in normalized
                    ],
                    "source_id": request.source_id,
                },
                timeout=30,
            )
            rules_response.raise_for_status()
            matched = rules_response.json().get("detections", [])
            persisted = []
            for detection in matched:
                response = requests.post(
                    f"{local_store_url}/persist",
                    json={
                        "detection": detection,
                        "source_id": request.source_id,
                        "clip_base64": request.clip_base64,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                persisted.append(response.json())
            return {
                "source_id": request.source_id,
                "model_id": request.model_id,
                "detections": normalized,
                "matched_count": len(matched),
                "persisted": persisted,
            }
        except (ValueError, requests.RequestException) as error:
            raise HTTPException(status_code=502, detail=f"Pipeline processing failed: {error}")
    
    return app


def main() -> None:
    """Run the inference API server."""
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Inference API server")
    parser.add_argument(
        "--foundry-url",
        default=os.getenv("FOUNDRY_URL", "http://foundry-local:8000"),
        help="URL of the Foundry Local inference endpoint",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("INFERENCE_API_PORT", "8081")),
        help="Port to listen on",
    )
    parser.add_argument(
        "--event-rules-url",
        default=os.getenv("EVENT_RULES_URL", "http://event-rules:8082"),
    )
    parser.add_argument(
        "--local-store-url",
        default=os.getenv("LOCAL_STORE_URL", "http://local-store:8083"),
    )
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    logger.info(f"Starting Inference API, Foundry at {args.foundry_url}")
    
    app = create_app(args.foundry_url, args.event_rules_url, args.local_store_url)
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()


def _extract_detection_payload(response_payload: Any) -> list[dict[str, Any]]:
    if isinstance(response_payload, list):
        return [item for item in response_payload if isinstance(item, dict)]
    if not isinstance(response_payload, dict):
        return []

    if "detections" in response_payload and isinstance(response_payload["detections"], list):
        return [item for item in response_payload["detections"] if isinstance(item, dict)]
    return []


def _read_message_content(message: Any) -> Any:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            return content
    return None


def normalize_inference_response(
    payload: dict[str, Any],
    *,
    model_id: str | None = None,
    source_id: str | None = None,
) -> list[Detection]:
    """Normalize the first model response into a list of processed detections."""

    if not isinstance(payload, dict):
        return []

    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return []

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return []

    message = first_choice.get("message", {})
    content = _read_message_content(message)
    if content is None:
        return []

    parsed: Any = content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return []

    detections = _extract_detection_payload(parsed)
    return [
        Detection.from_payload(detection, model_id=model_id, source_id=source_id)
        for detection in detections
    ]

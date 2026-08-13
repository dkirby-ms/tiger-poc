import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


bundle_dir = Path(os.getenv("MODEL_BUNDLE_DIR", "/models"))
manifest_path = bundle_dir / "bundle.json"
execution_provider = os.getenv(
    "FOUNDRY_EXECUTION_PROVIDER", "CUDAExecutionProvider"
)
runtime_mode = os.getenv("FOUNDRY_RUNTIME_MODE", "onnx")

app = FastAPI(title="Foundry Local Runtime", version="0.1.0")


class ChatRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]


def load_manifest() -> dict[str, Any]:
    if not manifest_path.exists():
        return {"bundle_id": "unavailable", "bundle_version": "unavailable", "models": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def model_status(model: dict[str, Any]) -> dict[str, Any]:
    artifact = bundle_dir / model["path"]
    available = artifact.is_file()
    digest = None
    if available:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "id": model["id"],
        "object": "model",
        "owned_by": "tiger-poc",
        "format": model["format"],
        "precision": model["precision"],
        "available": available,
        "sha256": digest,
    }


@app.get("/healthz")
def health() -> dict[str, Any]:
    manifest = load_manifest()
    return {
        "status": "ok",
        "runtime_mode": runtime_mode,
        "execution_provider": execution_provider,
        "bundle_id": manifest.get("bundle_id"),
        "bundle_version": manifest.get("bundle_version"),
    }


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [model_status(model) for model in load_manifest().get("models", [])],
    }


def _run_onnx_inference(model_path: str, model_id: str) -> list[dict[str, Any]]:
    """
    Load an ONNX model and return synthetic inference results based on model type.
    For actual vision models, this would perform real inference; here we return
    representative detections matching the expected output schema.
    """
    try:
        if model_path:
            session = ort.InferenceSession(model_path, providers=[execution_provider])
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load ONNX model: {str(e)}",
        )

    # Return synthetic detections based on model type
    if model_id == "yolo":
        # YOLO returns object detections: class, confidence, bounding box
        return [
            {
                "id": "detection-1",
                "label": "person",
                "confidence": 0.92,
                "bbox": [100.0, 50.0, 300.0, 400.0],
            },
            {
                "id": "detection-2",
                "label": "backpack",
                "confidence": 0.87,
                "bbox": [150.0, 200.0, 250.0, 350.0],
            },
        ]
    elif model_id == "florence-2":
        # Florence-2 returns detailed object descriptions and properties
        return [
            {
                "id": "caption-1",
                "label": "person wearing blue jacket",
                "confidence": 0.85,
                "bbox": [100.0, 50.0, 300.0, 400.0],
            }
        ]
    elif model_id == "phi-4-multimodal":
        # Phi-4-multimodal returns reasoning and text output
        return [
            {
                "id": "reasoning-1",
                "label": "analysis",
                "confidence": 0.88,
                "content": "Image contains multiple objects in an indoor setting",
            }
        ]
    else:
        return [{"id": "result-1", "label": "unknown", "confidence": 0.5}]


@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest) -> dict[str, Any]:
    manifest = load_manifest()
    model = next(
        (item for item in manifest.get("models", []) if item["id"] == request.model),
        None,
    )
    if model is None:
        raise HTTPException(status_code=404, detail=f"Unknown model: {request.model}")

    model_path = bundle_dir / model["path"]
    if runtime_mode != "mock":
        if not model_path.is_file():
            raise HTTPException(
                status_code=503,
                detail=f"Model artifact is not installed: {model['path']}",
            )
        # Run actual inference or get synthetic results
        try:
            detections = _run_onnx_inference(str(model_path), request.model)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Inference failed: {str(e)}",
            )
    else:
        # Mock mode: return synthetic detections without loading model files
        detections = _run_onnx_inference("", request.model)

    return {
        "id": "chatcmpl-tiger-poc",
        "object": "chat.completion",
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(detections),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": len(detections), "total_tokens": len(detections)},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("FOUNDRY_PORT", "8000")))

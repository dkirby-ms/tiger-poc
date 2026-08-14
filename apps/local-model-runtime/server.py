import hashlib
import json
import os
import base64
from pathlib import Path
from typing import Any

import cv2
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
    image_base64: str | None = None


def load_manifest() -> dict[str, Any]:
    if not manifest_path.exists():
        return {"bundle_id": "unavailable", "bundle_version": "unavailable", "models": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def model_status(model: dict[str, Any]) -> dict[str, Any]:
    artifact = bundle_dir / model["path"]
    available = artifact.is_file() or artifact.is_dir()
    digest = None
    if available:
        if artifact.is_file():
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


def _run_onnx_inference(model_path: str, model_id: str, image_bytes: bytes) -> list[dict[str, Any]]:
    if model_id != "yolo":
        raise HTTPException(
            status_code=501,
            detail=f"ONNX post-processing is not implemented for model {model_id}",
        )

    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="image_base64 is not a valid image")

    try:
        session = ort.InferenceSession(model_path, providers=[execution_provider])
        input_info = session.get_inputs()[0]
        input_shape = input_info.shape
        input_height = int(input_shape[2] or 640)
        input_width = int(input_shape[3] or 640)
        resized = cv2.resize(image, (input_width, input_height))
        tensor = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]
        output = session.run(None, {input_info.name: tensor})[0]
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"ONNX inference failed: {error}") from error

    predictions = np.asarray(output)
    if predictions.ndim == 3:
        predictions = predictions[0]
    if predictions.ndim != 2:
        raise HTTPException(status_code=500, detail="Unsupported YOLO output shape")
    if predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.transpose()

    detections: list[dict[str, Any]] = []
    for prediction in predictions:
        if prediction.shape[0] < 6:
            continue
        class_scores = prediction[4:]
        class_index = int(np.argmax(class_scores))
        confidence = float(class_scores[class_index])
        if confidence < 0.25:
            continue
        center_x, center_y, width, height = map(float, prediction[:4])
        detections.append(
            {
                "label": str(class_index),
                "confidence": confidence,
                "bbox": [
                    (center_x - width / 2) / input_width,
                    (center_y - height / 2) / input_height,
                    (center_x + width / 2) / input_width,
                    (center_y + height / 2) / input_height,
                ],
            }
        )
    return detections


def _run_genai_inference(model_path: str, image_bytes: bytes) -> list[dict[str, Any]]:
    try:
        import onnxruntime_genai as og
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="onnxruntime-genai-cuda is required for Phi-4 inference",
        ) from error

    image_path = "/tmp/tiger-poc-phi4-input.jpg"
    Path(image_path).write_bytes(image_bytes)
    try:
        model = og.Model(model_path)
        tokenizer = og.Tokenizer(model)
        processor = model.create_multimodal_processor()
        images = og.Images.open(image_path)
        prompt = "<|user|><|image_1|>Return a concise JSON description of the image.<|end|><|assistant|>"
        inputs = processor(prompt, images=images)
        params = og.GeneratorParams(model)
        params.set_search_options(max_length=512, batch_size=1)
        generator = og.Generator(model, params)
        generator.set_inputs(inputs)
        output_tokens: list[int] = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.extend(generator.get_next_tokens())
        text = tokenizer.decode(output_tokens)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Phi-4 inference failed: {error}") from error
    finally:
        Path(image_path).unlink(missing_ok=True)

    return [{"label": "analysis", "confidence": 1.0, "content": text}]


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
        if not model_path.is_file() and not model_path.is_dir():
            raise HTTPException(
                status_code=503,
                detail=f"Model artifact is not installed: {model['path']}",
            )
        if not request.image_base64:
            raise HTTPException(status_code=400, detail="image_base64 is required")
        try:
            image_bytes = base64.b64decode(request.image_base64, validate=True)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="image_base64 is invalid") from error
        if model.get("runtime") == "onnxruntime-genai-cuda":
            detections = _run_genai_inference(str(model_path), image_bytes)
        elif model.get("runtime") == "transformers":
            raise HTTPException(
                status_code=501,
                detail="Florence-2 requires its Transformers runtime adapter",
            )
        else:
            detections = _run_onnx_inference(str(model_path), request.model, image_bytes)
    else:
        # Mock mode: return synthetic detections without loading model files
        detections = []

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

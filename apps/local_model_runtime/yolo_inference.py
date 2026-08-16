"""Real YOLOv8 ONNX inference for the predictive workload contract.

Loads the exported `model.onnx` (input `images` [1,3,640,640], output
`output0` [1,84,8400]: 4 box coordinates plus 80 COCO class scores) and
decodes detections from a base64-encoded image.
"""

from __future__ import annotations

import base64
import binascii
import io
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, UnidentifiedImageError

INPUT_SIZE = 640
DEFAULT_IOU_THRESHOLD = 0.45
DEFAULT_CONFIDENCE_THRESHOLD = 0.25
MAX_DETECTIONS = 100

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


class ImageDecodeError(ValueError):
    """The request payload did not contain a decodable image."""


def _decode_image(image_b64: str) -> Image.Image:
    try:
        raw = base64.b64decode(image_b64, validate=False)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError) as error:
        raise ImageDecodeError(str(error)) from error


def _letterbox(image: Image.Image, size: int = INPUT_SIZE) -> Tuple[np.ndarray, float, int, int]:
    """Resize preserving aspect ratio and pad to a square, matching Ultralytics export."""
    width, height = image.size
    scale = min(size / width, size / height)
    new_width, new_height = round(width * scale), round(height * scale)
    resized = image.resize((new_width, new_height), Image.BILINEAR)

    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    pad_x, pad_y = (size - new_width) // 2, (size - new_height) // 2
    canvas.paste(resized, (pad_x, pad_y))

    tensor = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = tensor.transpose(2, 0, 1)[np.newaxis, ...]
    return np.ascontiguousarray(tensor), scale, pad_x, pad_y


def _iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    intersection = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = area_box + areas - intersection
    return np.where(union > 0, intersection / union, 0.0)


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> List[int]:
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size:
        current = order[0]
        keep.append(int(current))
        if order.size == 1:
            break
        remaining = order[1:]
        overlaps = _iou(boxes[current], boxes[remaining])
        order = remaining[overlaps <= iou_threshold]
    return keep


def _postprocess(
    output: np.ndarray,
    original_size: Tuple[int, int],
    scale: float,
    pad_x: int,
    pad_y: int,
    confidence_threshold: float,
    iou_threshold: float,
) -> List[Dict[str, Any]]:
    predictions = output[0].transpose(1, 0)  # (8400, 84)
    boxes_cxcywh = predictions[:, :4]
    class_scores = predictions[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    scores = class_scores[np.arange(class_scores.shape[0]), class_ids]

    keep_mask = scores >= confidence_threshold
    if not np.any(keep_mask):
        return []

    boxes_cxcywh = boxes_cxcywh[keep_mask]
    class_ids = class_ids[keep_mask]
    scores = scores[keep_mask]

    cx, cy, w, h = boxes_cxcywh[:, 0], boxes_cxcywh[:, 1], boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]
    boxes_xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - pad_x) / scale
    boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - pad_y) / scale

    width, height = original_size
    boxes_xyxy[:, [0, 2]] = boxes_xyxy[:, [0, 2]].clip(0, width)
    boxes_xyxy[:, [1, 3]] = boxes_xyxy[:, [1, 3]].clip(0, height)

    detections: List[Dict[str, Any]] = []
    for class_id in np.unique(class_ids):
        class_mask = class_ids == class_id
        kept = _nms(boxes_xyxy[class_mask], scores[class_mask], iou_threshold)
        class_boxes = boxes_xyxy[class_mask][kept]
        class_scores_kept = scores[class_mask][kept]
        for box, score in zip(class_boxes, class_scores_kept):
            label = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else str(int(class_id))
            detections.append(
                {
                    "label": label,
                    "confidence": round(float(score), 4),
                    "box": {
                        "x1": round(float(box[0]), 2),
                        "y1": round(float(box[1]), 2),
                        "x2": round(float(box[2]), 2),
                        "y2": round(float(box[3]), 2),
                    },
                }
            )

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections[:MAX_DETECTIONS]


@lru_cache(maxsize=None)
def _session(model_path: str):
    import onnxruntime as ort

    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def run_yolo_inference(
    image_b64: str,
    model_path: Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Decode `image_b64` and return YOLO detections, or `[]` if undecodable."""
    try:
        image = _decode_image(image_b64)
    except ImageDecodeError:
        return []

    session = _session(str(model_path))
    input_tensor, scale, pad_x, pad_y = _letterbox(image)
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: input_tensor})[0]

    return _postprocess(
        output,
        original_size=image.size,
        scale=scale,
        pad_x=pad_x,
        pad_y=pad_y,
        confidence_threshold=confidence_threshold,
        iou_threshold=iou_threshold,
    )

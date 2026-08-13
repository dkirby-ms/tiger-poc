from __future__ import annotations

from pathlib import Path

from inference_api.service import normalize_inference_response
from event_rules.service import EventRuleConfig, apply_event_rules
from local_store.service import LocalDetectionStore


def test_given_foundry_response_when_normalize_then_returns_detection_list() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"detections":[{"label":"person","confidence":0.91,"bbox":[0.1,0.2,0.4,0.7],"zone":"entry"}]}'
                }
            }
        ]
    }

    results = normalize_inference_response(payload, model_id="yolo-v8", source_id="camera-1")

    assert len(results) == 1
    assert results[0].label == "person"
    assert results[0].confidence == 0.91
    assert results[0].bbox == (0.1, 0.2, 0.4, 0.7)


def test_given_low_confidence_and_short_dwell_when_apply_rules_then_filters() -> None:
    config = EventRuleConfig(confidence_threshold=0.75, dwell_time_seconds=1.0)
    detections = [
        {"label": "person", "confidence": 0.91, "dwell_time_seconds": 1.5, "bbox": [0.1, 0.2, 0.4, 0.7]},
        {"label": "vehicle", "confidence": 0.60, "dwell_time_seconds": 2.0, "bbox": [0.2, 0.3, 0.8, 0.9]},
        {"label": "person", "confidence": 0.82, "dwell_time_seconds": 0.2, "bbox": [0.5, 0.1, 0.7, 0.3]},
    ]

    filtered = apply_event_rules(detections, config)

    assert [item["label"] for item in filtered] == ["person"]
    assert filtered[0]["confidence"] == 0.91


def test_given_detection_when_persist_then_writes_json_and_clip_metadata(tmp_path: Path) -> None:
    store = LocalDetectionStore(tmp_path)
    detection = {
        "camera_id": "camera-1",
        "model_id": "yolo-v8",
        "label": "person",
        "confidence": 0.88,
        "bbox": [0.1, 0.2, 0.4, 0.7],
    }

    record = store.persist_detection(detection, clip_bytes=b"demo-clip")

    assert record["clip_path"].endswith(".mp4")
    assert len(store.list_detections()) == 1
    assert (tmp_path / "detections").exists()
    assert (tmp_path / "clips").exists()

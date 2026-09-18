from __future__ import annotations

import json
from pathlib import Path

import pytest
import rtsp_yolo
from tiger_perception.sinks import LocalJsonlSink, SinkError, SinkUnavailableError


@pytest.fixture
def sink_path(tmp_path: Path) -> Path:
    return tmp_path / "process-events.jsonl"


def valid_event(event_id: str = "evt-001") -> dict:
    return {
        "schemaVersion": "1.0",
        "eventId": event_id,
        "eventType": "ProcessEvent",
        "sourceId": "camera-01",
        "subjectId": "station-7",
        "observationType": "state",
        "value": "running",
        "unit": "status",
        "confidence": 0.99,
        "capturedAt": "2026-09-15T10:00:00Z",
        "producedAt": "2026-09-15T10:00:01Z",
        "publishedAt": "2026-09-15T10:00:02Z",
        "provider": "local-replay",
        "model": "demo-model",
        "source": "replay",
        "sensitive": {"token": "should-not-persist"},
    }


def test_local_jsonl_sink_writes_valid_events(sink_path: Path) -> None:
    sink = LocalJsonlSink(path=sink_path, max_retries=2)

    result = sink.publish(valid_event())

    assert result is True
    assert sink.published_count == 1
    assert sink.failed_count == 0
    lines = sink_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["eventId"] == "evt-001"
    assert payload["schemaVersion"] == "1.0"
    assert "should-not-persist" not in payload["sensitive"]["token"]
    assert "should-not-persist" not in json.dumps(payload)


def test_invalid_event_fails_before_publication(sink_path: Path) -> None:
    sink = LocalJsonlSink(path=sink_path, max_retries=2)
    invalid = valid_event()
    invalid.pop("subjectId")

    with pytest.raises(SinkError, match="subjectId"):
        sink.publish(invalid)

    assert sink_path.exists() is False or sink_path.read_text(encoding="utf-8") == ""
    assert sink.failed_count == 1


def test_given_non_json_extension_when_published_then_local_sink_rejects(sink_path: Path) -> None:
    event = {**valid_event(), "observation": {"labels": {"person"}}}
    sink = LocalJsonlSink(path=sink_path)

    with pytest.raises(SinkError, match="JSON-serializable"):
        sink.publish(event)

    assert sink.failed_count == 1
    assert not sink_path.exists()


def test_sink_outage_and_recovery_are_bounded_and_deterministic(sink_path: Path) -> None:
    sink = LocalJsonlSink(path=sink_path, max_retries=2)
    sink.set_healthy(False)

    with pytest.raises(SinkUnavailableError):
        sink.publish(valid_event("evt-outage-1"))

    assert sink.attempted_count == 1
    assert sink.failed_count == 1
    assert sink_path.exists() is False

    sink.set_healthy(True)
    assert sink.publish(valid_event("evt-recovered-1")) is True
    assert sink.published_count == 1

    assert sink.publish(valid_event("evt-recovered-1")) is False
    assert sink.duplicate_count == 1


def test_duplicate_event_ids_are_not_written_twice(sink_path: Path) -> None:
    sink = LocalJsonlSink(path=sink_path, max_retries=2)

    assert sink.publish(valid_event("dup-1")) is True
    assert sink.publish(valid_event("dup-1")) is False
    assert sink_path.read_text(encoding="utf-8").count("dup-1") == 1


def test_detector_builds_valid_process_event() -> None:
    detections = [
        {"classId": 0, "label": "person", "confidence": 0.91, "boundingBox": {"xMin": 1, "yMin": 2, "xMax": 3, "yMax": 4}},
        {"classId": 1, "label": "car", "confidence": 0.72, "boundingBox": {"xMin": 5, "yMin": 6, "xMax": 7, "yMax": 8}},
    ]

    event = rtsp_yolo.build_process_event(
        camera_id="camera-01",
        frame_number=42,
        timestamp="2026-09-15T10:00:00Z",
        detections=detections,
        model_name="demo-model",
    )

    print(
        "process_event:",
        {
            "eventId": event["eventId"],
            "eventType": event["eventType"],
            "sourceId": event["sourceId"],
            "value": event["value"],
            "confidence": event["confidence"],
            "detection_count": len(detections),
        },
    )

    assert event["eventType"] == "ProcessEvent"
    assert event["sourceId"] == "camera-01"
    assert event["subjectId"] == "frame-42"
    assert event["observationType"] == "object-detections"
    assert event["value"] == 2
    assert 0.0 <= float(event["confidence"]) <= 1.0
    assert "token" not in json.dumps(event)


def test_given_transient_write_failure_when_publishing_then_retry_same_event(sink_path, monkeypatch):
    sink = LocalJsonlSink(path=sink_path, max_retries=2)
    original = sink._write_line
    writes = []

    def write(line):
        writes.append(line)
        if len(writes) == 1:
            raise OSError("private endpoint must not be logged")
        original(line)

    monkeypatch.setattr(sink, "_write_line", write)

    assert sink.publish(valid_event())
    assert writes[0] == writes[1]
    assert sink.failed_count == 1
    assert sink.published_count == 1


def test_given_permanent_failure_when_publishing_then_bounded_redacted_error(sink_path, monkeypatch):
    sink = LocalJsonlSink(path=sink_path, max_retries=2)

    def fail(line):
        raise OSError("rtsp://private-secret@camera")

    monkeypatch.setattr(sink, "_write_line", fail)

    with pytest.raises(SinkUnavailableError, match="retry budget") as error:
        sink.publish(valid_event())
    assert "private-secret" not in str(error.value)
    assert sink.failed_count == 2


def test_given_nested_secrets_when_publishing_then_redact_recursively(sink_path):
    sink = LocalJsonlSink(path=sink_path)
    event = valid_event()
    event["observation"] = {"details": [{"password": "nested-secret", "camera": "rtsp://private"}]}

    sink.publish(event)

    assert "nested-secret" not in sink_path.read_text()
    assert "rtsp://" not in sink_path.read_text()

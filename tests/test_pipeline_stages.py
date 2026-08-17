import json
from types import SimpleNamespace

import pytest
from PIL import Image

from apps.pipeline_framework import (
    Detection,
    DetectionSet,
    Envelope,
    Event,
    Frame,
    PipelineRunner,
    PreparedFrame,
    RuleEvaluation,
    StageContext,
    load_pipeline,
)
from apps.pipeline_framework.stages import built_in_registry
from apps.pipeline_framework.stages.file_source import FileSource, FileSourceConfig
from apps.pipeline_framework.stages.foundry import (
    LocalFoundryInference,
    LocalFoundryInferenceConfig,
)
from apps.pipeline_framework.stages.jsonl_sink import JsonlSink, JsonlSinkConfig
from apps.pipeline_framework.stages.letterbox import Letterbox, LetterboxConfig
from apps.pipeline_framework.stages.rules import (
    DwellRule,
    DwellRuleConfig,
    ThresholdRule,
    ThresholdRuleConfig,
)


async def collect(iterator):
    return [item async for item in iterator]


class FakeFoundryRuntime:
    def __init__(self, predictions=None, ready=True):
        self.predictions = predictions or []
        self.requests = []
        self.deployment = SimpleNamespace(
            model_id="yolo",
            route="/v1/predict",
            secret="test-secret",
            ready=ready,
        )

    def list_deployments(self):
        return [self.deployment]

    def dispatch(self, model_id, route, secret, payload):
        self.requests.append((model_id, route, secret, payload))
        return {
            "status": "ok",
            "response": {"predictions": [self.predictions]},
        }


def frame_envelope(captured_at=0.0):
    return Envelope.create(
        stream_id="camera-1",
        seq=int(captured_at),
        captured_at=captured_at,
        payload=Frame(Image.new("RGB", (100, 50), "white"), "generated"),
    )


def evaluation_envelope(matched, captured_at):
    detection = Detection("person", 0.9, (0, 0, 10, 10))
    return Envelope.create(
        stream_id="camera-1",
        seq=int(captured_at),
        captured_at=captured_at,
        payload=RuleEvaluation("threshold:person", matched, (detection,) if matched else ()),
    )


@pytest.mark.asyncio
async def test_given_image_file_when_produced_then_frame_identity_and_pixels_are_preserved(tmp_path):
    # Arrange
    image_path = tmp_path / "frame.png"
    Image.new("RGB", (12, 8), "red").save(image_path)
    source = FileSource(FileSourceConfig(path=image_path, stream_id="test-stream"))
    await source.setup(StageContext("source"))

    # Act
    results = await collect(source.produce())

    # Assert
    assert len(results) == 1
    assert results[0].stream_id == "test-stream"
    assert results[0].payload.image.size == (12, 8)


@pytest.mark.asyncio
async def test_given_wide_frame_when_letterboxed_then_padding_metadata_is_correct():
    # Arrange
    stage = Letterbox(LetterboxConfig(size=200))

    # Act
    results = await collect(stage.process(frame_envelope()))
    prepared = results[0].payload

    # Assert
    assert prepared.image.size == (200, 200)
    assert (prepared.scale, prepared.pad_x, prepared.pad_y) == (2.0, 0, 50)


@pytest.mark.asyncio
async def test_given_ready_model_when_inferred_then_boxes_are_mapped_to_original_image():
    # Arrange
    runtime = FakeFoundryRuntime(
        [{"label": "person", "confidence": 0.9, "box": {"x1": 20, "y1": 60, "x2": 180, "y2": 140}}]
    )
    stage = LocalFoundryInference(LocalFoundryInferenceConfig(model_id="yolo"))
    await stage.setup(StageContext("detect", {"foundry": runtime}))
    prepared = PreparedFrame(Image.new("RGB", (200, 200)), 100, 50, 2.0, 0, 50)
    envelope = frame_envelope().derive(prepared)

    # Act
    results = await collect(stage.process(envelope))

    # Assert
    assert results[0].payload.detections[0].box == (10.0, 5.0, 90.0, 45.0)
    assert runtime.requests[0][3]["items"][0]["data"]


@pytest.mark.asyncio
async def test_given_detection_below_threshold_when_evaluated_then_negative_result_is_emitted():
    # Arrange
    stage = ThresholdRule(ThresholdRuleConfig(label="person", min_confidence=0.8))
    envelope = frame_envelope().derive(
        DetectionSet((Detection("person", 0.7, (0, 0, 1, 1)),), "yolo")
    )

    # Act
    results = await collect(stage.process(envelope))

    # Assert
    assert results[0].payload.matched is False


@pytest.mark.asyncio
async def test_given_continuous_match_when_dwell_elapsed_then_one_event_is_emitted_until_reset():
    # Arrange
    stage = DwellRule(DwellRuleConfig(min_dwell_s=2, event_type="person_present"))

    # Act
    first = await collect(stage.process(evaluation_envelope(True, 0)))
    boundary = await collect(stage.process(evaluation_envelope(True, 2)))
    suppressed = await collect(stage.process(evaluation_envelope(True, 3)))
    await collect(stage.process(evaluation_envelope(False, 4)))
    reset = await collect(stage.process(evaluation_envelope(True, 6)))
    second = await collect(stage.process(evaluation_envelope(True, 8)))

    # Assert
    assert (first, len(boundary), suppressed, reset, len(second)) == ([], 1, [], [], 1)


@pytest.mark.asyncio
async def test_given_small_retention_limit_when_events_written_then_file_stays_bounded(tmp_path):
    # Arrange
    path = tmp_path / "events.jsonl"
    sink = JsonlSink(JsonlSinkConfig(path=path, max_bytes=400))
    await sink.setup(StageContext("events"))

    # Act
    for sequence in range(10):
        event = Envelope.create(
            stream_id="camera-1",
            seq=sequence,
            captured_at=float(sequence),
            payload=Event(
                "person_present", "camera-1", 0, float(sequence), ()
            ),
        )
        await collect(sink.process(event))

    # Assert
    assert path.stat().st_size <= 400
    assert all(json.loads(line)["schema_version"] == 1 for line in path.read_text().splitlines())


@pytest.mark.asyncio
async def test_given_local_manifest_when_run_then_detection_event_is_written(tmp_path):
    # Arrange
    image_path = tmp_path / "input.png"
    output_path = tmp_path / "events.jsonl"
    manifest_path = tmp_path / "pipeline.yaml"
    Image.new("RGB", (100, 50), "white").save(image_path)
    manifest_path.write_text(
        f"""apiVersion: tiger.dev/v1
kind: Pipeline
metadata: {{name: e2e}}
spec:
  stages:
    - id: source
      type: source.file
      config: {{path: {image_path}, stream_id: camera-1}}
    - id: letterbox
      type: transform.letterbox
      inputs: [source]
      config: {{size: 200}}
    - id: detect
      type: infer.foundry.local
      inputs: [letterbox]
      config: {{model_id: yolo}}
    - id: threshold
      type: rule.threshold
      inputs: [detect]
      config: {{label: person, min_confidence: 0.5}}
    - id: dwell
      type: rule.dwell
      inputs: [threshold]
      config: {{event_type: person_present, min_dwell_s: 0}}
    - id: events
      type: sink.jsonl
      inputs: [dwell]
      config: {{path: {output_path}}}
""",
        encoding="utf-8",
    )
    runtime = FakeFoundryRuntime(
        [{"label": "person", "confidence": 0.9, "box": {"x1": 20, "y1": 60, "x2": 180, "y2": 140}}]
    )
    registry = built_in_registry()
    runner = PipelineRunner(
        load_pipeline(manifest_path, registry),
        registry,
        services={"foundry": runtime},
    )

    # Act
    result = await runner.run()

    # Assert
    record = json.loads(output_path.read_text(encoding="utf-8"))
    assert record["event_type"] == "person_present"
    assert record["stream_id"] == "camera-1"
    assert result.channels["dwell->events"].received == 1
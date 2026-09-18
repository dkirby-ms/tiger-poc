"""End-to-end normalized evidence through isolated local JSONL outputs."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tiger_perception.config import load_workload
from tiger_perception.contracts import RawDetection, RawInference
from tiger_perception.runner import WorkloadRuntime, output_lock
from tiger_perception.sinks import validate_process_event

MANIFESTS = Path(__file__).parents[1] / "manifests"


@pytest.fixture
def qr_runtime(tmp_path):
    workload = load_workload(MANIFESTS / "cell-c-qr.yaml")
    workload.spec.destination.path = str(tmp_path / "events.jsonl")
    workload.spec.destination.statusPath = str(tmp_path / "status.json")
    return WorkloadRuntime(workload)


def observe_cases(runtime, second, case_ids=("CASE-001",), *, succeeded=True):
    now = datetime(2026, 9, 17, tzinfo=UTC) + timedelta(seconds=second)
    detections = [RawDetection(0, "qr", 1.0,
                              {"xMin": 0.2, "yMin": 0.2, "xMax": 0.4, "yMax": 0.4},
                              case_id=case_id) for case_id in case_ids]
    runtime.process(RawInference(str(second), runtime.rule.source_id, int(second * 10),
                                 now.isoformat(), now.isoformat(), "opencv", "QRCodeDetector",
                                 detections, succeeded=succeeded), now=now)


def test_given_outside_region_label_when_confirmed_then_no_identification(qr_runtime):
    qr_runtime.rule.policy = replace(qr_runtime.rule.policy, region=(0.5, 0.5, 1.0, 1.0))

    observe_cases(qr_runtime, 0)
    observe_cases(qr_runtime, 0.5)

    assert qr_runtime.sink.published_count == 0
    assert qr_runtime._qr_codes == []


def test_given_new_case_while_another_visible_when_confirmed_then_identify_both(qr_runtime):
    observe_cases(qr_runtime, 0)
    observe_cases(qr_runtime, 0.5)
    observe_cases(qr_runtime, 1, ("CASE-001", "CASE-002"))
    observe_cases(qr_runtime, 1.5, ("CASE-001", "CASE-002"))

    assert qr_runtime.sink.published_count == 2
    assert qr_runtime.latest_event["value"] == "CASE-002"


def test_given_lost_reads_when_case_returns_then_reidentify_without_removal_event(qr_runtime):
    observe_cases(qr_runtime, 0)
    observe_cases(qr_runtime, 0.5)
    for second in (1, 2, 3):
        observe_cases(qr_runtime, second, ())
    assert qr_runtime.sink.published_count == 1

    observe_cases(qr_runtime, 3.5)
    observe_cases(qr_runtime, 4)

    events = [json.loads(line) for line in Path(qr_runtime.workload.spec.destination.path).read_text().splitlines()]
    assert [event["value"] for event in events] == ["CASE-001", "CASE-001"]


def test_given_inference_failure_when_confirming_case_then_require_fresh_window(qr_runtime):
    observe_cases(qr_runtime, 0)
    observe_cases(qr_runtime, 0.5, succeeded=False)
    observe_cases(qr_runtime, 1)
    assert qr_runtime.sink.published_count == 0

    observe_cases(qr_runtime, 1.5)

    assert qr_runtime.sink.published_count == 1


def test_given_stale_gap_when_confirming_case_then_require_fresh_window(qr_runtime):
    observe_cases(qr_runtime, 0)
    observe_cases(qr_runtime, 4)
    assert qr_runtime.sink.published_count == 0

    observe_cases(qr_runtime, 4.5)

    assert qr_runtime.sink.published_count == 1


def test_given_qr_preflight_when_running_then_never_load_yolo_or_open_camera(monkeypatch):
    from tiger_perception import runner

    def unexpected(*args, **kwargs):
        pytest.fail("QR preflight must not load YOLO or open the camera")

    monkeypatch.setattr(runner, "YoloProvider", unexpected)
    monkeypatch.setattr(runner, "CameraCapture", unexpected)
    monkeypatch.setenv("CAMERA_C_RTSP_URL", "rtsp://unused")
    args = runner.create_parser().parse_args(["--manifest", str(MANIFESTS / "cell-c-qr.yaml"), "--check"])

    assert runner.run(args) == 0


def test_given_qr_frames_when_runner_executes_then_write_identifications_and_preview(qr_runtime, monkeypatch):
    import cv2
    import numpy as np
    from tiger_perception import runner
    from tiger_perception.contracts import Frame

    tiles = [cv2.resize(np.pad(cv2.QRCodeEncoder_create().encode(case_id), 8, constant_values=255),
                        (300, 300), interpolation=cv2.INTER_NEAREST)
             for case_id in ("CASE-001", "CASE-002", "CASE-003")]
    image = cv2.cvtColor(np.concatenate(tiles, axis=1), cv2.COLOR_GRAY2BGR)
    workload = qr_runtime.workload
    closed = []

    class TestCapture:
        def __init__(self, *args):
            self.sequence = 0

        def start(self):
            pass

        def read(self):
            self.sequence += 1
            captured = datetime.now(UTC) - timedelta(seconds=0.6 if self.sequence == 1 else 0)
            return Frame(workload.spec.source.id, self.sequence, captured.isoformat(), image,
                         {"usable": True, "epoch": 0})

        def close(self):
            closed.append(True)

    monkeypatch.setattr(runner, "load_workload", lambda path: workload)
    monkeypatch.setattr(runner, "CameraCapture", TestCapture)
    monkeypatch.setenv("CAMERA_C_RTSP_URL", "rtsp://unused")
    args = runner.create_parser().parse_args([
        "--manifest", str(MANIFESTS / "cell-c-qr.yaml"), "--max-frames", "2"])

    assert runner.run(args) == 0

    events = [validate_process_event(json.loads(line))
              for line in Path(workload.spec.destination.path).read_text().splitlines()]
    assert sorted(event["value"] for event in events) == ["CASE-001", "CASE-002", "CASE-003"]
    status = json.loads(Path(workload.spec.destination.statusPath).read_text())
    assert status["availability"] == "unavailable"
    assert status["reason"] == "Workload stopped"
    preview = cv2.imread(str(Path(workload.spec.destination.statusPath).with_suffix(".jpg")))
    assert preview.shape == (320, 960, 3)
    assert closed == [True]


def test_given_capture_reconnect_when_case_pending_then_start_new_confirmation(qr_runtime):
    from tiger_perception.contracts import Frame

    observe_cases(qr_runtime, 0)
    frame = Frame(qr_runtime.rule.source_id, 1, datetime.now(UTC).isoformat(), None,
                  {"usable": True, "epoch": 1})

    assert qr_runtime.accept_frame(frame)
    observe_cases(qr_runtime, 0.5)
    assert qr_runtime.sink.published_count == 0
    observe_cases(qr_runtime, 1)

    assert qr_runtime.sink.published_count == 1


@pytest.mark.parametrize("manifest,label,expected", [
    ("cell-a-jeep.yaml", "car", []),
    ("cell-c-qr.yaml", "qr", ["CASE-001"]),
])
def test_given_case_metadata_when_rendering_then_show_labels_only_for_qr_workloads(
        tmp_path, monkeypatch, manifest, label, expected):
    import cv2
    import numpy as np
    from tiger_perception.contracts import Frame

    workload = load_workload(MANIFESTS / manifest)
    workload.spec.destination.path = str(tmp_path / "events.jsonl")
    workload.spec.destination.statusPath = str(tmp_path / "status.json")
    runtime = WorkloadRuntime(workload)
    now = datetime.now(UTC)
    frame = Frame(runtime.rule.source_id, 1, now.isoformat(), np.zeros((240, 320, 3), dtype=np.uint8))
    detection = RawDetection(0, label, 1.0,
                             {"xMin": 0.3, "yMin": 0.3, "xMax": 0.6, "yMax": 0.6},
                             case_id="CASE-001")
    inference = RawInference("test", frame.source_id, 1, frame.captured_at, frame.captured_at,
                             "fixture", "fixture", [detection], qr_codes=["CASE-001"])
    drawn_labels = []
    monkeypatch.setattr(cv2, "putText", lambda image, text, *args: drawn_labels.append(text))

    runtime.process(inference, now=now)
    runtime.write_status(force=True)
    runtime.write_preview(frame, inference)

    assert drawn_labels == expected
    assert json.loads(Path(workload.spec.destination.statusPath).read_text())["qrCodes"] == expected
    assert Path(workload.spec.destination.statusPath).with_suffix(".jpg").is_file()


def test_given_two_workloads_when_states_change_then_outputs_remain_independent(tmp_path):
    runtimes = []
    for cell in ("a", "b"):
        workload = load_workload(MANIFESTS / f"cell-{cell}.yaml")
        workload.spec.destination.path = str(tmp_path / cell / "events.jsonl")
        workload.spec.destination.statusPath = str(tmp_path / cell / "status.json")
        runtimes.append(WorkloadRuntime(workload))
    start = datetime.now(UTC) - timedelta(seconds=20)
    detection = RawDetection(56, "chair", 0.9, {"xMin": 0.4, "yMin": 0.4, "xMax": 0.6, "yMax": 0.6})

    for second in range(16):
        for index, runtime in enumerate(runtimes):
            present = (4 <= second < 9) if index == 0 else second >= 8
            timestamp = (start + timedelta(seconds=second)).isoformat()
            inference = RawInference(f"{index}:{second}", runtime.rule.source_id, second,
                                     timestamp, timestamp, "fixture", "fixture-model",
                                     [detection] if present else [])
            runtime.process(inference, now=datetime.fromisoformat(timestamp))

    expected = [[False, True, False], [False, True]]
    for index, runtime in enumerate(runtimes):
        events = [validate_process_event(json.loads(line))
                  for line in Path(runtime.workload.spec.destination.path).read_text().splitlines()]
        assert [event["value"] for event in events] == expected[index]
        assert all(event["sourceId"] == runtime.rule.source_id for event in events)
        assert all(event["subjectId"] == runtime.rule.subject_id for event in events)
        assert all(event["plantId"] == "demo-plant-01" for event in events)


def test_given_output_owner_when_second_instance_starts_then_reject(tmp_path):
    path = tmp_path / "events.jsonl"

    with output_lock(path), pytest.raises(ValueError, match="already owned"), output_lock(path):
        pass


def test_given_multiple_qr_cases_when_confirmed_then_publish_ids_not_occupancy(tmp_path):
    workload = load_workload(MANIFESTS / "cell-c-qr.yaml")
    workload.spec.destination.path = str(tmp_path / "events.jsonl")
    workload.spec.destination.statusPath = str(tmp_path / "status.json")
    runtime = WorkloadRuntime(workload)
    start = datetime.now(UTC)
    detections = [RawDetection(0, "qr", 1.0,
                              {"xMin": 0.2, "yMin": 0.2, "xMax": 0.4, "yMax": 0.4},
                              case_id=case_id) for case_id in ("CASE-001", "CASE-002", "CASE-003")]

    for sequence in range(4):
        now = start + timedelta(seconds=sequence * 0.5)
        runtime.process(RawInference(str(sequence), runtime.rule.source_id, sequence,
                                     now.isoformat(), now.isoformat(), "opencv", "QRCodeDetector",
                                     detections), now=now)

    events = [validate_process_event(json.loads(line))
              for line in Path(workload.spec.destination.path).read_text().splitlines()]
    assert [event["subjectId"] for event in events] == ["CASE-001", "CASE-002", "CASE-003"]
    assert all(event["value"] == event["subjectId"] and event["observationType"] == "BoxIdentified"
               and event["unit"] == "identifier" for event in events)
    assert all(event["observation"]["positionId"] == workload.spec.source.subjectId for event in events)
    runtime.write_status(force=True)
    assert json.loads(Path(workload.spec.destination.statusPath).read_text())["qrCodes"] == [
        "CASE-001", "CASE-002", "CASE-003"]


def test_given_reconnect_when_first_new_frame_arrives_then_reset_pending(tmp_path):
    from tiger_perception.contracts import Frame

    workload = load_workload(MANIFESTS / "cell-a.yaml")
    runtime = WorkloadRuntime(workload)
    now = datetime.now(UTC)
    timestamp = now.isoformat()
    frame = Frame(runtime.rule.source_id, 1, timestamp, None, {"usable": True, "epoch": 0})
    runtime.accept_frame(frame)
    runtime.process(RawInference("first", runtime.rule.source_id, 1, timestamp, timestamp,
                                 "fixture", "fixture", []), now=now)

    runtime.accept_frame(replace(frame, metadata={"usable": True, "epoch": 1}))

    assert runtime.rule.availability == "unavailable"
    assert runtime.rule.confirmed is None
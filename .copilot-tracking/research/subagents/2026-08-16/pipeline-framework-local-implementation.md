---
title: Pipeline Framework Local Implementation Research
description: Focused research for a minimal local pipeline framework implementation in Tiger PoC
ms.date: 2026-08-16
ms.topic: concept
---

## Research questions

* What is the smallest extensible local package layout for Envelope, Stage, InProcChannel, registry, manifest validation, and runner?
* How should file source, letterbox, local Foundry inference, threshold and dwell rules, and JSONL sink compose?
* Which dependencies, manifest format, CLI, and tests fit the current repository?
* Which later issue-plan items remain blocked on external services?

## Discoveries

* The repository has no packaging metadata. Importable code lives under `apps/`,
  and `pytest.ini` adds the repository root to `pythonpath`. The smallest
  consistent location is therefore `apps/pipeline_framework/`, not the
  multi-package `packages/` target layout described for the mature system.
* `LocalFoundryDeploymentRuntime.dispatch()` is the correct local inference
  boundary. It resolves deployment identity, enforces route, readiness, and
  credential isolation, then calls the existing workload adapter. For YOLO,
  that path executes the ONNX model through `run_yolo_inference()`.
* Local inference is synchronous and CPU-bound from the runner's perspective.
  The inference stage should call it with `asyncio.to_thread()` so one model
  request does not block every pipeline task.
* The current predictive contract accepts a base64 JPEG in `image`. A local
  letterbox stage can emit a padded RGB frame plus scale and padding metadata;
  the inference stage can encode that image, dispatch it, and remap returned
  boxes to original coordinates. This preserves the Foundry contract without
  passing NumPy tensors across the deployment boundary.
* Threshold must emit a result for every input frame, including negative
  matches. Otherwise dwell never observes the frame that should reset an
  active interval. A `RuleEvaluation` payload with `matched`, count, and
  matching detections gives dwell deterministic reset semantics.
* Without a tracker, dwell can only mean continuous label presence per stream,
  not continuous presence of the same object. Object-level dwell belongs with
  the later tracking work in IS011.
* The first runner should support one source, one input per non-source stage,
  and fan-out. It should reject fan-in during manifest validation. Supporting
  fan-in correctly requires merge ordering and multi-upstream close semantics,
  which are not needed by the requested local chain.
* The current environment uses Python 3.12.3 but has none of the project runtime
  or test dependencies installed. `pytest -q` could not run because `pytest`
  is unavailable. Repository documentation and the Dockerfile target Python
  3.11, so implementation should retain Python 3.11 compatibility.

## Evidence

* `docs/pipeline-framework.md` defines the Envelope, Stage, Channel, registry,
  manifest, runner, and stage contracts, and identifies operator preview
  artifacts as unavailable through public channels.
* `requirements.txt` currently contains only ONNX Runtime, NumPy, and Pillow.
* `pytest.ini` currently contains only `pythonpath = .`.
* `apps/local_model_runtime/foundry_contract.py` exposes deployment listing,
  readiness, health, and dispatch through `LocalFoundryDeploymentRuntime`.
* `apps/local_model_runtime/workload_adapters.py` routes YOLO predictive calls
  to the model bundle and returns normalized predictions.
* `apps/local_model_runtime/yolo_inference.py` contains the current Pillow
  letterbox implementation and ONNX postprocessing logic.
* `apps/local_model_runtime/__main__.py` establishes the repository's existing
  `argparse` CLI convention.
* `tests/` contains service and contract tests but no media fixture, pipeline
  package, or asynchronous test configuration.
* `pipelines/` is empty and can hold the first checked-in local manifest.

## Recommended implementation

### Package and file plan

* `apps/pipeline_framework/__init__.py`: export stable core contracts and the
  built-in registry constructor
* `apps/pipeline_framework/__main__.py`: implement `validate` and `run`
  subcommands with `argparse`
* `apps/pipeline_framework/contracts.py`: define immutable `Envelope`, `Frame`,
  `PreparedFrame`, `DetectionSet`, `RuleEvaluation`, `Event`, `StageContext`,
  `StageHealth`, `Stage`, and `Source`
* `apps/pipeline_framework/channel.py`: define `Channel`, `InProcChannel`,
  `OverflowPolicy`, `SendResult`, and counters for sent, received, and dropped
* `apps/pipeline_framework/registry.py`: define `StageRegistry`, typed config
  registration, built-in loading, and optional `tiger.stages` entry-point
  discovery
* `apps/pipeline_framework/manifest.py`: parse YAML into Pydantic models and
  perform registry-aware graph and type validation before setup
* `apps/pipeline_framework/runner.py`: instantiate stages and per-edge channels,
  run source and worker tasks in an `asyncio.TaskGroup`, propagate close, and
  teardown in reverse topological order
* `apps/pipeline_framework/stages/file_source.py`: decode JPEG and PNG files
  with Pillow and recorded video with PyAV; preserve sequence, stream identity,
  and media PTS-derived capture time
* `apps/pipeline_framework/stages/letterbox.py`: resize and pad to a configured
  square while retaining original size, scale, and padding
* `apps/pipeline_framework/stages/foundry.py`: resolve one local deployment in
  setup, verify readiness, base64-encode the prepared JPEG, dispatch through an
  injected `LocalFoundryDeploymentRuntime`, and normalize or remap detections
* `apps/pipeline_framework/stages/rules.py`: implement per-frame confidence and
  count threshold evaluation plus one-event-per-episode dwell state per stream
* `apps/pipeline_framework/stages/jsonl_sink.py`: append one versioned event per
  line and flush each record; create the parent directory only when configured
* `apps/pipeline_framework/stages/__init__.py`: register the built-in stage
  definitions explicitly so imports are deterministic in tests
* `pipelines/local-yolo.yaml`: provide the first file-to-JSONL example
* `requirements.txt`: add `pydantic>=2.7,<3`, `PyYAML>=6,<7`, `av>=12,<17`, and
  `ulid-py>=1.1,<2`
* `requirements-dev.txt`: include `-r requirements.txt`, `pytest>=8,<9`, and
  `pytest-asyncio>=0.23,<2`
* `pytest.ini`: add the `model` marker; asynchronous tests can use explicit
  `@pytest.mark.asyncio` without global auto mode

Keep `apps/local_model_runtime/` behavior unchanged in this first slice. The
pipeline package consumes its public runtime and deployment contracts. A later
control-plane split can replace the injected runtime without changing stages.

### Core behavior

`Envelope` should use a ULID, immutable metadata, a monotonic per-stream
sequence, and a `derive()` helper that creates a new envelope ID while retaining
stream, sequence, capture time, trace context, and a parent ID. Payloads remain
ordinary frozen dataclasses. Cross-process serialization is deferred.

`InProcChannel` should wrap a bounded `asyncio.Queue` and implement `block`,
`drop_oldest`, and `drop_newest`. Close uses a private sentinel and is
idempotent. Tests must pin ordering, each overflow policy, drop counters, and
receive termination. The `sample` overflow policy remains invalid in the first
manifest schema until its sampling contract is specified.

The registry owns type name, factory, config model, accepted payload type, and
emitted payload type. Registration rejects duplicate names. Manifest loading
first validates structure, then resolves every type and config through the
registry. Validation rejects duplicate IDs, unknown types, missing inputs,
cycles, unreachable stages, incompatible payloads, nonpositive capacities,
multiple sources, fan-in, source inputs, and non-source stages without input.
No stage setup or model loading occurs during validation.

The runner creates one channel per edge. A stage routes each emitted envelope
to every outgoing edge, so fan-out has independent capacity and drop accounting.
When a source or worker completes, it closes its outgoing channels. Any task
failure cancels the task group, and all initialized stages are torn down once in
reverse topological order.

### Rule semantics

`rule.threshold` consumes a `DetectionSet` and always emits one
`RuleEvaluation`. Configuration includes `label`, `min_confidence`, and
`min_count`. The evaluation includes the filtered detections and whether the
count threshold passed.

`rule.dwell` consumes each evaluation. It starts an interval on the first true
evaluation, resets on false, and emits one `Event` when envelope capture time
reaches `min_dwell_s`. It suppresses further events until a false evaluation
ends the episode. State is keyed by `stream_id`.

### Manifest format

Use the documented envelope while limiting the first executable schema to a
single-source graph with no fan-in:

```yaml
apiVersion: tiger.dev/v1
kind: Pipeline
metadata:
  name: local-yolo
spec:
  defaults:
    channel:
      kind: inproc
      capacity: 8
      on_full: block
  stages:
    - id: frames
      type: source.file
      config:
        path: samples/input.mp4
        stream_id: file-01
    - id: letterbox
      type: transform.letterbox
      inputs: [frames]
      config:
        size: 640
        jpeg_quality: 90
    - id: detect
      type: infer.foundry.local
      inputs: [letterbox]
      config:
        model_id: yolo
        confidence_threshold: 0.35
    - id: person-threshold
      type: rule.threshold
      inputs: [detect]
      config:
        label: person
        min_confidence: 0.5
        min_count: 1
    - id: person-dwell
      type: rule.dwell
      inputs: [person-threshold]
      config:
        min_dwell_s: 2.0
        event_type: person_present
    - id: events
      type: sink.jsonl
      inputs: [person-dwell]
      config:
        path: data/events.jsonl
        create_parents: true
```

Model routes and secrets must not appear in the pipeline manifest. The local
inference stage resolves both from the deployment contract for `model_id`.

### CLI

```bash
python -m apps.pipeline_framework validate pipelines/local-yolo.yaml
python -m apps.pipeline_framework run pipelines/local-yolo.yaml
```

`validate` prints the pipeline name and topological stage order, returning 0 on
success and 2 on a manifest error. `run` validates first, returns 0 after a
finite file source drains, 2 for manifest errors, and 1 for runtime failures.
Errors should include the stage ID and configuration field when available.

### Tests

* `tests/test_pipeline_contracts.py`: envelope derivation and immutable metadata
* `tests/test_pipeline_channel.py`: ordering, capacity, overflow, close, stats
* `tests/test_pipeline_manifest.py`: schema, config, graph, and type failures
* `tests/test_pipeline_runner.py`: lifecycle order, filtering, fan-out, failure
  cancellation, and teardown
* `tests/test_file_source_stage.py`: still image and mocked or generated video
  frame ordering and timestamps
* `tests/test_letterbox_stage.py`: aspect ratio, padding, and transform metadata
* `tests/test_foundry_stage.py`: fake runtime resolution, readiness, payload,
  error mapping, thread offload, and box remapping without loading ONNX
* `tests/test_rule_stages.py`: threshold negatives, dwell boundary, one event per
  episode, reset, and stream isolation
* `tests/test_jsonl_sink.py`: one parseable line per event and exact schema
* `tests/test_pipeline_e2e.py`: generated image, fake local runtime, manifest,
  ordered event JSONL, plus an optional `model`-marked YOLO bundle smoke test

Focused commands after implementation:

```bash
python -m pytest -q tests/test_pipeline_channel.py tests/test_pipeline_manifest.py tests/test_pipeline_runner.py
python -m pytest -q tests/test_file_source_stage.py tests/test_letterbox_stage.py tests/test_foundry_stage.py
python -m pytest -q tests/test_rule_stages.py tests/test_jsonl_sink.py tests/test_pipeline_e2e.py -m "not model"
python -m pytest -q tests/test_pipeline_e2e.py -m model
python -m pytest -q
```

## External blockers

* IS005 and IS006 are fully local and unblocked by external services.
* The requested portion of IS007 is unblocked for recorded files. RTSP can be
  tested with a local simulator; no external camera should gate implementation.
* The local portion of IS008 is unblocked through
  `LocalFoundryDeploymentRuntime`. Kubernetes control-plane resolution is not
  part of this slice.
* The threshold, dwell, and JSONL subset of IS011 is unblocked. Tracking,
  clips, retention, and MQTT remain deferred, but a local broker can later test
  MQTT without an external service.
* IS004 cannot meet its operator-ready acceptance criterion until the Foundry
  Local operator chart and images are available through preview onboarding.
  The k3d, registry, cert-manager, Gateway API, and Istio preparation remains
  locally actionable.
* IS009 can implement request codecs and recorded contract tests locally, but
  live verification of preview endpoint and authentication behavior remains
  gated on operator access.
* IS010 must remain blocked as an integration item because it explicitly
  requires the shared Foundry Local platform, generated credentials, and real
  `ModelDeployment` lifecycle behavior.
* IS013's local HTTP partitioning work is not externally blocked. Only Azure
  IoT Operations transport and Arc deployment validation should remain gated.
* Tier 3 validation for Entra ID, GPU scheduling, disconnected operation, and
  Arc extension installation requires an Arc-enabled Azure Local cluster.

## Clarifying questions

None. The local implementation can proceed with the explicit first-version
constraints above.

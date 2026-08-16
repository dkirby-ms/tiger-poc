---
title: Modular Pipeline Framework Design
description: Target architecture and migration plan for evolving Tiger PoC into a pluggable, Foundry Local-native video inference pipeline framework
author: Tiger PoC
ms.date: 2026-08-16
ms.topic: concept
keywords:
  - pipeline framework
  - foundry local
  - video inference
  - microservices
  - plugin architecture
estimated_reading_time: 18
---

## Purpose and scope

Tiger PoC currently serves models over HTTP and enforces a Foundry Local deployment contract. Video ingestion, preprocessing, rules, and storage exist in architecture documents but not in code. This design turns the proof of concept into four things at once:

* a reference architecture that maps cleanly onto Azure Local and Foundry Local
* a set of independently deployable microservices
* a pluggable pipeline where stages are third-party extensible
* a Foundry Local-native inference path with deployment-aware routing

The guiding constraint is that a stage author should never need to modify framework code. Adding a new source, transform, or sink means writing one class and registering it.

## Design goals

| Goal | Consequence for the design |
|------|----------------------------|
| Composition over configuration branches | Pipelines are declared as a directed graph in YAML, not assembled in Python |
| Location transparency | Stages communicate through a `Channel` abstraction so in-process and cross-service topologies share one contract |
| Contract-first extension points | Stage, channel, and control-plane interfaces are protocols with conformance test suites |
| Foundry Local as the model control plane | Stages resolve models by deployment identity, not by hard-coded URLs |
| Backpressure is explicit | Every edge declares capacity and an overflow policy, because dropping frames is normal at the edge |
| Observability by construction | The framework emits per-stage latency, queue depth, and drop counters without stage-author effort |

### Non-goals

* Distributed scheduling or cluster autoscaling. Kubernetes and Foundry Local own that.
* A general-purpose stream processing engine. The graph is bounded and declarative, not a dataflow language.
* Exactly-once delivery. Video inference at the edge is best-effort with explicit drop accounting.

## Target architecture

```text
+=============================================================================+
|  Control Plane                                                              |
|                                                                             |
|   +------------------+    +------------------+    +------------------+      |
|   | Pipeline Manifest|    | Foundry Local    |    | Model Bundle     |      |
|   | pipelines/*.yaml |    | deployments      |    | registry         |      |
|   +--------+---------+    +---------+--------+    +---------+--------+      |
|            |                        |                       |              |
+============|========================|=======================|==============+
             v                        v                       v
+=============================================================================+
|  Pipeline Runtime                                                           |
|                                                                             |
|  +---------+   +---------+   +---------+   +---------+   +---------+        |
|  | Source  |-->|Transform|-->| Infer   |-->| Rules   |-->| Sink    |        |
|  | rtsp    | C | sample  | C | foundry | C | dwell   | C | jsonl   |        |
|  +---------+   +---------+   +---------+   +---------+   +---------+        |
|       ^             ^             |             |             |            |
|       |             |             v             v             v            |
|  +----+-------------+-------------+-------------+-------------+----+       |
|  |  Runner: scheduling, channels, health, metrics, lifecycle       |       |
|  +-----------------------------------------------------------------+       |
|                                                                             |
|  C = Channel (inproc queue | HTTP | MQTT), selected per edge at deploy time |
+=============================================================================+
             |                                        |
             v                                        v
+=============================================================================+
|  Model Serving Plane (existing local_model_runtime, refactored)             |
|                                                                             |
|   gateway :8080  -->  /yolo  /florence-2  /phi-4-multimodal                 |
|                       one model service container per deployment            |
+=============================================================================+
```

The runtime and the model serving plane stay separate processes. That boundary already exists today and is the correct seam: inference has different resource, scaling, and lifecycle characteristics than frame handling.

## Core abstractions

Five types carry the entire framework. Everything else is a plugin.

### Envelope

Every value that crosses a stage boundary is wrapped. The wrapper carries identity, ordering, timing, and trace context so that stages remain stateless with respect to plumbing.

```python
@dataclass(frozen=True)
class Envelope(Generic[T]):
    id: str                      # ULID, unique per envelope
    stream_id: str               # camera or source identity
    seq: int                     # monotonic per stream_id
    captured_at: float           # epoch seconds at source
    payload: T                   # Frame, Detections, Event, Clip, ...
    meta: Mapping[str, Any]      # accumulated stage annotations
    trace: TraceContext          # W3C traceparent for cross-service spans
```

Payload types are ordinary dataclasses (`Frame`, `Detections`, `Event`) and live in the core package so that stages from different authors interoperate. Stages declare `accepts` and `emits` types, and the graph loader validates type compatibility before the pipeline starts.

### Stage

```python
class Stage(Protocol[TIn, TOut]):
    accepts: type[TIn]
    emits: type[TOut]

    async def setup(self, ctx: StageContext) -> None: ...
    async def process(self, envelope: Envelope[TIn]) -> AsyncIterator[Envelope[TOut]]: ...
    async def teardown(self) -> None: ...
    def health(self) -> StageHealth: ...
```

`process` returns an async iterator rather than a single value. That single decision covers filtering (yield nothing), one-to-one mapping (yield once), and batching or fan-out (yield many) without separate interfaces.

Sources are stages whose `accepts` is `None` and which implement `produce()` instead. Sinks have `emits` set to `None`.

`StageContext` provides the logger, metrics recorder, per-stage configuration, a resolved Foundry client, and a cancellation token. Stages receive dependencies rather than importing globals, which keeps them unit-testable in isolation.

### Channel

The transport abstraction is what makes the in-process and microservice topologies the same pipeline.

```python
class Channel(Protocol):
    async def send(self, envelope: Envelope) -> SendResult
    def receive(self) -> AsyncIterator[Envelope]
    async def close(self) -> None
    def stats(self) -> ChannelStats     # depth, dropped, sent, received
```

| Implementation | Transport | Use |
|----------------|-----------|-----|
| `InProcChannel` | bounded `asyncio.Queue` | single-process runner, default |
| `HttpChannel` | POST to a downstream runner | splitting a graph across services |
| `MqttChannel` | Azure IoT Operations MQTT broker | event fan-out, cross-node stages |
| `FileChannel` | append-only spool directory | replay, debugging, crash recovery |

Every implementation passes the same conformance suite, so swapping a channel is a manifest edit rather than a code change. Frame payloads over non-local channels serialize as JPEG bytes with a content descriptor; the envelope header stays JSON.

### Overflow policy

Each edge declares what happens when the consumer falls behind.

| Policy | Behavior | Typical use |
|--------|----------|-------------|
| `block` | Producer awaits capacity | file replay, correctness over liveness |
| `drop_oldest` | Evict head, enqueue new | live camera detection, prefers recency |
| `drop_newest` | Reject the incoming envelope | expensive downstream stages |
| `sample` | Keep every Nth under pressure | generative captioning fed from a detection stream |

Drops increment a counter tagged with stream, edge, and reason. Silent frame loss is the most common failure mode in edge vision systems, so it is measured rather than hidden.

### Registry

Stages register by type name through a decorator, and third-party packages register through Python entry points.

```python
@register_stage("source.rtsp")
class RtspSource(Source[Frame]):
    config_model = RtspSourceConfig
```

```toml
[project.entry-points."tiger.stages"]
my_tracker = "acme_tracker:register"
```

The loader discovers built-in stages, then entry-point packages, then any paths listed under `spec.plugins` in the manifest. Each stage supplies a pydantic `config_model`, so manifest validation reports precise, typed errors before any resource is acquired.

## Pipeline manifest

```yaml
apiVersion: tiger.dev/v1
kind: Pipeline
metadata:
  name: warehouse-safety
spec:
  defaults:
    channel:
      kind: inproc
      capacity: 8
      on_full: drop_oldest

  streams:
    - id: dock-01
      url: rtsp://10.0.0.42/stream1
    - id: dock-02
      url: rtsp://10.0.0.43/stream1
    - id: yard-01
      url: rtsp://10.0.0.51/stream1

  stages:
    - id: camera
      type: source.rtsp
      config:
        target_fps: 5
        reconnect_backoff_s: [1, 2, 5, 15]

    - id: letterbox
      type: transform.letterbox
      inputs: [camera]
      config:
        size: 640

    - id: batch
      type: transform.batch
      inputs: [letterbox]
      config:
        max_items: 8
        max_wait_ms: 80

    - id: detect
      type: infer.foundry
      inputs: [batch]
      config:
        model_id: yolo
        confidence_threshold: 0.35
        max_concurrency: 2
        timeout_s: 5

    - id: ppe-rule
      type: rule.dwell
      inputs: [detect]
      config:
        label: person
        zone: [[0.1, 0.4], [0.9, 0.4], [0.9, 1.0], [0.1, 1.0]]
        min_dwell_s: 3

    - id: describe
      type: infer.foundry
      inputs: [ppe-rule]
      channel:
        capacity: 2
        on_full: drop_newest
      config:
        model_id: phi-4-multimodal
        prompt: "Describe the safety hazard visible in this frame."

    - id: events
      type: sink.jsonl
      inputs: [ppe-rule, describe]
      config:
        path: /data/events.jsonl
        rotate_mb: 64
```

The graph is a DAG. Fan-out happens when several stages list the same input; fan-in happens when a stage lists several inputs. The loader rejects cycles, type mismatches, unknown stage types, and unreachable stages before startup.

### Streams and multi-camera execution

The graph is declared once and instantiated once per stream. A runner hosting three cameras builds three independent chains of stage instances, each with its own bounded channels and its own asyncio task group. A camera that stalls on reconnect, or a stage that blocks on a slow disk, degrades only its own chain.

This makes fair-share scheduling unnecessary. The heavy resource, GPU inference, lives in the model serving plane and is shared across all streams through its own concurrency limits, so the runner is left with decode and HTTP work that bounded per-stream queues already regulate. One runner per camera becomes the degenerate case of a shard containing a single stream rather than a separate execution model.

Stage instances are per-stream, so stateful stages such as trackers and dwell rules keep their state naturally scoped. Stages that must aggregate across streams declare `scope: pipeline` and receive a single shared instance.

### Stage catalog

| Type | Category | Emits | Status after migration |
|------|----------|-------|------------------------|
| `source.rtsp` | source | `Frame` | new |
| `source.file` | source | `Frame` | new |
| `source.folder` | source | `Frame` | new |
| `transform.sample` | transform | `Frame` | new |
| `transform.letterbox` | transform | `Frame` | ported from `yolo_inference._letterbox` |
| `transform.batch` | transform | `Batch[Frame]` | new, feeds Foundry predictive batching |
| `infer.foundry` | transform | `Detections` or `Completion` | wraps existing model runtime call path |
| `transform.track` | transform | `Detections` | new, IoU tracker for stable identities |
| `rule.threshold` | transform | `Event` | new |
| `rule.dwell` | transform | `Event` | new |
| `sink.jsonl` | sink | none | new |
| `sink.clip` | sink | none | new, writes pre/post roll video |
| `sink.mqtt` | sink | none | new, Azure IoT Operations bridge |

### Retention and storage pressure

Sinks own retention, because only a sink knows whether it is writing to a rotating log file, a clip directory, or a remote blob container. The framework supplies a shared `RetentionPolicy` that sinks compose rather than reimplement.

```yaml
retention:
  max_bytes: 20Gi
  max_age: 72h
  max_files: 5000
  high_water: 0.85
```

Eviction runs on a high-water trigger rather than on every write, evicting oldest first until usage falls below the mark. When a sink cannot evict fast enough, it raises a disk-pressure signal that the runner converts into an overflow condition on that sink's inbound edge. Storage exhaustion then degrades into measured, attributed frame drops instead of a crashed pipeline or a full volume. Clip sinks default to a byte-bounded ring, which is the only policy that reliably survives an unattended edge node.

## Foundry Local integration

The binding target is Foundry Local on Azure Local, the Kubernetes inference operator exposing `foundrylocal.azure.com/v1` in the `foundry-local-operator` namespace. This is distinct from the Windows and macOS Foundry Local developer SDK, which is a different product with a different API and is not a target here.

Today `LocalFoundryDeploymentRuntime` is both the contract harness and the dispatcher. Splitting it produces a genuinely Foundry-native path.

```python
class FoundryControlPlane(Protocol):
    def list_deployments(self) -> list[DeploymentContract]: ...
    def get(self, model_id: str) -> DeploymentContract | None: ...
    def create(self, config: DeploymentConfig) -> DeploymentContract: ...
    def delete(self, model_id: str) -> bool: ...
    def wait_ready(self, model_id: str, timeout_s: float) -> bool: ...
```

`LocalControlPlane` is the current in-process registry and supervisor, retained for tests and single-node development. `KubernetesFoundryControlPlane` reconciles against real `ModelDeployment` resources, reads endpoint information from resource status, and pulls API keys from the generated `<deployment-name>-api-keys` secret.

### Alignment already achieved

The existing implementation matches the operator more closely than expected, and these semantics carry forward unchanged.

| Concept | Current code | Operator behavior |
|---------|--------------|-------------------|
| Lifecycle states | `DeploymentState` enum | `Pending`, `Creating`, `Running`, `Updating`, `Error`, `Terminating` |
| Runtimes | `onnx-genai`, `vllm` with vLLM restricted to GPU generative | Same constraint, selected by `spec.runtime` |
| Workload split | predictive and generative profiles | Same split, different endpoints and images |
| Routing | path prefix plus rewrite in `EndpointConfig` | Gateway API path template plus rewrite |
| GPU limits | `resources.limits.gpu` | `resources.limits.gpu`, range 1 to 8 |

### Corrections required

Three contract details in the current code do not match the operator. Payload and auth are corrected in Phase 3; model sourcing follows in Phase 4.

| Area | Current | Correct |
|------|---------|---------|
| Predictive payload | `{"image": "<base64>"}` | `{"items": [{"content_type": "image/jpeg", "encoder": "base64", "data": "<base64>"}]}` |
| Predictive auth | `Authorization: Bearer` or `api-key` | `X-API-Key`, while generative keeps `Authorization: Bearer` |
| Model sourcing | file path resolved from `models/bundle.json` | OCI or ORAS artifact pulled from a registry, cached by the model store |

The predictive `items` array is not cosmetic. It is a batch envelope, and the predictive runtime batches server side with a default size of 32. That is why `transform.batch` exists in the stage catalog: sending small batches instead of single frames converts a per-frame HTTP round trip into amortized throughput, and the batch boundary is a pipeline concern rather than a stage-author concern.

The preview ships no meaningful predictive model catalog, so YOLO and any other detection model arrive through the bring-your-own path. `bundle_registry` therefore changes role. Instead of resolving a path inside the repository, it becomes a packaging and publishing step that produces an ONNX artifact in an ORAS-compatible registry, plus a `Model` resource that references it. Local development keeps the file path behavior behind the same interface.

### Stage behavior

The `infer.foundry` stage consumes the control plane abstraction rather than a URL:

* resolve `model_id` to an endpoint, route, and credential through the control plane
* gate startup on `wait_ready`, so a pipeline does not emit failures while the model store is still caching artifacts
* issue a warmup request during `setup` to pay ONNX session initialization cost before the first frame
* map deployment state changes to stage health, so a model rollout degrades one stage instead of crashing the pipeline
* select payload codec and auth header from the deployment workload type

This is where the current investment in deployment lifecycle, GPU capacity accounting, and route isolation pays off. Those semantics become the pipeline's model-binding layer instead of a standalone mock.

## Service topology

The manifest describes the graph. A deployment profile describes how the graph is cut into processes.

```yaml
kind: Deployment
spec:
  pipeline: warehouse-safety
  partitions:
    - name: ingest
      stages: [camera, letterbox, batch]
      replicas: 2
      shard:
        by: stream
        strategy: consistent-hash
    - name: analyze
      stages: [detect, ppe-rule, describe, events]
      replicas: 2
  edges:
    batch -> detect:
      channel: {kind: http, endpoint: http://analyze:9000/ingest}
```

A single partition yields the in-process runner. Multiple partitions yield microservices, with the runner exposing an ingress endpoint per cross-partition edge. Stage code is identical in both cases, which is the payoff of the channel abstraction.

Stream sharding lives here rather than in the pipeline manifest, because how many cameras a process handles is a deployment concern and not a description of the analysis. Each replica claims a deterministic subset of `spec.streams` by consistent hash, so adding a replica moves a minority of streams instead of reshuffling all of them. Setting `replicas` equal to the stream count produces one runner per camera without any change to the graph.

Target service inventory:

| Service | Responsibility |
|---------|----------------|
| `pipeline-runner` | Executes one partition of a pipeline graph for its assigned streams |
| `model-gateway` | Existing route and credential isolation for model deployments |
| `model-service` | Existing one-deployment-per-container inference server |
| `control-api` | Read-only pipeline status, stage health, and metrics aggregation |

### Manifest delivery

Manifests are files, delivered as a mounted ConfigMap and reconciled from Git. The `control-api` service reads status and never owns state, so there is no bespoke manifest database to operate, back up, or reconcile against the cluster.

The end state is a `Pipeline` CRD with its own operator, mirroring how `ModelDeployment` already works. That is the idiomatic shape for this environment and it makes pipelines a first-class cluster resource with the same reconciliation, status, and RBAC story as model deployments. Building a separate control plane first would only create something to migrate away from, so the ConfigMap path is deliberately structured as a subset: the manifest schema is already `apiVersion` plus `kind` plus `spec`, so promoting it to a CRD is a packaging change rather than a rewrite.

## Repository layout

```text
packages/
  tiger-core/            envelope, stage, channel, registry, graph, runner, telemetry
  tiger-stages-video/    rtsp, file, folder, sample, letterbox, clip writer
  tiger-stages-infer/    foundry client, infer stage, workload adapters
  tiger-stages-rules/    threshold, dwell, tracker
  tiger-stages-sinks/    jsonl, mqtt, blob
services/
  pipeline-runner/       runner entrypoint, partition ingress, health and metrics
  model-runtime/         current apps/local_model_runtime, refactored
pipelines/               example manifests
deployments/             deployment profiles and Kubernetes manifests
models/                  model packaging, Model and ModelDeployment resources
docker/                  per-service Dockerfiles
tests/
  conformance/           channel and stage protocol suites reused by all packages
```

Each package is independently installable, which is what makes third-party stages practical and keeps the core free of ONNX, PyAV, and MQTT dependencies.

## Technology choices

Python remains the implementation language for the framework. The existing ONNX, deployment, and adapter code is Python, the stage-author audience is Python-first, and asyncio handles the concurrency shape well since the workload is I/O bound at the pipeline layer and offloaded to native code at the inference layer.

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Async runtime | asyncio | Standard, no framework lock-in, integrates with FastAPI |
| HTTP surface | FastAPI and uvicorn | Replaces hand-rolled `http.server`, gives OpenAPI and validation for free |
| Config and schema | pydantic v2 | Typed stage configs, precise manifest errors |
| Video decode | PyAV | Direct libav bindings, correct RTSP timestamp and reconnect handling; OpenCV is heavier and less precise here |
| Metrics | prometheus-client | Scrape endpoint per runner |
| Tracing | OpenTelemetry | Envelope carries traceparent across channels |

One place justifies leaving Python. If RTSP decode plus JPEG encode becomes the bottleneck at high camera counts, a Rust or Go ingest binary can replace `source.rtsp` behind the same source contract, publishing frames over a shared-memory or gRPC channel. The channel abstraction makes that a later, contained decision rather than an upfront commitment. Do not take it until measurements demand it.

## Local development fidelity

The primary deployment target runs on an Arc-enabled Kubernetes cluster, which no workstation provides. Development therefore proceeds on a fidelity ladder, where each tier is a strict superset of the one below and no tier blocks work on the others.

| Tier | Environment | Validates | Gated |
|------|-------------|-----------|-------|
| 1 | Workstation, no cluster | Pipeline framework, stage logic, `LocalControlPlane`, OCI artifact packaging | No |
| 2 | k3d on the workstation, operator installed by Helm | Real CRDs, real endpoints, real auth, real model store | Operator artifacts only |
| 3 | Arc-enabled cluster | Arc extension install, Entra ID auth, GPU scheduling, disconnected operations | Yes |

The Helm install channel is what makes Tier 2 possible. Its prerequisites are ordinary cluster components with no dependency on Azure Local, so the operator can run on a local k3d cluster once its artifacts are obtainable. That channel also excludes Entra ID authentication and falls back to API keys, which matches the credential model the current code already implements.

### What the gate actually covers

The artifact situation was verified rather than assumed, because it determines how much work can proceed today.

| Component | Source | Available now |
|-----------|--------|---------------|
| cert-manager, trust-manager | upstream Jetstack charts | Yes |
| Gateway API CRDs v1.4.0 or later | upstream | Yes |
| Gateway API Inference Extension CRDs | upstream | Yes |
| Istio 1.29 or later as a Gateway API controller | upstream | Yes |
| Local OCI registry and `oras` tooling | `registry:2` image | Yes |
| Foundry Local operator chart and images | preview onboarding | No |

Two findings shaped this table. The registry referenced in the disconnected install documentation, `edgeartifacts.edgeacr.autonomous.cloud.private`, is an air-gapped mirror internal to an Azure Local appliance and does not resolve publicly, so it is not an access path. A search of the public Microsoft Container Registry catalog returned no Foundry Local operator repository, so the operator cannot be pulled anonymously today.

The gate is subscription-level preview onboarding, not a hardware requirement. Everything except the operator itself is ungated, which is why Phase 0 can build most of Tier 2 before access arrives.

## Migration plan

Existing tests pin contracts that this design intentionally reshapes. Each phase states what happens to them.

### Phase 0: Baseline and de-risking

This phase exists because the highest-uncertainty item in the plan, bring-your-own model packaging, was originally scheduled after several phases of work that depend on it. Pulling it forward converts a late structural risk into an early, cheap answer. None of this phase requires a pipeline framework, and none of it is blocked by preview access.

Start the preview onboarding request first, since it has the longest lead time and sits on the critical path for the Foundry-native claim.

Capture current behavior as characterization tests: gateway routing, credential isolation, payload validation, and YOLO detection output on a fixed sample image. These become the regression net for everything that follows.

Validate model packaging against a local registry:

* run `registry:2` locally as the stand-in for the operator's model store
* package `models/yolo/model.onnx` as an OCI artifact with `oras push`, recording media types and annotations
* pull it back into a clean directory and verify the digest and that the ONNX file loads
* script both directions so the same procedure can later target a real registry unchanged

Build the ungated portion of the Tier 2 cluster:

* create a k3d cluster and wire it to the local registry
* install cert-manager and trust-manager, then confirm the `certificates.cert-manager.io` CRD exists
* install Gateway API CRDs and the Inference Extension CRDs, then Istio as a Gateway API controller
* verify Istio is running and the gateway CRDs are registered

The cluster then sits ready, and onboarding turns Tier 2 into a single operator install rather than a multi-day environment build.

Use `compute: cpu` throughout this phase. The question being answered concerns packaging and contract shape, not throughput, and CPU avoids NVIDIA device plugin setup under WSL2 entirely.

Exit criteria: characterization tests pass, a YOLO OCI artifact round-trips through a local registry, and the k3d cluster reports healthy cert-manager, Gateway API, and Istio components.

### Phase 1: Extract the core

Create `packages/tiger-core` with `Envelope`, `Stage`, `Channel`, `InProcChannel`, the registry, the manifest loader, and the runner. No behavior change to the model runtime. Add the conformance suites. Deliverable: a two-stage pipeline of `source.file` into `sink.jsonl` runs from a manifest.

### Phase 2: First real pipeline

Port letterboxing out of `yolo_inference.py` into `transform.letterbox`, wrap the model runtime call in `infer.foundry`, and add `source.rtsp` plus `sink.jsonl`. Deliverable: a video file or RTSP stream produces detection events end to end through a manifest.

Mapping from current code:

| Current | Becomes |
|---------|---------|
| `yolo_inference._letterbox`, `_decode_image` | `transform.letterbox` stage |
| `yolo_inference._postprocess`, `_nms` | model service internals, unchanged |
| `workload_adapters.PredictiveAdapter` | payload codec used by `infer.foundry` |
| `workload_adapters.GenerativeAdapter` | payload codec used by `infer.foundry` |
| `bundle_registry` | model packaging step plus control plane resolution |

### Phase 3: Foundry control plane split and contract correction

Introduce `FoundryControlPlane`, refactor `LocalFoundryDeploymentRuntime` into `LocalControlPlane`, and add readiness gating and warmup to `infer.foundry`. Replace `http.server` with FastAPI in the model service and gateway.

Correct the three contract mismatches against the operator in the same pass, since they touch the same code paths:

* switch the predictive payload to the `items` array with `content_type` and `encoder` fields
* switch predictive auth to `X-API-Key` while generative retains `Authorization: Bearer`
* add `transform.batch` and wire batch size to the predictive runtime's server-side batching

Contract tests move from asserting mock dispatch to asserting control-plane behavior, and HTTP tests target the FastAPI app through its test client. The characterization tests from Phase 0 are updated deliberately here, with each change traceable to a documented operator behavior rather than to convenience.

### Phase 4: Model packaging and Kubernetes control plane

Promote the Phase 0 packaging script to a real registry, author the corresponding `Model` and `ModelDeployment` resources, and implement `KubernetesFoundryControlPlane` against `foundrylocal.azure.com/v1`. Install the operator onto the k3d cluster prepared in Phase 0, which reduces this step to a single Helm install once preview access lands.

Deliverable: the same pipeline runs unchanged against the real operator at Tier 2, selected purely by which control plane implementation is configured. Tier 3 concerns, Arc extension packaging, Entra ID authentication, and GPU scheduling, are validated separately when cluster access is available and are not prerequisites for this deliverable.

### Phase 5: Rules, sinks, and events

Add tracking, threshold and dwell rules, clip writing with `RetentionPolicy`, and the MQTT sink. Deliverable: dwell-based events with attached clips, published to a broker, with retention verified under a deliberately undersized volume.

### Phase 6: Partitioning and sharding

Add `HttpChannel`, the deployment profile loader, per-partition runner ingress, and consistent-hash stream sharding. Deliverable: the same manifest runs single-process and split across two containers with no stage code change, verified by running the same end-to-end assertions against both topologies.

## Testing strategy

| Layer | Approach |
|-------|----------|
| Stage protocol | Shared conformance suite every stage runs: setup and teardown idempotence, cancellation, health reporting, config validation |
| Channel | Shared conformance suite: ordering, capacity, each overflow policy, close semantics, stats accuracy |
| Graph loader | Property tests over generated manifests for cycle, type, and reachability rejection |
| Inference | Golden-frame fixtures asserting detection output within tolerance |
| Foundry contract | Recorded operator request and response shapes, asserted against both control plane implementations |
| Retention | Undersized volume soak, asserting eviction and attributed drop counts rather than failure |
| End to end | A short sample clip through a full manifest, asserting event count and latency budget |
| Topology equivalence | Identical assertions against in-process and partitioned deployments |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Multi-camera model | N streams per runner with per-stream isolated chains, sharded across replicas by the deployment profile | Inference is a shared external plane, so the runner needs isolation rather than a scheduler |
| Manifest storage | Files and ConfigMap via GitOps now, `Pipeline` CRD and operator later, `control-api` read-only | Matches the operator pattern already present; avoids a bespoke control plane to migrate away from |
| Retention ownership | Sinks enforce, framework supplies `RetentionPolicy` and a disk-pressure signal | Only the sink knows its storage medium; pressure becomes measured drops instead of outage |
| Foundry target | Azure Local operator `foundrylocal.azure.com/v1` as primary, `LocalControlPlane` for dev and test | The Windows and macOS Foundry Local SDK is a separate product and not the deployment target |
| Contract corrections | Fix payload, auth header, and model packaging in Phase 3 and Phase 4 | Divergence from the real operator would invalidate the reference architecture claim |

## Remaining risks

* Foundry Local on Azure Local is in preview, so CRD fields and endpoints can change before general availability. `FoundryControlPlane` exists partly to contain that blast radius, and the recorded contract tests are the early warning system.
* Operator artifacts require preview onboarding, which is an external dependency with an unpredictable lead time. The mitigation is structural: Phase 0 builds everything ungated, so only Phase 4 blocks on access, and it blocks on a Helm install rather than on environment construction.
* The preview has no meaningful predictive model catalog, so every detection model depends on the bring-your-own packaging path working reliably. Phase 0 validates the artifact half of that path locally; the operator half stays unproven until Tier 2 is reachable.
* Server-side predictive batching interacts with latency budgets. `transform.batch` needs measurement to choose `max_wait_ms`, since a batch window that helps throughput can breach an event-detection deadline.

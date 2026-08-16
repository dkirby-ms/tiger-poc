---
title: Local Model Runtime
description: Deterministic Foundry-compatible deployment contract harness for the Tiger PoC local model runtime
author: Tiger PoC
ms.date: 2026-08-15
ms.topic: reference
keywords:
  - foundry local
  - model runtime
  - deployment contract
  - testing
estimated_reading_time: 3
---

## Overview

`local_model_runtime` is a generic model service for Tiger PoC. One instance
runs per model, serving the Foundry-compatible contract over HTTP: model
availability, route selection, authentication, and request payload semantics.

It does not yet load model weights; inference responses are deterministic
contract responses. Use
[`scripts/verify-local-model-runtime.sh`](../../scripts/verify-local-model-runtime.sh)
to build, start, and probe every containerized model service.

## Deployments

Every model runs in its own service instance of the same generic
`ModelService` implementation. There is no per-model service code; the model
identity, bundle reference, workload contract, and resource allocation come
from the service catalog at [`models/services.json`](../../models/services.json).

| Model ID             | `workloadType` | Route                  | Accepted payload | Default state |
|----------------------|----------------|------------------------|------------------|---------------|
| `yolo`               | `predictive`   | `/v1/predict`          | `image`          | `Running`     |
| `florence-2`         | `predictive`   | `/v1/predict`          | `image`          | `Running`     |
| `phi-4-multimodal`   | `generative`   | `/v1/chat/completions` | `messages`       | `Running`     |

Catalog field names follow the Foundry Local `ModelDeployment` CRD:
`workloadType`, `compute`, `runtime`, `replicas`, `port`, and
`resources.requests` / `resources.limits`. `runtime: vllm` requires
`compute: gpu` and does not serve predictive workloads.

Each deployment has a distinct configured secret. The contract exposes the
secret in its successful response for deterministic test assertions; it must
not be used as an example of production credential handling.

## Model Services

`ModelServiceSupervisor` owns one `ModelService` per model and starts, stops,
and reports health for each independently. A service is bound to a single
bundle reference and raises `RuntimeError` if a second model bundle is loaded
into it, so no process ever holds more than one set of model weights.

```python
from apps.local_model_runtime import ModelServiceSupervisor, load_default_specs

supervisor = ModelServiceSupervisor(load_default_specs())
supervisor.start_all()
supervisor.stop("phi-4-multimodal")

health = supervisor.health()
assert health["healthy"] is False
```

Resource configuration is per deployment, expressed as Kubernetes quantities
under `resources.requests` and `resources.limits`, with `limits.gpu` counting
whole GPUs. Adding a model means adding a catalog entry, not a new service
implementation.

## Lifecycle States

Services report the states the inference operator uses, so client behavior
can be tested against the same values as Azure Local:

| State         | Meaning |
|---------------|---------|
| `Pending`     | Registered but not scheduled; zero ready replicas |
| `Creating`    | Bundle downloading into the model cache |
| `Running`     | All replicas ready; the endpoint accepts requests |
| `Updating`    | A new spec is being applied |
| `Error`       | Failed with an actionable `message` and `reason` |
| `Terminating` | Being removed |

`health()` reports `state`, `ready`, `deploymentReady`, `serviceReady`,
`endpointReady`, `restartCount`, and `replicas.desired` / `ready` /
`available`.

Failure reasons are `ModelDownloadFailed`, `InsufficientGpuCapacity`,
`ModelRuntimeUnhealthy`, and `BundleConflict`. A `503` from an unready
deployment carries the state and reason so clients can defer rather than
retry blindly.

## Simulate Lifecycle and Faults

Construct services with a model cache delay, and give the supervisor a GPU
budget so scheduling can fail the way it does on a real node:

```python
from apps.local_model_runtime import ModelServiceSupervisor, load_default_specs

supervisor = ModelServiceSupervisor(load_default_specs(), gpu_capacity=1, cache_steps=2)
supervisor.start("yolo")            # Creating while the cache fills
supervisor.progress("yolo")         # advance one cache step
supervisor.progress("yolo")         # Running

supervisor.start("florence-2")      # Error: InsufficientGpuCapacity
supervisor.get("yolo").fail("ONNX Runtime session crashed")
supervisor.restart("yolo")          # restartCount increments, others untouched
```

Deployments fail independently: one `Error` never changes another
deployment's state.

## Gateway

`Gateway` mirrors the operator's HTTPRoute behavior. Each deployment is
served at its `endpoint.path` prefix, defaulting to `/<deployment-name>`,
rewritten to `endpoint.rewritePath` before reaching the backend:

```bash
python -m apps.local_model_runtime --gateway
curl -X POST http://localhost:8080/yolo/v1/predict \
  -H 'Authorization: Bearer yolo-secret' \
  -d '{"image": "base64-image-data"}'
```

`GET /routes` lists the active routes and `GET /healthz` reports gateway
status. Deployments with `endpoint.exposure: none` keep their direct service
URL but are not routed. An unreachable backend returns `502` with
`upstream_unreachable`.

## Run a Service

Each process hosts exactly one catalog entry, selected with `--model-id` or
the `MODEL_ID` environment variable:

```bash
python -m apps.local_model_runtime --model-id yolo
```

The service binds the catalog port (`8001`, `8002`, `8003` by default) and
exposes only the route its workload owns:

| Endpoint               | Method | Purpose |
|------------------------|--------|---------|
| `/healthz`             | GET    | Service health; `503` while stopped |
| `/v1/models`           | GET    | The single model this service hosts |
| `/v1/predict`          | POST   | Predictive services only |
| `/v1/chat/completions` | POST   | Generative services only |

Requests authenticate with the service credential in either an
`Authorization: Bearer` or `api-key` header:

```bash
curl -X POST http://localhost:8001/v1/predict \
  -H 'Authorization: Bearer yolo-secret' \
  -d '{"image": "base64-image-data"}'
```

Failures map to `401` for a wrong credential, `404` for a route the service
does not own, `400` for a payload that does not match the workload, and `503`
while the service is stopped. Error bodies carry an OpenAI-style envelope
naming the offending field:

```json
{
  "status": "wrong_payload",
  "error": {
    "type": "invalid_request_error",
    "code": "wrong_payload",
    "message": "'confidence_threshold' must be between 0 and 1",
    "param": "confidence_threshold",
    "model": "yolo"
  }
}
```

## Response Contracts

Response shape is chosen by workload, so all predictive services answer alike
and the generative service is OpenAI chat-completions compatible.

| Workload     | Response `object` | Body |
|--------------|-------------------|------|
| `predictive` | `prediction`      | `predictions` array plus `model`, `created`, and `usage` |
| `generative` | `chat.completion` | `choices[].message`, `finish_reason`, and token `usage` |

Weights are not loaded yet, so `predictions` is empty and the assistant
message states that the service is validating the contract only.

All three services run together from a single image:

```bash
docker compose up --build model-yolo model-florence-2 model-phi-4-multimodal
```

## Use the Contract

Import `LocalFoundryDeploymentRuntime`, then call `dispatch` with a model ID,
route, secret, and payload:

```python
from apps.local_model_runtime import LocalFoundryDeploymentRuntime

runtime = LocalFoundryDeploymentRuntime()
result = runtime.dispatch(
    model_id="yolo",
    route="/v1/predict",
    secret="yolo-secret",
    payload={"image": "base64-image-data", "confidence_threshold": 0.5},
)

assert result["status"] == "ok"
```

Predictive deployments require an `image` field and reject a `messages` field.
The chat-completions deployment requires `messages` and rejects an `image`
field. Extra fields are otherwise retained outside the contract's concern.

## Simulate Readiness

Tests can model an unavailable deployment with `set_ready`, which also stops
or starts the backing service:

```python
runtime.set_ready("yolo", False)
result = runtime.dispatch(
    model_id="yolo",
    route="/v1/predict",
    secret="yolo-secret",
    payload={"image": "base64-image-data"},
)

assert result["status"] == "not_ready"
```

Calling `set_ready` for an unknown model raises `KeyError`.

## Responses

`dispatch` returns a dictionary with a `status` field. The contract supports
the following outcomes:

| Status          | Meaning |
|-----------------|---------|
| `ok`            | Model, route, secret, readiness, and payload are valid |
| `unknown_model` | No deployment contract matches the requested model ID |
| `not_ready`     | The requested deployment is unavailable |
| `wrong_route`   | The requested route differs from the deployment route |
| `unauthorized`  | The supplied secret does not match the deployment secret |
| `wrong_payload` | The supplied payload does not match the route's contract |

Validation stops at the first failure in this order: model lookup, readiness,
route, secret, then payload.

## Verify

Run the focused contract tests from the repository root:

```bash
pytest tests/test_foundry_local_deployment_contracts.py tests/test_model_services.py tests/test_model_service_http.py
```

For model artifact and containerized service verification, see
[the model setup guide](../../docs/model-setup.md) and run:

```bash
./scripts/verify-local-model-runtime.sh
```
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

`local_model_runtime` is an in-process, deterministic harness for validating
the Foundry-compatible deployment contract used by Tiger PoC. It models model
availability, route selection, authentication, and request payload semantics.

It does not load model artifacts or expose an HTTP server. Use
[`scripts/verify-local-model-runtime.sh`](../../scripts/verify-local-model-runtime.sh)
to verify the containerized local runtime service.

## Deployments

| Model ID             | Route                  | Accepted payload | Default state |
|----------------------|------------------------|------------------|---------------|
| `yolo`               | `/v1/predict`          | `image`          | Ready         |
| `florence-2`         | `/v1/predict`          | `image`          | Ready         |
| `phi-4-multimodal`   | `/v1/chat/completions` | `messages`       | Ready         |

Each deployment has a distinct configured secret. The contract exposes the
secret in its successful response for deterministic test assertions; it must
not be used as an example of production credential handling.

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

Tests can model an unavailable deployment with `set_ready`:

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
pytest tests/test_foundry_local_deployment_contracts.py
```

For model artifact and containerized service verification, see
[the model setup guide](../../docs/model-setup.md) and run:

```bash
./scripts/verify-local-model-runtime.sh
```
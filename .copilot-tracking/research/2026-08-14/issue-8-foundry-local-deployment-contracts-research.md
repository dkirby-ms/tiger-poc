---
title: Foundry Local Deployment Contract Research for Issue 8
description: Research summary for Tiger PoC issue 8 covering Foundry Local deployment contracts, model routing, auth boundaries, payload expectations, readiness, and the recommended testing approach
author: Tiger PoC
ms.date: 2026-08-14
ms.topic: reference
keywords:
  - foundry local
  - model deployment
  - issue 8
  - contract testing
  - azure local
estimated_reading_time: 8
---

## Status

Complete

## Research scope

This note answers the issue question for Tiger PoC: how the system design defines the three Foundry Local model deployments, what the contract requirements are for those deployments, and what testing strategy best covers those requirements for issue 8.

## Evidence base

The design is most clearly defined in the architecture and parity notes in the project docs, especially the architecture diagram and the edge parity section of the system design.

The relevant findings are:

* The pre-processor and inference API resolve each model to its own Foundry Local ModelDeployment endpoint.
* YOLO and Florence-2 use /v1/predict.
* Phi-4-multimodal uses /v1/chat/completions.
* Each ModelDeployment owns one model, its Deployment, Service, API key Secret, and optional Gateway route.
* Multiple models run concurrently as independent deployments rather than in one shared runtime process.
* The local development parity model expects one service per model and one deployment per model.
* The design explicitly calls for predictive and generative endpoint contract tests in CI before promotion.

## How the system design defines the three deployments

The architecture names three model deployments in the edge inference plane:

| Deployment | Role | Model family | Endpoint contract | Payload class |
|------------|------|--------------|------------------|--------------|
| YOLO | Predictive vision detection | YOLO | /v1/predict | Predictive object detection request/response |
| Florence-2 | Predictive multimodal analysis | Florence-2 | /v1/predict | Predictive visual inference request/response |
| Phi-4-multimodal | Generative multimodal chat | Phi-4-multimodal | /v1/chat/completions | Generative chat-completion payload |

The design is not a single shared model service; it is explicitly a three-deployment pattern. The summary states that each deployment is independent and can be scheduled with its own compute and resource limits. This matters because the project treats model execution as a deployment concern, not a code-path concern.

From the design text:

* Each ModelDeployment owns one model reference, one readiness state, one deployment-specific endpoint, and one independent credential.
* Model runtime is selected by deployment configuration, not by hardcoded service logic.
* The three model deployments are run concurrently, which implies the API layer must route to the correct instance rather than assume one model is a global default.

## Contract requirements derived from the design

### 1. One model per deployment

The design requires a strict one-model-per-deployment model. The architecture explicitly says:

* Each ModelDeployment owns one model, its Deployment, Service, API key Secret, and optional Gateway route.
* Multiple models run concurrently as independent deployments rather than in one shared runtime process.

This means the contract requirement is:

* A deployment must correspond to exactly one model family and one model bundle reference.
* The deployment must not silently serve multiple models behind one route or one secret.
* The runtime metadata for the deployment should include a clear model identifier and bundle digest.

### 2. Route isolation

The route model is central to the contract:

* YOLO and Florence-2 use /v1/predict.
* Phi-4-multimodal uses /v1/chat/completions.

The requirement is not just different paths; it is route isolation and route correctness. A contract test must prove that:

* A predictive deployment does not accept a generative chat-completion request.
* A generative deployment does not accept a predictive request.
* The request path is not shared across multiple deployments.
* Each deployment has a deployment-specific endpoint or gateway route that maps to one model identity only.

This also aligns with the explicit CI goal: validate routing behavior before promotion.

### 3. Auth separation

The design also states that each deployment owns an independent API key Secret. This is a strong contract requirement. A deployment must not share credentials with another deployment. The design further notes local parity with per-deployment API keys and routes.

The contract requirement is:

* Each deployment has its own credential.
* Valid requests must include the matching credential for that deployment.
* A request with another deployment's key should be rejected.
* Auth must be validated per deployment, not per service group or per runtime process.

This is especially important because the project expects multiple models to be active at the same time. Shared or global auth would undermine route isolation and create cross-deployment leakage.

### 4. Predictive versus generative payload contracts

The project distinguishes predictive and generative workloads by the API endpoint and expected payload semantics:

* Predictive endpoints use /v1/predict for object detection and visual inference requests.
* Generative endpoints use /v1/chat/completions for multimodal chat-style generation.

The payload contract is therefore not merely different URLs; it is different request and response semantics.

Predictive contract expectations:

* Requests are generally inference requests against a visual model.
* Response types are normalized detection outputs and model-specific inference results.
* The output is intended to feed event rules and downstream inference normalization.

Generative contract expectations:

* Requests follow chat-completion semantics.
* Responses are conversation or content-generation style responses rather than detection outputs.
* The payload should not be treated as equivalent to the predictive detection schema.

The issue requirement here is to ensure that deployment selection is based on route and payload contract, not on a generic fallback or shared response schema.

### 5. Readiness behavior

The system design includes the phrase model lifecycle and readiness state. Although not fully enumerated in prose, the requirement is clear: a deployment cannot be treated as routable before it is ready.

The implied contract is:

* A ModelDeployment has a readiness state.
* A deployment that is not ready must not receive traffic.
* Ready status must be verified before the route is considered valid for use.
* A deployment can be independently started, scaled, or failed without affecting other deployments.

The design's local development parity specifically says to model the ModelDeployment lifecycle locally, including readiness state and deployment-specific endpoint. This is a direct requirement for issue 8 and should be tested explicitly.

### 6. Failure behavior

The design does not spell out a complete failure matrix, but the implied failure contract is important and testable.

The expected behavior is:

* A failed deployment does not silently route traffic to a healthy deployment.
* A missing or invalid auth key is rejected at the deployment boundary.
* A request sent to the wrong endpoint or wrong model-specific route is rejected rather than misrouted.
* A deployment in a failed or non-ready state should surface a clear failure signal, including 4xx or 5xx semantics depending on the contract.
* The system should preserve isolation so one deployment's outage does not cause another deployment's traffic to break.

Because the architecture is built around independent deployments, the issue requirement is not a single global fallback; it is per-deployment fault isolation.

## Recommended testing approach for issue 8

The strongest approach is to treat issue 8 as a deployment contract test suite, not simply a smoke test. The design itself calls for predictive and generative endpoint contract tests in CI, which is the correct anchor.

### Test strategy

1. Model each deployment as a distinct contract subject
   * YOLO predictive deployment
   * Florence-2 predictive deployment
   * Phi-4-multimodal generative deployment

2. Validate identity and scope per deployment
   * exactly one model reference per deployment
   * one route per deployment
   * one auth secret per deployment
   * one readiness state per deployment

3. Validate route isolation explicitly
   * call /v1/predict against YOLO and Florence-2 with valid auth and ensure the right model is hit
   * call /v1/chat/completions against Phi-4 with valid auth and ensure generative semantics are used
   * send each deployment the wrong request shape and verify rejection

4. Validate auth separation explicitly
   * use the correct secret for one deployment and verify success
   * use a different deployment's secret and verify rejection
   * verify that either auth failure is not treated as a route fallback to another deployment

5. Validate payload semantics explicitly
   * predictive deployment requests use the predictive body contract
   * generative deployment requests use the chat-completion body contract
   * response parsing must follow the type-specific schema and cannot be cross-used for detection and generation outputs

6. Validate readiness and failure gating
   * start the service in non-ready state and assert no traffic is accepted
   * mark a deployment as failed and ensure the route is not treated as available
   * assert that failed auth or invalid route failure does not affect sibling deployments

### Recommended test matrix

| Dimension | YOLO | Florence-2 | Phi-4-multimodal |
|-----------|------|------------|------------------|
| Deployment count | 1 | 1 | 1 |
| Route | /v1/predict | /v1/predict | /v1/chat/completions |
| Auth | unique secret | unique secret | unique secret |
| Payload | predictive inference | predictive inference | generative completion |
| Success condition | valid predictive response | valid predictive response | valid chat-completion response |
| Wrong-route failure | reject | reject | reject |
| Wrong-auth failure | reject | reject | reject |
| Non-ready failure | reject | reject | reject |
| Dependency failure isolation | isolated | isolated | isolated |

### Implementation recommendation

The best issue-8 test suite is a small contract harness that runs against the local Foundry-compatible mock or canonical local deployment stack and checks these invariants:

* one deployment = one model identity
* route names must match the deployment contract
* auth is unique and per deployment
* predictive and generative payloads follow different schemas and are never interchanged
* readiness is enforced before traffic is routed
* failures are isolated and do not silently route to another deployment

This should be exercised in CI against recorded video and a deterministic local mock so it validates routing behavior before promotion.

## Conclusion

The system design establishes three independent Foundry Local deployments and makes their boundaries explicit: one model per deployment, deployment-specific route, unique auth, and distinct predictive versus generative payload semantics. The contract risk is not in the model code itself; it is in the boundary conditions between deployments. Issue 8 should therefore be solved as a deployment contract suite that validates isolation, authorization, route correctness, payload semantics, and readiness/failure behavior before promoting the stack.

The core design statement that should guide the final issue resolution is this:

* The platform must treat each model deployment as an independently addressable, independently authenticated, independently ready service, and the tests must prove this in CI.

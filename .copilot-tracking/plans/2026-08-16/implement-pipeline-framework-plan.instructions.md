<!-- markdownlint-disable-file -->
# Implement Pipeline Framework Plan

## User Requests

* Execute the work represented by the attached issue plan.
* Do not create or update GitHub issues.
* Pause only when a specific user decision is required.

## Objectives

Deliver the locally executable pipeline platform in dependency order, preserve
current model-runtime behavior except for documented target-contract changes,
and identify preview-gated integration work without blocking local progress.

## Context Summary

Follow the repository Python, Python test, Bash, Markdown, and writing-style
instructions. Use the architecture and migration phases in
`docs/pipeline-framework.md`. Research is recorded in
`.copilot-tracking/research/2026-08-16/pipeline-framework-research.md`.

## Implementation Checklist

### Phase 0: Baseline and test bootstrap

<!-- parallelizable: false -->

* [x] Add reproducible development dependencies usable through `uv`.
* [x] Run and record the existing test baseline.
* [x] Add characterization coverage where contract behavior is unpinned.

### Phase 1: Core in-process framework

<!-- parallelizable: false -->

* [x] Add immutable envelopes and shared payload contracts.
* [x] Add bounded channels with explicit overflow policies and statistics.
* [x] Add stage registry and typed manifest validation.
* [x] Add lifecycle-safe asynchronous graph runner.
* [x] Add channel, manifest, registry, and runner tests.

### Phase 2: First complete local workflow

<!-- parallelizable: false -->

* [x] Add file image source and letterbox transform.
* [x] Add local Foundry inference stage with readiness gating.
* [x] Add threshold and dwell stages.
* [x] Add JSONL event sink and retention policy.
* [x] Add CLI, example manifest, and end-to-end tests.

### Phase 3: Foundry contract correction

<!-- parallelizable: false -->

* [x] Introduce a `FoundryControlPlane` protocol and local implementation.
* [x] Correct predictive batching payloads and workload-specific auth.
* [x] Update HTTP, gateway, deployment, and adapter tests deliberately.
* [x] Preserve explicit compatibility boundaries for existing callers.

### Phase 4: Local delivery and observability

<!-- parallelizable: true -->

* [x] Add model artifact packaging and verification scripts where tooling permits.
* [x] Add pipeline health and channel/stage metrics snapshots.
* [x] Align setup and repository documentation with implemented paths.

### Phase 5: External and distributed integrations

<!-- parallelizable: false -->

* [ ] Implement locally testable HTTP partitioning and deterministic sharding.
* [x] Document the operator, Kubernetes, MQTT, and Arc validation gates.
* [ ] Defer only live verification that requires unavailable credentials,
  artifacts, hardware, or a user-selected deployment environment.

## Dependencies

* Python 3.11 or later
* `uv` for isolated dependency execution
* Existing ONNX Runtime, NumPy, and Pillow dependencies
* PyYAML and Pydantic for manifest parsing and validation
* pytest and pytest-asyncio for validation

## Success Criteria

* Focused tests pass after every implementation phase.
* The full local suite passes at completion.
* The example manifest can be validated from the CLI.
* No secret is stored in a pipeline manifest.
* Preview-only claims are not marked complete without live verification.

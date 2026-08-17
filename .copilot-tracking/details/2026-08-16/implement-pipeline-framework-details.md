<!-- markdownlint-disable-file -->
# Pipeline Framework Implementation Details

## Context

* Plan: `.copilot-tracking/plans/2026-08-16/implement-pipeline-framework-plan.instructions.md`
* Research: `.copilot-tracking/research/2026-08-16/pipeline-framework-research.md`
* Architecture: `docs/pipeline-framework.md`

## Phase details

### Phase 0

Use a development requirements file and `uv run --with-requirements` so the
repository remains usable without a global Python environment. Establish the
existing suite result before changing runtime contracts.

### Phase 1

Keep the first graph runtime in `apps/pipeline_framework`. Support one source,
one input per worker, and fan-out. Reject fan-in until merge ordering and close
semantics are specified. Use one bounded channel per edge and close downstream
channels when an upstream task drains.

### Phase 2

Use finite image and folder inputs first. Keep decoding and model execution off
the event loop with `asyncio.to_thread`. Resolve model routes and credentials
from the injected control plane rather than the manifest. Emit negative rule
evaluations so dwell state can reset deterministically.

### Phase 3

Change predictive requests to a validated `items` array and preserve ordering
in responses. Authenticate predictive calls with `X-API-Key`; authenticate
generative calls with bearer tokens. Avoid returning expected credentials in
error payloads.

### Phase 4

Expose bounded counters and health snapshots without requiring a metrics
server. Package model artifacts only through scripts that can verify digests
locally. Keep operator installation separate from ungated environment setup.

### Phase 5

Use the channel abstraction for local HTTP partitioning and compare results
against in-process execution. Record external prerequisites before attempting
operator, MQTT, or Arc validation.

## Validation

Run focused pytest files after each phase, then the full suite. Validate the
example manifest through the module CLI. Use shell syntax checks for new Bash
scripts and avoid starting persistent services unless an end-to-end check needs
one.

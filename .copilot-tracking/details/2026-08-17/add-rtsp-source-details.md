<!-- markdownlint-disable-file -->
# Add RTSP Source Details

## Context

* Plan: `.copilot-tracking/plans/2026-08-17/add-rtsp-source-plan.instructions.md`
* Architecture: `docs/pipeline-framework.md`
* Existing source: `apps/pipeline_framework/stages/file_source.py`

## Implementation Notes

The source owns its active PyAV container so teardown can close network I/O.
Blocking open and decode calls run through `asyncio.to_thread`. Reconnect waits
use `asyncio.sleep`, making backoff cancellation immediate.

Each connection maps the first media timestamp to the wall clock at connection
time. Later frames retain media deltas. Across reconnects, capture timestamps
are clamped to remain monotonic while sequence numbers continue unchanged.

The manifest stores `url_env`, not a URL. Direct `url` configuration remains
available for non-secret local simulators but documentation recommends the
environment path.

## Validation

Use injected or monkeypatched PyAV open calls and fake containers. Test one
failed connection followed by successful frames, target-FPS filtering, active
container closure, URL redaction from frame metadata, and manifest validation.

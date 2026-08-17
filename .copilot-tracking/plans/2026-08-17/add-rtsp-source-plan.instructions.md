<!-- markdownlint-disable-file -->
# Add RTSP Source Plan

## User Requests

* Continue with suggested work item 1: build RTSP support.
* Process a live RTSP feed instead of a static JPEG.

## Objectives

Add a production-shaped `source.rtsp` stage without changing downstream stage
contracts. Keep camera credentials out of manifests, preserve stream ordering
and media timing, reconnect after transient failures, and stop cleanly.

## Context Summary

The existing `Frame` and `Envelope` contracts already carry the data required
by downstream stages. PyAV is already a runtime dependency. The runner closes
outgoing channels and tears stages down after cancellation or failure.

## Implementation Checklist

### Phase 1: RTSP source

<!-- parallelizable: false -->

* [x] Add validated RTSP configuration and environment URL resolution.
* [x] Decode frames through PyAV with transport and timeout options.
* [x] Preserve sequence and media-relative capture timestamps.
* [x] Sample to a configured target FPS.
* [x] Reconnect with bounded backoff values repeated until cancellation.
* [x] Close the active PyAV container during teardown.

### Phase 2: Integration and documentation

<!-- parallelizable: false -->

* [x] Register `source.rtsp` as a built-in stage.
* [x] Add an RTSP pipeline manifest that contains no credential.
* [x] Document local invocation and environment variables.

### Phase 3: Validation

<!-- parallelizable: false -->

* [x] Test environment resolution and missing configuration.
* [x] Test reconnect, ordering, sampling, timestamps, and close behavior.
* [x] Validate both example manifests and run the full suite.

## Success Criteria

* A user can select `source.rtsp` and provide `TIGER_RTSP_URL` at runtime.
* Temporary open or decode failures reconnect without resetting sequence.
* Emitted timestamps follow media timing and remain monotonic across reconnects.
* Cancellation or teardown closes the active network container.
* No test requires a physical camera or live network.

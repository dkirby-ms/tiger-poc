<!-- markdownlint-disable-file -->
# Add RTSP Source Changes

## Summary

Added a reconnecting live RTSP source that emits the existing frame envelope,
plus a credential-free example manifest and local run documentation.

## Added

* `apps/pipeline_framework/stages/rtsp_source.py`
* `pipelines/rtsp-yolo.yaml`
* `tests/test_rtsp_source.py`
* RTSP implementation plan, details, log, changes, and review artifacts

## Modified

* Built-in stage registration
* Pipeline CLI interrupt handling
* Root and pipeline framework documentation

## Behavior

* Resolves camera URLs from `TIGER_RTSP_URL` by default
* Supports RTSP TCP or UDP and open/read timeouts
* Samples frames to a target FPS
* Preserves sequence and media-relative timing across reconnects
* Repeats bounded reconnect delays until cancellation
* Closes active containers during disconnect, cancellation, and teardown

## Validation

* 137 pytest tests passed
* Both example manifests validated
* Editor diagnostics reported no errors

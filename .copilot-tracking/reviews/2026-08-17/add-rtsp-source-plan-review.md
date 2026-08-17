<!-- markdownlint-disable-file -->
# Add RTSP Source Plan Review

## Request Fulfillment

* Complete: `source.rtsp` accepts a live RTSP or RTSPS feed.
* Complete: camera credentials can remain outside manifests.
* Complete: reconnect, target-FPS sampling, sequence, timestamps, and teardown
  are covered without a physical camera.
* Complete: a full RTSP-to-YOLO-to-JSONL manifest is included.
* Pending user smoke test: actual camera connectivity and codec compatibility.

## Quality Review

The source is isolated behind the existing `Frame` contract, so downstream
stages and the runner did not require RTSP-specific branches. Error health does
not include the endpoint, preventing credential leakage. Backoff resets only
after a usable frame arrives.

## Validation

* Full pytest suite: 137 passed
* RTSP focused suite: 5 passed
* File and RTSP manifest validation: passed
* Editor diagnostics: no errors

## Overall Status

Complete, with a real-feed smoke test remaining environment-dependent.

<!-- markdownlint-disable-file -->
# Add RTSP Source Planning Log

## Status

Implementation and automated validation are complete. A real-feed smoke test
requires a user-provided RTSP endpoint.

## Decisions

* Use a separate `source.rtsp` stage rather than overloading `source.file`.
* Resolve credentials from `TIGER_RTSP_URL` by default.
* Prefer RTSP over TCP while allowing UDP selection.
* Reconnect indefinitely with a configurable repeated backoff schedule.
* Preserve relative media timing and monotonic timestamps across reconnects.

## Validation Approach

No live camera is required for automated tests. Fake PyAV frames and containers
will exercise all control flow. A real feed remains a user-run smoke test.

## Validation Log

* Existing pipeline integration after first edit: 13 tests passed.
* Focused RTSP behavior: 5 tests passed.
* File and RTSP manifests validated successfully.
* Editor diagnostics reported no errors.
* Full suite passed with 137 tests.

## Implementation Adjustment

Backoff initially reset after opening a socket. Review identified that a socket
can open and immediately yield no frames, so reset now occurs only after a
usable frame is emitted. A focused test pins escalation for empty connections.


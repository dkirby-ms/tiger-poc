<!-- markdownlint-disable-file -->
# Planning Log: frontend dashboard

**Related Plan**: frontend-dashboard-plan.instructions.md

## Discrepancy Log

### Unaddressed Research Items

* DR-01: Need to confirm whether a browser can render the live RTSP stream directly.
  * Source: frontend-dashboard-research.md (Lines 1-120)
  * Reason: The repo does not include a browser-friendly stream adapter yet.
  * Impact: high

### Implementation Deviations

* DD-01: The dashboard will favor a stored-clip preview over a true live camera view.
  * Plan specifies: use a Vite dashboard and treat live preview as a separate stream-proxy task.
  * Implementation differs: the app will include a preview panel that points to a served local clip when available.
  * Rationale: This is the lowest-risk browser-safe preview that matches the current data model.

## Suggested Follow-On Work

* WI-01: Add a dedicated MJPEG or WebRTC proxy for true live camera preview (medium)
  * Source: Phase 2, Step 3
  * Dependency: dashboard MVP must be stable and user-validated first
* WI-02: Expand dashboard regression coverage around service health parsing and preview URL normalization (medium)
  * Source: Phase 3, Validation and handoff
  * Dependency: maintain the browser-safe preview contract and future API changes

## User Decisions

* ID-01: Prefer a saved-clip preview and explicit live-preview warning rather than attempting RTSP in-browser.
  * Rationale: Browser-native RTSP is not supported and the current repo has no compatible proxy.

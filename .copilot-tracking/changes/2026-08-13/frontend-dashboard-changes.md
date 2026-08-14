<!-- markdownlint-disable-file -->
# Release Changes: frontend dashboard

**Related Plan**: frontend-dashboard-plan.instructions.md
**Implementation Date**: 2026-08-13

## Summary

Add a lightweight Vite dashboard to the Tiger PoC for health monitoring, recent detection review, and a browser-safe preview panel aligned with the current local storage contract.

## Changes

### Added
* apps/dashboard/ - Vite React + TypeScript dashboard app
* .copilot-tracking/details/2026-08-13/frontend-dashboard-details.md - implementation details for the dashboard MVP
* .copilot-tracking/plans/logs/2026-08-13/frontend-dashboard-log.md - discrepancy tracking and follow-on work

### Modified
* .copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md - plan checklist updated as work completes

### Removed
* None

## Additional or Deviating Changes

* Browser preview uses saved clips from the local data directory rather than direct RTSP playback.
  * Reason: browser-native RTSP is not supported and the current repo does not expose a compatible stream proxy.
* Fixed preview integrity by exposing a local-store clip endpoint and normalizing file paths into browser-safe URLs.
  * Reason: absolute filesystem paths are not accessible from the browser and the app was previously masking real health errors behind synthetic fallback data.

## Release Summary

The dashboard MVP introduces a minimal observability app that polls the core service health endpoints and displays recent detections from the local-store endpoint. It includes a preview area that renders a saved clip via a browser-safe API route when present, preserves the actual backend error state instead of masking it with fallback data, and documents the live-preview limitation for the current RTSP-first pipeline. Validation evidence: the dashboard regression tests pass and the Vite production build completes successfully.

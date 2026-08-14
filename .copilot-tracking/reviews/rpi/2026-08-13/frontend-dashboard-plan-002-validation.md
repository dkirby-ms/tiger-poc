---
title: Frontend dashboard Phase 2 validation
description: Validation of the dashboard data-integration phase against the plan, changes log, and research
ms.date: 2026-08-13
ms.topic: reference
---

# Frontend dashboard Phase 2 validation

## Executive summary

**Validation status**: Passed

The implementation covers the Phase 2 data integration requirements: the dashboard shell is in place, the Vite app is configured for local backend access, health endpoints are polled on a 15-second cadence, and recent detections are fetched from the local store and rendered as a list with timestamp, camera ID, confidence, and label information.

The implementation also intentionally avoids direct browser RTSP playback and instead shows a saved detection clip or a browser-safe fallback message, which matches the research requirement and the repo’s real backend constraints.

## Validation document

- Plan: [.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md](.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md)
- Changes: [.copilot-tracking/changes/2026-08-13/frontend-dashboard-changes.md](.copilot-tracking/changes/2026-08-13/frontend-dashboard-changes.md)
- Research: [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md)

## Phase 2 plan requirements

### Requirement 1: Poll backend health endpoints

**Plan requirement**: Poll the backend health endpoints and show the main service states.

**Evidence**:

- Dashboard service list is configured for Foundry Local, Inference API, Event Rules, and Local Store in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L22-L46).
- The polling and health fetch logic runs in a 15-second refresh cycle in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L66-L138).
- The app renders service status cards and readable details in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L164-L175).

**Assessment**: Match confirmed.

### Requirement 2: Fetch detection records from the local store

**Plan requirement**: Fetch detection records from the local store and present the most recent events.

**Evidence**:

- The dashboard fetches the detection payload from `/api/store/detections` in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L86-L99).
- The local-store service exposes `/healthz` and `/detections` in [apps/vision-pipeline/local_store/service.py](apps/vision-pipeline/local_store/service.py#L62-L104).
- Detection records are written with fields including timestamp, camera_id, label, confidence, model_id, source_id, and clip_path in [apps/vision-pipeline/local_store/service.py](apps/vision-pipeline/local_store/service.py#L17-L41).

**Assessment**: Match confirmed.

### Requirement 3: Render a list with timestamp, camera ID, confidence, and labels

**Plan requirement**: Render a table or card list with timestamps, camera IDs, confidence, and labels.

**Evidence**:

- The detection list view is rendered in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L211-L230).
- Each card displays label, confidence percentage, camera ID, and formatted timestamp in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L217-L227).
- Timestamp formatting is handled by the helper in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L48-L58).

**Assessment**: Match confirmed.

### Requirement 4: Maintain a browser-safe preview model

**Plan requirement**: Present a latest event preview without assuming browser-native RTSP playback.

**Evidence**:

- The preview panel exposes a saved clip when available and otherwise shows an explicit browser-unsupported message in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L177-L208).
- The research explicitly documents the RTSP constraint and the preferred clip or still-based preview approach in [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md#L16-L44).
- The decision is consistent with the “MVP recommendation” in [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md#L73-L92).

**Assessment**: Match confirmed.

## Evidence of implementation completeness

### Dashboard shell and Vite app

- The Vite React + TypeScript app exists under [apps/dashboard](apps/dashboard) with scripts and dependencies in [apps/dashboard/package.json](apps/dashboard/package.json#L1-L25).
- Vite is configured for host 0.0.0.0 on port 5173 and proxied backend routes in [apps/dashboard/vite.config.ts](apps/dashboard/vite.config.ts#L4-L32).
- The dashboard shell and layout cards are implemented in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L145-L232) and [apps/dashboard/src/App.css](apps/dashboard/src/App.css#L1-L240).

### Polling flow and fallback behavior

- The component initializes a refresh cycle and uses fallback data when services are unavailable in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L66-L138).
- Errors surface as a visible alert banner in [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L158-L162).
- The fetch path matches the repo’s backend contract for health and detection endpoints defined in the research and local store service.

## Coverage assessment

**Overall coverage**: Complete for the validated Phase 2 scope.

The implementation satisfies the core requirements for health polling, detection fetching, and recent detections rendering. The preview is intentionally browser-safe and does not violate the repo’s current live-stream constraints.

## Findings

### Severity: Minor

1. The preview is not true RTSP live video; it uses a saved detection or fallback message.
   - This is a deliberate design choice, not a defect, and it aligns with the research and the browser compatibility constraints.
   - Evidence: [apps/dashboard/src/App.tsx](apps/dashboard/src/App.tsx#L184-L192) and [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md#L16-L44).

No Critical or Major deviations were identified.

## Recommended next validations

- Validate actual runtime behavior with the local Docker Compose stack running and the dashboard served on port 5173.
- Confirm the health endpoints respond successfully when services are started in the local environment.
- Verify the latest detection preview resolves properly from persisted data under the data/detections directories.
- Validate an end-to-end detection event from the pipeline to stored clip and list rendering.

## Clarifying questions

- None at this time. The available plan, changes, and research are sufficient to validate the Phase 2 scope.

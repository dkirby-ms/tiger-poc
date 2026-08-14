<!-- markdownlint-disable-file -->
# Frontend dashboard plan

## User Requests
1. Research the minimum requirements for a simple dashboard frontend for the current Tiger PoC.
2. Determine whether a Vite app is a practical fit for this repo.
3. Define the architecture, integration points, and MVP scope before implementation starts.
4. Identify the live camera preview constraint and recommend the safest path.

## Overview
The project already has a working backend service topology, but no browser-facing dashboard. The next step is to plan a lightweight UI that observes the running services, lists recent detections, and presents a preview of the latest event without changing the current pipeline contract.

## Context Summary
* The repo is organized around Docker Compose and Python services under `apps/vision-pipeline`.
* Current backend services expose health and persistence endpoints suitable for frontend polling.
* The existing design is local-first and does not yet include a browser stream or dashboard UI.
* The RTSP simulator exists, but RTSP is not browser-native. This is the main technical constraint for a live-view feature.

## Implementation Checklist
- [x] Confirm service contracts and dashboard data sources
- [x] Decide whether to use a Vite React app or a simpler static frontend
- [x] Define the MVP dashboard layout and required data widgets
- [x] Choose the camera-preview strategy: stills, clips, or MJPEG/WebRTC proxy
- [x] Prepare a phased implementation plan for frontend build and backend integration

<!-- parallelizable: false -->

## Dependencies
* Existing Python service APIs in `apps/vision-pipeline`
* Local detection and clip outputs under `data/detections`
* Docker Compose runtime for service health and camera sources
* Vite ecosystem and browser compatibility constraints for RTSP

## Proposed architecture
### Frontend app
* Vite + React + TypeScript app
* local dev server on port 5173
* proxy or direct fetch calls to `localhost` backend ports

### Data sources
* `http://localhost:8081/healthz` for inference API status
* `http://localhost:8082/healthz` for rules status
* `http://localhost:8083/healthz` and `http://localhost:8083/detections` for storage status and event list
* `http://localhost:8000/healthz` for Foundry Local status

### Preview strategy
For the MVP, prefer one of these:

1. Latest saved frame or detection clip
2. MJPEG proxy from a small ffmpeg-based stream adapter
3. A later WebRTC upgrade once the prod-like live view is needed

## Phased implementation approach
### Phase 1: Dashboard shell
* Create the Vite app
* Add layout cards for health, detection summary, and recent activity
* Add a simple loading/error state pattern

### Phase 2: Data integration
* Poll the backend health endpoints
* Fetch detection records from the local store
* Render a table or card list with timestamps, camera IDs, confidence, and labels

### Phase 3: Preview and UX
* Add a “latest detection” pane with clip or image preview
* Add refresh cadence and last-updated indicators
* Keep the visual design minimal and fast

### Phase 4: Live stream decision
* Decide whether the app needs a true live camera preview or whether a periodic snapshot is sufficient
* If live preview is required, add a dedicated stream proxy service instead of forcing RTSP into the browser

## Success criteria
* A dashboard can render health status for the main services.
* A user can review recent detections without manual file inspection.
* The preview design matches the repo’s real capabilities and does not assume unsupported browser RTSP playback.
* The app remains simple enough to run locally with the existing Compose stack.

## Risks and constraints
* Browser RTSP playback is not viable without a proxy or conversion layer.
* The repo’s local-store service is the cleanest source for recent events and historical review.
* The dashboard should not be coupled to a future cloud architecture; it should work with the local PoC first.

## Summary
The safest next step is a Vite dashboard focused on observability and detection review, not a direct RTSP viewer. The dashboard should consume the project’s existing health and detections endpoints and treat a real camera preview as a separate stream-proxy problem to be solved after the MVP is working.

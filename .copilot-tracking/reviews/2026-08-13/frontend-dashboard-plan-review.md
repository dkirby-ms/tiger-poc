<!-- markdownlint-disable-file -->
# Frontend dashboard plan review

## Review metadata
* Date: 2026-08-13
* Related plan: [.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md](../../plans/2026-08-13/frontend-dashboard-plan.instructions.md)
* Changes log: [.copilot-tracking/changes/2026-08-13/frontend-dashboard-changes.md](../../changes/2026-08-13/frontend-dashboard-changes.md)
* Research document: [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](../../research/2026-08-13/frontend-dashboard-research.md)

## Summary of validation findings
* Critical: 0
* Major: 2
* Minor: 1

## RPI validation synthesis

### Phase 1: Service contracts and Vite fit
Status: Pass

Evidence:
* The repo already exposes the expected health and detection endpoints in [docker-compose.yml](../../../docker-compose.yml), [apps/vision-pipeline/local_store/service.py](../../../apps/vision-pipeline/local_store/service.py), [apps/vision-pipeline/event_rules/service.py](../../../apps/vision-pipeline/event_rules/service.py), and [apps/vision-pipeline/inference_api/service.py](../../../apps/vision-pipeline/inference_api/service.py).
* The Vite app is a practical fit for the repo and the project builds successfully.

### Phase 2: Dashboard shell and data integration
Status: Pass

Evidence:
* Vite proxy configuration is set in [apps/dashboard/vite.config.ts](../../../apps/dashboard/vite.config.ts).
* Polling logic for health and local-store detections is implemented in [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx).
* Detection list rendering matches the intended UX with timestamps, confidence, and camera labels.

### Phase 3: Preview and UX
Status: Pass with caveat

Evidence:
* The dashboard includes a preview panel and refresh indicator in [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx).
* The implementation correctly avoids assuming browser-native RTSP playback, matching the plan and research guidance.

### Phase 4: Live stream decision
Status: Pass

Evidence:
* The app explicitly informs the user that RTSP live preview is not supported in-browser and prefers a saved clip workflow instead.
* This aligns with the research summary in [.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md](../../research/2026-08-13/frontend-dashboard-research.md).

## Implementation quality findings

### [Major] IV-001: Preview path is not browser-safe because it points to an absolute local file path
Evidence:
* [apps/vision-pipeline/local_store/service.py](../../../apps/vision-pipeline/local_store/service.py#L24-L47) stores `clip_path` as an absolute path under `/data/detections/clips/...`.
* [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L150-L190) renders `<video src={latestDetection.clip_path}>` directly.
* The Vite app does not expose the `/data` directory or a clip-serving API route in [apps/dashboard/vite.config.ts](../../../apps/dashboard/vite.config.ts).

Impact:
* The browser cannot load the stored clip because the UI does not serve the file through a browser-accessible route.

Recommended fix:
* Expose a backend route or dashboard-served asset for stored detections and clip previews, rather than referencing absolute filesystem paths.

### [Major] IV-002: Broken fallback preview and misleading service status masking
Evidence:
* [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L17-L27) defines a fallback clip path to `/latest-detection.mp4`.
* The public dashboard folder in [apps/dashboard/public](../../../apps/dashboard/public) does not include that asset.
* The fetch error handler in [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L41-L95) swaps the app into synthetic fallback data, which hides the real service status.

Impact:
* The preview falls back to a missing asset, and the app can mask backend outages behind placeholder data.

Recommended fix:
* Replace the broken preview fallback with a clear “no preview available” state and preserve the actual offline/error state for services.

### [Minor] IV-003: Missing test coverage for the preview contract
Evidence:
* The dashboard app does not include a focused test suite for health payload parsing, proxy configuration, or saved-clip preview behavior.

Impact:
* A regression in the preview path or API contract could ship unnoticed.

Recommended fix:
* Add a small test suite covering health endpoint handling, detection payload parsing, and preview URL generation.

## Validation command outputs
```text
cd /home/saitcho/tiger-poc/apps/dashboard && npm run build
> dashboard@0.0.0 build
> tsc -b && vite build

vite v8.2.1 building client environment for production...
✓ 17 modules transformed.
✓ built in 162ms
```

```text
curl -I http://localhost:5173/
HTTP/1.1 200 OK
```

## Missing work and deviations
* The stored-clip preview is not yet served over a valid browser route.
* The dashboard uses placeholder fallback data when service calls fail, which reduces operational clarity.
* The UI does not yet add automated regression tests for the preview contract.

## Follow-up work recommendations

### Deferred from scope
* Decide whether a dedicated MJPEG or WebRTC proxy is required for a future live camera preview.

### Discovered during review
* Add a browser-safe clip-serving route or static asset pipeline for persisted detection videos.
* Replace the missing fallback preview asset with a real “no preview available” state.
* Add a small dashboard test suite for health and detection contract parsing.

## Overall status
Needs Rework

Reviewer notes:
* The dashboard correctly matches the repo’s local-first architecture and no-RTSP-in-browser decision.
* The remaining gap is preview integrity: the current implementation references filesystem paths that the browser cannot access and uses a broken fallback asset.
* This is a bounded fix and should be resolved before the dashboard is considered complete.

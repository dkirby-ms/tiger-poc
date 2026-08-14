# Frontend dashboard plan — Phase 4 validation

## Scope
- Plan: [frontend-dashboard-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md)
- Changes log: [frontend-dashboard-changes.md](../../../.copilot-tracking/changes/2026-08-13/frontend-dashboard-changes.md)
- Research: [frontend-dashboard-research.md](../../../.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md)
- Validation target: Phase 4 — live stream decision

## Validation status
Passed

## Phase 4 requirements extracted from the plan
The Phase 4 requirement in the plan is explicit:
- Decide whether the app needs a true live camera preview or whether a periodic snapshot is sufficient.
- If live preview is required, add a dedicated stream proxy service instead of forcing RTSP into the browser.

This is reinforced by the research summary, which states that browser-native RTSP playback is not viable and that the safe MVP path is a saved clip or still-frame preview with a future MJPEG/WebRTC proxy as a separate concern.

## Evidence review

### Requirement: use a browser-safe preview strategy rather than in-browser RTSP
Evidence:
- [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L176-L191) renders a preview panel labeled “Browser-safe” and explicitly states: “RTSP live preview is not supported in-browser.”
- [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L177-L190) uses the latest saved detection clip or a placeholder instead of a direct RTSP stream.
- [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L240-L244) documents the architectural decision: “It does not assume browser-native RTSP playback” and recommends a dedicated MJPEG or WebRTC proxy later.

Status: Matched.

### Requirement: prefer saved detection clips or periodic snapshots for the MVP
Evidence:
- [frontend-dashboard-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md#L39-L61) recommends saved frame/clip preview as the preferred MVP option.
- [frontend-dashboard-research.md](../../../.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md#L38-L80) describes the MVP path as “status + recent detection cards + snapshot/clip viewer” and calls out RTSP in-browser as unsupported.
- [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L174-L191) displays the latest event using the persisted clip path when available.

Status: Matched.

### Requirement: keep the dashboard aligned with existing local backend contracts
Evidence:
- [apps/dashboard/vite.config.ts](../../../apps/dashboard/vite.config.ts#L1-L26) configures Vite proxies to existing service ports for Foundry Local, inference, rules, and local-store endpoints.
- [apps/dashboard/src/App.tsx](../../../apps/dashboard/src/App.tsx#L18-L33) polls those service health endpoints and the /detections endpoint.
- [frontend-dashboard-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md#L33-L61) specifically calls for the dashboard to consume existing endpoints and avoid changing the backend contract.

Status: Matched.

## Findings by severity
### Critical
- None.

### Major
- None.

### Minor
- None.

## Coverage assessment
Phase 4 is implemented to the required level for the current repo maturity. The implementation does not attempt to force RTSP through the browser and instead follows the recommended MVP pattern: observe service health, review recent detections, and surface the latest saved clip as the browser-safe preview. The decision is explicitly documented in the UI and matches the research and plan guidance.

## Implementation verification
The dashboard build was verified successfully:
- Command run: `cd /home/saitcho/tiger-poc/apps/dashboard && npm run build`
- Result: exit code 0
- Evidence: Vite completed a production build successfully and emitted dist assets.

## Conclusion
The live stream decision is confirmed as a no-RTSP-in-browser recommendation for this Phase 4 implementation. The dashboard is intentionally designed around the repo’s real capabilities: health polling plus saved detection data and preview, with a dedicated proxy reserved for any future true live-view requirement.

## Recommended next validations not completed in this session
- Verify the dashboard end-to-end against the running Compose stack once the services are started.
- Validate the latest saved clip path and fallback behavior against real detection files under `data/detections`.
- Decide whether a separate stream-proxy service is needed for a production-grade live preview beyond the local PoC MVP.

## Clarifying questions
- None required. The plan, research, and implementation are consistent on the browser-safe live preview decision.

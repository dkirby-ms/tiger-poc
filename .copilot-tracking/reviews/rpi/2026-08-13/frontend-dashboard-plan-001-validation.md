# Frontend dashboard Phase 1 validation

- Plan: `.copilot-tracking/plans/2026-08-13/frontend-dashboard-plan.instructions.md`
- Changes log: `.copilot-tracking/changes/2026-08-13/frontend-dashboard-changes.md`
- Research: `.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md`
- Validation status: Passed
- Validation date: 2026-08-13

## Scope
This review validates the Phase 1 dashboard shell against the plan, research, and implementation claim for the frontend dashboard effort. The review specifically checks:

1. service contracts and dashboard data sources
2. Vite app fit for the current repo
3. MVP layout and health/detection widgets
4. browser-safe preview strategy for the current RTSP constraint

## Extracted Phase 1 requirements
From the implementation plan, Phase 1 requires the following:

- confirm service contracts and dashboard data sources
- decide whether to use Vite React or a simpler static frontend
- define the MVP dashboard layout and required data widgets
- choose a browser-safe camera preview strategy
- prepare a phased implementation plan for frontend build and backend integration

The plan explicitly confirms the recommended architecture: Vite + React + TypeScript, local dev server on port 5173, and proxy or direct fetch access to existing backend health and detection endpoints.

## Comparison against the implementation
### 1. Service contracts and data sources
The repo already exposes the backend endpoints required by the dashboard:

- Foundry Local: `http://localhost:8000/healthz`
- Inference API: `http://localhost:8081/healthz`
- Event rules: `http://localhost:8082/healthz`
- Local store: `http://localhost:8083/healthz` and `http://localhost:8083/detections`

Evidence:

- `docker-compose.yml:18-95` defines the running service topology and ports for the Foundry Local, inference API, event rules, and local-store services.
- `apps/vision-pipeline/local_store/service.py:89-133` exposes `/healthz` and `/detections` and returns a JSON payload with `count` and `detections`.
- `apps/vision-pipeline/event_rules/service.py:98-118` exposes `/healthz` with health and rule configuration metadata.
- `apps/vision-pipeline/inference_api/service.py:133-160` exposes `/healthz` for service health.

The dashboard app consumes these endpoints through Vite proxy routes:

- `apps/dashboard/vite.config.ts:4-28` proxies `/api/foundry`, `/api/inference`, `/api/rules`, and `/api/store` to the local service ports.
- `apps/dashboard/src/App.tsx:16-31` defines the dashboard service endpoints and polling contract.
- `apps/dashboard/src/App.tsx:35-91` fetches health and detections data and populates `services` and `detections` state.

This matches the research and plan: the dashboard is aligned to the repo’s current contract and does not require backend contract changes.

### 2. Vite fit and implementation strategy
The plan recommends a Vite React app, and the codebase implements exactly that:

- `apps/dashboard/package.json:1-22` declares a Vite React + TypeScript app.
- `apps/dashboard/vite.config.ts:1-28` sets `host: '0.0.0.0'`, port `5173`, and service-specific proxy rules.
- `apps/dashboard/src/App.tsx:1-241` renders a dashboard shell with health cards, detection list, preview panel, and fallback states.

Build verification:

- `cd /home/saitcho/tiger-poc/apps/dashboard && npm run build`
- Result: success, with Vite production build completing without TypeScript or bundling errors.

This confirms the Vite + React + TypeScript approach is a practical fit for the repo and works in the current local-first architecture.

### 3. MVP dashboard layout and widgets
The dashboard covers the Phase 1 MVP layout from the plan:

- health cards for system status
- preview area for the latest event
- recent detections list
- simple loading/error/fallback state pattern

Evidence:

- `apps/dashboard/src/App.tsx:93-155` renders the service status cards.
- `apps/dashboard/src/App.tsx:157-201` renders the latest event preview and recent detections panels.
- `apps/dashboard/src/App.tsx:203-241` adds a system notes section and refresh interval messaging.

This satisfies the plan requirement to create the dashboard shell and required MVP data widgets.

### 4. Camera preview strategy and RTSP limitation
The research and plan explicitly call out that browser-native RTSP is not supported and that the MVP should not assume direct browser playback. The implementation follows that recommendation.

Evidence:

- `.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md:20-82` states that there is no browser-native RTSP viewer path and recommends stills, saved clips, or a later proxy-based stream.
- `apps/dashboard/src/App.tsx:160-177` renders a preview pane that falls back to a browser-safe placeholder when no saved clip is available and notes that RTSP live preview is not supported in-browser.
- `apps/dashboard/src/App.tsx:38-48` uses a fallback detection object with a local clip path and there is no attempted direct RTSP URL mounting.
- `docker-compose.yml:1-35` confirms the RTSP simulator is running in the pipeline, but the browser-facing dashboard avoids direct RTSP consumption.

This is a correct Phase 1 decision and is consistent with the research recommendation.

## Severity-ranked findings
### Critical
- None.

The implementation does not violate the essential contract required for Phase 1. It remains compatible with the repo’s local service topology and the plan’s guidance.

### Major
- None.

There are no material gaps in the Phase 1 implementation against the plan, research, or service contract. The dashboard design stays within the repo’s actual capabilities and avoids an unsupported browser RTSP assumption.

### Minor
1. Local fallback state is intentionally used when backend services are unavailable.
   - Evidence: `apps/dashboard/src/App.tsx:35-91` sets fallback status cards and detection data if a fetch fails.
   - Impact: This is good for resilience, but it means the dashboard still shows mocked or fallback content during outages; that is acceptable for a local PoC, but it should be recognized as non-production behavior.

2. The preview is clip-based rather than real live camera streaming.
   - Evidence: `apps/dashboard/src/App.tsx:160-177` and `.copilot-tracking/research/2026-08-13/frontend-dashboard-research.md:32-82`.
   - Impact: The implementation matches the recommended MVP scope, but it does not provide a real live camera feed yet. This is a conscious design choice, not a defect.

## Coverage assessment
Phase 1 coverage is complete for the scope defined by the plan and research:

- service contracts confirmed
- Vite app selected and proven viable
- health widgets implemented
- recent detections panel implemented
- browser-safe preview strategy implemented
- phased plan completed and documented

The implementation is fully consistent with the repo’s current local-first design and does not create a hidden contract mismatch.

## Clarifying questions
No blocking clarifying questions remain for Phase 1. The remaining product decision is optional and belongs to a later phase: whether a dedicated MJPEG/WebRTC proxy is required for a true live preview beyond the browser-safe stored clip workflow.

## Final assessment
The dashboard Phase 1 implementation is valid against the plan and research. It matches the repo’s actual service contract, uses a practical Vite-based frontend, and respects the RTSP/browser limitation by using safe saved-clip and polling-based behavior rather than unsupported direct browser streaming.

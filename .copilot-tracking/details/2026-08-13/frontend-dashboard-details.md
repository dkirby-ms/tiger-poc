<!-- markdownlint-disable-file -->
# Frontend dashboard details

## Goal
Create a small Vite React dashboard for the Tiger PoC that surfaces health status, recent detections, and a browser-safe preview strategy without changing the current service contract.

## Phase breakdown
### Phase 1: Plan analysis
* Confirm the current backend contract and required API dependencies.
* Confirm Vite is a good fit and identify any browser constraints.
* Capture the required UI and data flows in the implementation plan.

### Phase 2: Dashboard implementation
* Scaffold the Vite app in `apps/dashboard`.
* Add polling health checks for Foundry, inference API, event rules, and local store.
* Load recent detections from the local store JSON endpoint.
* Render a responsive dashboard with card layouts and basic error/loading states.
* Show the latest detection detail and stored clip preview when available.

### Phase 3: Validation and handoff
* Run a production build.
* Confirm the app works with a mocked or live local stack.
* Record the changes and any follow-up items needed.

## Source of truth
* `docker-compose.yml` for service ports and topology
* `apps/vision-pipeline/local_store/service.py` for `/healthz` and `/detections`
* `apps/vision-pipeline/inference_api/service.py` for `/healthz`
* `apps/vision-pipeline/event_rules/service.py` for service health and filtering logic
* `data/detections` for persisted detection output examples

## MVP requirements
* Poll the core service health endpoints
* List recent detections from `local-store`
* Highlight the most recent event details
* Avoid raw RTSP playback in the browser
* Keep the app lightweight and local-first

## Browser-safe preview strategy
The dashboard should not send raw RTSP into a browser. For the MVP, it should either:

* display a saved detection clip from the local `data` folder when available, or
* show a “no browser-safe live preview” note if a clip is unavailable.

This keeps the frontend aligned with the actual repo capabilities while preserving a migration path to a dedicated proxy later.

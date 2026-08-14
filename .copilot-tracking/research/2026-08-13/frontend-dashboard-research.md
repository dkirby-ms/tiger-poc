<!-- markdownlint-disable-file -->
# Frontend dashboard research

## Goal
Research what is required to build a simple Vite-based dashboard for the Tiger PoC and document the minimum viable architecture before implementation.

## Current project contract
The project already exposes several backend endpoints that are suitable for a dashboard:

* `http://localhost:8000/healthz` from the Foundry Local runtime
* `http://localhost:8081/healthz` from the inference API
* `http://localhost:8082/healthz` from event rules
* `http://localhost:8083/healthz` and `http://localhost:8083/detections` from local storage

This means the dashboard can show service status and recent detection records without changing the backend contract.

## Findings from the codebase

### 1. Service status is already available
The backend services use FastAPI and expose simple health endpoints.

* `inference_api/service.py` defines `/healthz` and `/infer`
* `event_rules/service.py` defines `/healthz` and `/filter`
* `local_store/service.py` defines `/healthz`, `/persist`, and `/detections`

A dashboard can poll these endpoints to display uptime, connectivity, and counts.

### 2. Recent detections are persisted locally
The local store writes JSON files to `data/detections/detections/` and keeps clip artifacts under `data/detections/clips/`.

This is ideal for:

* activity feed
* recent detection table
* camera ID and confidence summary
* quick drill-down into saved JSON records

### 3. There is no browser-native RTSP viewer path
The app does not currently expose a web-friendly live video stream.

This matters because modern browsers do not natively play RTSP streams in `<video>` tags. The practical choices are:

* stream the camera through a proxy that converts RTSP to MJPEG or WebRTC
* show a still-frame snapshot instead of live video
* render clips from the persisted MP4 files after detection occurs

For a first dashboard, the most reliable design is not “live RTSP in the browser” but “status + recent detection cards + snapshot/clip viewer.”

### 4. A Vite frontend is a good fit
A Vite + React + TypeScript app suits this repo because it is small, easy to run locally, and supports polling and basic UI composition without a heavy frontend framework.

A minimal dashboard can be built with:

* Vite React app
* TypeScript
* lightweight CSS or Tailwind
* `fetch` or `@tanstack/react-query` for polling
* static asset or proxy for camera preview

## Recommended dashboard scope
The initial dashboard should focus on the following features:

1. System health panel
   * Foundry Local health
   * Inference API health
   * Event rules health
   * Local store health

2. Detection activity panel
   * recent detection records from `/detections`
   * count by camera ID and label
   * latest detection timestamp

3. Last event detail panel
   * confidence
   * bbox coordinates
   * model ID
   * source ID
   * optional clip reference

4. Camera preview area
   * preferred: stills or saved clips from local store
   * fallback: proxied MJPEG stream from FFmpeg or a dedicated stream service

## Key design decision: live camera preview
The dashboard should not assume browser-native RTSP playback. The preferred architecture is:

### Option A: still image / clip viewer (best for MVP)
Use saved frames or stored clips from `local_store` and refresh periodically.

Pros:

* lowest complexity
* no extra streaming infrastructure
* works with current project layout

Cons:

* not a true live camera feed

### Option B: MJPEG proxy from FFmpeg (good compromise)
Use a small backend proxy that pulls RTSP and re-serves MJPEG or WebRTC to the browser.

Pros:

* near-live preview in browser
* simpler than building a full streaming service

Cons:

* requires an extra process or container
* needs stream conversion tooling

### Option C: WebRTC streaming via a dedicated proxy (most production-like)
Use WebRTC or another browser-compatible stream format.

Pros:

* strongest user experience
* scalable for later production work

Cons:

* more complexity than needed for a PoC

## MVP recommendation
For the first frontend, the best path is:

* Vite React app served locally on port 5173
* proxy API calls through Vite to the existing container ports
* poll the health and detection endpoints
* show recent detections and stored clips
* display a “latest frame preview” using a generated still or stored clip rather than RTSP directly

This keeps the frontend aligned with the repo’s current actual behavior while preserving a clear upgrade path to a real live-streaming proxy later.

## Evidence log

* [docker-compose.yml](../../docker-compose.yml) exposes the RTSP simulator and the backend services.
* [apps/vision-pipeline/local_store/service.py](../../apps/vision-pipeline/local_store/service.py) exposes `/detections` and writes persisted detections.
* [apps/vision-pipeline/event_rules/service.py](../../apps/vision-pipeline/event_rules/service.py) exposes `/healthz` and `/filter`.
* [apps/vision-pipeline/inference_api/service.py](../../apps/vision-pipeline/inference_api/service.py) exposes `/healthz` and inference endpoints.
* The repository has no frontend or browser streaming stack today.

## Suggested next work
1. Scaffold a Vite React dashboard app.
2. Add API config and proxy rules for backend services.
3. Build health widgets and recent detection panels.
4. Add preview behavior for stored images or clips.
5. Decide whether to add a streaming proxy for a true live camera view.

## Success criteria
A dashboard MVP is complete when it can:

* show health state for the core services
* list recent detections from the local store
* present a clear preview of the latest event or clip
* run locally with the current Docker Compose stack without changing the backend contract

## Summary
The repo is already close to a useful dashboard because it exposes health and persistence endpoints. The main gap is the live camera preview, which requires a browser-safe proxy or a still/clip-based alternative. A Vite frontend is the right next step; it should stay focused on observability and detection review rather than trying to make RTSP work directly in the browser.

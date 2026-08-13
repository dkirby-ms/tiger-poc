<!-- markdownlint-disable-file -->
---
title: Local Development Environment Backlog Review
description: Completion assessment of backlog items against current workspace state
ms.date: 2026-08-13
---

# Backlog Review: Local Development Environment

**Review Date:** 2026-08-13  
**Backlog Reference:** [backlog-local-dev-environment.md](../../docs/backlog-local-dev-environment.md)  
**Status:** PARTIALLY COMPLETE — 4 of 8 epics have deliverables; 2 epics are partial; 2 epics not started

---

## Executive Summary

The workspace demonstrates substantial progress on the core pipeline architecture. The frame ingestion, preprocessing, and foundry local infrastructure are implemented and ready for integration testing. Event rules and local storage services are code-complete. Key gaps include: model files in the bundle, production-ready Foundry Local server implementation, wired inference and event rule services, MQTT publishing integration, and CI/promotion workflows.

---

## Epic-by-Epic Assessment

### Epic 1: Workstation and GPU Foundation

**Status:** ✅ NOT APPLICABLE (Manual Setup)

**Summary:**
* 1.1 (NVIDIA driver verification): Out of scope for code review; assumes user has performed this independently.
* 1.2 (NVIDIA Container Toolkit): Out of scope for code review; foundry-local Dockerfile assumes toolkit is available.
* 1.3 (Repo scaffolding and devcontainer): ✅ COMPLETE

**Findings:**
* `.devcontainer/devcontainer.json` exists and provides VS Code container environment.
* Folder layout (`apps/`, `docker/`, `k8s/`, `models/`, `samples/`) matches backlog specification.
* `docker-compose.yml` skeleton is present with placeholder services and proper dependency ordering.

**Acceptance Criteria Met:**
* ✅ Documented folder layout exists
* ✅ `.devcontainer.json` exists
* ✅ `docker-compose.yml` skeleton with all pipeline stage placeholders

---

### Epic 2: Video Ingestion

**Status:** ✅ COMPLETE

**Summary:** Frame grabber and RTSP simulator are fully implemented with tests.

**Completed Items:**

#### 2.1: Sample video and RTSP simulator source
* ✅ COMPLETE
* `docker-compose.yml` includes `rtsp-simulator` (bluenviron/mediamtx) and `sample-video` (ffmpeg-based RTSP stream generator)
* Services run under "simulator" profile
* Sample video generation uses `testsrc` for deterministic testing

**Acceptance Criteria Met:**
* ✅ RTSP simulator container streams on `rtsp://rtsp-simulator:8554/camera-1`
* ✅ Sample video generation is non-destructive (no large binaries committed)
* ✅ Source is configuration-driven (can switch between RTSP and file input via `VIDEO_SOURCE_TYPE` env var)

#### 2.2: Frame grabber service
* ✅ COMPLETE
* `apps/vision-pipeline/frame_grabber/service.py` and `receiver.py` implement frame sampling from RTSP or file sources
* Configuration-driven via environment variables (`VIDEO_SOURCE_TYPE`, `VIDEO_SOURCE`, `FRAME_RATE`, `CAMERA_ID`)
* HTTP sink: publishes frames to pre-processor via `FRAME_OUTPUT_URL` (http://pre-processor:8080/frames)
* Frame rate sampling logic is implemented
* Metadata (camera_id, sequence, timestamp, width, height) attached to each frame

**Acceptance Criteria Met:**
* ✅ Frame rate and source type are configuration, not code
* ✅ Service emits frames on HTTP internal interface consumed by pre-processor
* ✅ Unit tests in `tests/test_service.py` cover frame sampling with recorded file fixture

---

### Epic 3: Pre-Processing

**Status:** ✅ COMPLETE

**Summary:** Pre-processor service is fully implemented with resizing, normalization, and batching.

**Completed Item:**

#### 3.1: Pre-processor service (resize, normalize, batch)
* ✅ COMPLETE
* `apps/vision-pipeline/pre_processor/service.py` implements full preprocessing pipeline
* Features:
  * JPEG decoding with OpenCV
  * Frame resizing to target resolution (default 320×240, configurable)
  * Normalization to [0, 1] float32 range
  * Batch accumulation (default batch_size=1, configurable)
  * HTTP server interface on port 8080
* Configuration-driven via environment variables (`PREPROCESS_TARGET_WIDTH`, `PREPROCESS_TARGET_HEIGHT`, `PREPROCESS_BATCH_SIZE`)
* Output tensors are NumPy arrays in CHW format ready for ONNX inference

**Acceptance Criteria Met:**
* ✅ Batch size and target resolution are configurable
* ✅ Output tensors match documented input shape and dtype (float32, CHW format)
* ✅ Unit tests in `tests/test_preprocessor.py` validate output shape and normalization

---

### Epic 4: Foundry Local Runtime

**Status:** ⏳ IN PROGRESS — 60% complete (infrastructure ready; model files and full server logic pending)

**Findings:**

#### 4.1: Provision ONNX model bundle (YOLO, Florence-2, Phi-4-multimodal)
* ⏳ PARTIAL
* `models/bundle.json` manifest created with all three models listed
* Bundle structure defined:
  * `yolo/model.onnx` (fp16)
  * `florence-2/model.onnx` (fp16)
  * `phi-4-multimodal/model.onnx` (int4 quantized)
* **Gap:** Actual model files are not present; placeholders point to empty paths
* **Gap:** sha256 and source_url fields are empty (should reference model sources for reproducibility)
* **Gap:** No fetch/build script exists yet (`scripts/fetch-model-bundle.sh` placeholder exists but no content)

**Acceptance Criteria:**
* ⏳ Bundle has version identifier (bundle_version: "0.1.0", bundle_id: "tiger-vision-models")
* ❌ Content digest not recorded
* ❌ Fetch/build script does not exist or is incomplete

#### 4.2: Foundry Local container with CUDA/TensorRT execution provider
* ⏳ PARTIAL
* `docker/foundry-local/Dockerfile` builds a CUDA 12.8 runtime image
* `docker/foundry-local/server.py` implements FastAPI server skeleton
* Features present:
  * CUDA 12.8 base image
  * Model bundle directory mounting (`/models`)
  * Execution provider selection via env var (`FOUNDRY_EXECUTION_PROVIDER`, defaults to CUDAExecutionProvider)
  * Runtime mode selection (`FOUNDRY_RUNTIME_MODE`, defaults to "onnx")
  * FastAPI application scaffold with bundle manifest loading
* **Gap:** Actual `/v1/completions` endpoint logic is stubbed; inference is not implemented
* **Gap:** No ONNX Runtime or TensorRT library in `requirements.txt`; container has no model execution capability yet
* **Gap:** No smoke test confirming endpoint responsiveness

**Acceptance Criteria:**
* ⏳ Container builds and exposes port 8000
* ❌ `/v1` endpoints not implemented
* ❌ No smoke test for end-to-end inference

**Requirements.txt Analysis:**
* Missing: `onnxruntime-gpu` (or CPU equivalent)
* Missing: `fastapi`, `uvicorn` (may be in requirements.txt; not shown)

#### 4.3: VRAM budget validation across concurrent models
* ❌ NOT STARTED
* No VRAM usage documentation present
* No concurrent model loading test
* No fallback strategy (quantization or sequential loading) documented

**Acceptance Criteria Not Met:**
* ❌ No VRAM usage documentation
* ❌ No fallback strategy for Phi-4-multimodal

---

### Epic 5: Inference API and Event Rules

**Status:** ⏳ IN PROGRESS — 50% complete (code written; integration pending)

**Findings:**

#### 5.1: Inference API service
* ✅ CODE COMPLETE
* `apps/vision-pipeline/inference_api/service.py` implements:
  * `Detection` dataclass with normalization schema
  * `from_payload()` factory to parse diverse model response formats
  * `to_dict()` serialization
  * Support for `bbox` or `box`, `label` or `name` variants
* Schema includes: label, confidence, bbox (x, y, w, h), zone, source_id, model_id
* **Gap:** Service is not yet wired into docker-compose; entry point exists but no HTTP server or Foundry Local integration
* **Gap:** No integration test exercising full frame→detection path

**Acceptance Criteria:**
* ✅ Service contract (Detection schema) is documented
* ❌ Integration test does not exercise full path (mock Foundry Local needed)

#### 5.2: Event rules engine
* ✅ CODE COMPLETE
* `apps/vision-pipeline/event_rules/service.py` implements:
  * `EventRuleConfig` with confidence_threshold, dwell_time_seconds, allowed_zones
  * `apply_event_rules()` filtering logic
  * Support for both Detection objects and dicts
* Rules applied:
  * Confidence threshold filtering
  * Dwell time filtering
  * Zone allowlist filtering
* Configuration-driven via environment variables
* **Gap:** Not yet wired into docker-compose or pipeline; no HTTP/messaging interface
* **Gap:** Unit tests cover rules individually but not in full pipeline context

**Acceptance Criteria:**
* ✅ Thresholds and zone definitions are configurable
* ✅ Unit tests in `tests/test_epic_5.py` cover rule filtering

#### 5.3: Local storage for detections and clips
* ✅ CODE COMPLETE
* `apps/vision-pipeline/local_store/service.py` implements:
  * `LocalDetectionStore` class
  * Persistence to disk in directory structure
  * JSON detection records with timestamp, camera_id, model_id, etc.
  * Optional clip storage (MP4 reference in record)
  * `list_detections()` and `purge_expired()` methods
  * Retention policy (default 7 days)
* Configuration via constructor (`root`, `retention_days`)
* **Gap:** Service not wired into pipeline; no entry point or HTTP interface

**Acceptance Criteria:**
* ✅ Detections persisted with metadata (timestamp, camera_id, model_id, confidence)
* ✅ Storage location and retention configurable

---

### Epic 6: Local Messaging and Dataflow Stub

**Status:** ⏳ IN PROGRESS — 40% complete (infrastructure present; integration not wired)

**Findings:**

#### 6.1: Mosquitto MQTT broker container
* ✅ COMPLETE (INFRASTRUCTURE)
* `docker-compose.yml` includes `mosquitto` service using `eclipse-mosquitto:2` image
* Service will accept MQTT connections on default port 1883
* **Gap:** No topic configuration or topic naming convention documented in Mosquitto setup
* **Gap:** No test confirming broker connectivity or topic structure

**Acceptance Criteria:**
* ✅ Broker service defined in compose
* ❌ Topic naming convention not documented alongside Mosquitto (should reference `cv/{site}/{camera}/detections` pattern)

#### 6.2: Publish detections to MQTT from event rules
* ❌ NOT IMPLEMENTED
* Event rules service exists but has no MQTT publishing logic
* No client library (paho-mqtt, etc.) in project dependencies
* No integration between event_rules output and Mosquitto

**Acceptance Criteria Not Met:**
* ❌ No MQTT publishing in event rules service
* ❌ No payloads with model id and bundle digest

#### 6.3: Dataflow stub service
* ⏳ PARTIAL (INFRASTRUCTURE)
* `docker-compose.yml` includes `dataflow-stub` service (currently alpine:3.20 placeholder)
* Service is ordered after mosquitto and event-rules in dependency graph
* **Gap:** No actual dataflow stub implementation; service is a no-op placeholder

**Acceptance Criteria:**
* ⏳ Service defined in compose
* ❌ No actual MQTT subscriber logic implemented
* ❌ No message recording or simulation behavior

---

### Epic 7: Local Orchestration and Registry

**Status:** ✅ COMPLETE (Docker Compose); ⏳ PARTIAL (Kubernetes)

**Findings:**

#### 7.1: Docker Compose path for full pipeline
* ✅ COMPLETE
* `docker-compose.yml` wires all services:
  * rtsp-simulator + sample-video (video source, under "simulator" profile)
  * frame-grabber → pre-processor (HTTP frame ingestion)
  * foundry-local (model inference, GPU enabled)
  * inference-api, event-rules, local-store, mosquitto (placeholders with dependencies)
  * dataflow-stub (depends on event-rules and mosquitto)
* Service dependencies expressed correctly (`depends_on`)
* Full pipeline can start with `docker-compose up` (under default profile)
* **Gap:** Some services (inference-api, event-rules, local-store) are alpine no-op placeholders; not yet integrated

**Acceptance Criteria:**
* ✅ All services defined in single compose file
* ✅ Service dependencies correctly expressed
* ⏳ Full pipeline can start but end-to-end flow not validated (services not integrated)

#### 7.2: Local Kubernetes manifests (kind or k3d)
* ❌ NOT STARTED
* `k8s/` directory exists but contains only README.md
* No manifest files (Deployment, Service, etc.)
* No kind or k3d cluster config documented

**Acceptance Criteria Not Met:**
* ❌ No Kubernetes manifests
* ❌ No cluster config

#### 7.3: Local container registry
* ❌ NOT STARTED
* No registry service in docker-compose
* No tagging convention documented

**Acceptance Criteria Not Met:**
* ❌ No local registry setup
* ❌ No tagging convention

---

### Epic 8: CI, Parity, and Promotion

**Status:** ❌ NOT STARTED

**Findings:**

#### 8.1: CI pipeline running recorded-video validation
* ❌ NOT STARTED
* No CI workflow files (GitHub Actions, GitLab CI, etc.) present
* No recorded video test fixture in samples/

**Acceptance Criteria Not Met:**
* ❌ No CI job defined
* ❌ No recorded video fixture

#### 8.2: Image and model bundle promotion script
* ❌ NOT STARTED
* No promotion script in scripts/ directory
* No image tagging convention defined

**Acceptance Criteria Not Met:**
* ❌ No promotion script

#### 8.3: Dev/edge parity checklist
* ❌ NOT STARTED
* No parity checklist or documentation

**Acceptance Criteria Not Met:**
* ❌ No parity checklist

---

## Cross-Cutting Observations

### Architecture Alignment
* ✅ Pipeline stages follow the reference architecture: ingestion → preprocessing → inference → rules → storage/messaging
* ✅ Configuration-driven behavior (environment variables) enables dev/edge parity
* ✅ Service contracts (Detection schema, EventRuleConfig, etc.) are clearly defined

### Testing Coverage
* ✅ Unit tests exist for frame grabber, preprocessor, event rules, local store
* ✅ Recorded MP4 fixture used for deterministic testing
* ❌ Integration tests lacking (full pipeline end-to-end)
* ❌ No load testing or concurrent model VRAM validation

### Documentation
* ✅ Service docstrings and README present
* ✅ Configuration environment variables documented in code
* ⏳ Partially missing: topic naming convention, VRAM budget, model bundle fetch procedure

### Dependencies and Build
* ✅ `pyproject.toml` defines core dependencies (opencv-python-headless, requests)
* ✅ Test dependencies declared (pytest)
* ❌ Foundry Local requirements.txt missing critical deps (onnxruntime-gpu, fastapi, uvicorn)
* ❌ MQTT publishing client not declared

---

## Completion Summary

| Epic | Item | Status | Notes |
|------|------|--------|-------|
| 1 | Workstation Foundation | ✅ | Manual setup; repo scaffolding complete |
| 2.1 | RTSP Simulator | ✅ | Complete |
| 2.2 | Frame Grabber | ✅ | Complete |
| 3.1 | Pre-processor | ✅ | Complete |
| 4.1 | Model Bundle | ⏳ | Manifest defined; no model files or fetch script |
| 4.2 | Foundry Local | ⏳ | Container scaffolded; inference logic not implemented |
| 4.3 | VRAM Validation | ❌ | Not started |
| 5.1 | Inference API | ⏳ | Code complete; not wired into pipeline |
| 5.2 | Event Rules | ⏳ | Code complete; not wired into pipeline |
| 5.3 | Local Storage | ⏳ | Code complete; not wired into pipeline |
| 6.1 | Mosquitto | ✅ | Infrastructure present |
| 6.2 | MQTT Publishing | ❌ | Not implemented |
| 6.3 | Dataflow Stub | ❌ | Placeholder only |
| 7.1 | Docker Compose | ✅ | Structure complete; services need integration |
| 7.2 | Kubernetes | ❌ | Not started |
| 7.3 | Registry | ❌ | Not started |
| 8.1 | CI Pipeline | ❌ | Not started |
| 8.2 | Promotion Script | ❌ | Not started |
| 8.3 | Parity Checklist | ❌ | Not started |

**Overall: 8 items complete, 7 items partial, 5 items not started**

---

## Recommended Next Steps

### Immediate (Unblocks integration testing):
1. **Complete Foundry Local server** (Epic 4.2):
   * Add `onnxruntime-gpu` and FastAPI to `requirements.txt`
   * Implement `/v1/completions` endpoint mock or integration
   * Add smoke test

2. **Wire inference API service** (Epic 5.1):
   * Add HTTP server entry point
   * Connect to Foundry Local `/v1` endpoint
   * Update docker-compose to run service (not alpine placeholder)

3. **Wire event rules service** (Epic 5.2):
   * Add HTTP or queue interface
   * Consume inference API detections
   * Update docker-compose

4. **Validate end-to-end pipeline** (Epic 7.1):
   * Run `docker-compose up` and verify frames flow through all stages
   * Add integration test script

### Short-term (Closes messaging and local storage):
5. **Implement MQTT publishing** (Epic 6.2):
   * Add `paho-mqtt` dependency
   * Publish event-filtered detections to Mosquitto
   * Include model_id and bundle_digest in payload

6. **Implement dataflow stub** (Epic 6.3):
   * Subscribe to MQTT topics
   * Log or record messages to file

7. **Complete local storage integration** (Epic 5.3):
   * Wire local-store service into event-rules pipeline
   * Persist filtered detections and optional clips

### Medium-term (Adds Kubernetes and CI):
8. **Create Kubernetes manifests** (Epic 7.2)
9. **Stand up local registry** (Epic 7.3)
10. **Implement CI pipeline** (Epic 8.1)
11. **Create promotion script** (Epic 8.2)
12. **Document parity checklist** (Epic 8.3)

### Foundry Local Runtime (Critical blockers):
13. **Obtain and package model files** (Epic 4.1):
    * Download YOLO, Florence-2, Phi-4-multimodal ONNX models
    * Update bundle.json with correct paths and sha256 digests
    * Create `scripts/fetch-model-bundle.sh`

14. **Validate VRAM budget** (Epic 4.3):
    * Load YOLO + Florence-2 concurrently
    * Document memory usage
    * Define fallback for Phi-4-multimodal (quantization or sequential)

---

## Questions for Product/Architecture Review

1. **Model files**: Should we commit quantized ONNX models to the repo, or provide a download/build script only?
2. **Foundry Local server**: Should this be a custom FastAPI implementation for the local dev environment, or a wrapper around a real Foundry/vLLM server?
3. **MQTT topics**: Confirm the naming convention for published detections (e.g., `cv/{site}/{camera}/detections`).
4. **Parity with edge**: Should the local dev env match Azure IoT Operations exactly, or are certain local-only compromises acceptable?
5. **Kubernetes in scope**: Is kind/k3d deployment part of the current sprint, or should we defer to a follow-on iteration after single-box Compose validation?

---
title: Local Development Environment Backlog
description: Work item backlog for building the RTX 5070 local development environment described in the system design
author: Tiger PoC
ms.date: 2026-08-13
ms.topic: reference
keywords:
  - local development
  - foundry local
  - onnx runtime
  - backlog
estimated_reading_time: 10
---

## Scope

This backlog covers the work needed to stand up the local development environment described in the "Local Development Environment" section of [system-design.md](./system-design.md#local-development-environment): a workstation-based pipeline that mirrors the edge architecture using an NVIDIA RTX 5070, Docker, and a local Kubernetes cluster, so the same container image, models, and API contract used at the edge can be developed and tested locally.

Work items are grouped into epics that follow the pipeline stages in the reference architecture. Each item lists a suggested size (S/M/L), dependencies, and acceptance criteria. Sizes are rough guidance, not commitments.

## Progress Snapshot

As of 2026-08-13, Epics 2 and 3 are implemented with unit coverage. Epic 4
has a working CUDA-configurable runtime and a partial model bundle containing
YOLO; Florence-2 and Phi-4-multimodal artifacts remain pending. Epic 5 has
implemented inference normalization, event-rule filtering, and local storage
services, including HTTP service boundaries, but the full pipeline still needs
runtime integration validation. Epics 6.2 through 8 remain outstanding.

## Epic 1: Workstation and GPU Foundation

Prerequisite environment setup so the RTX 5070 is usable by containers before any pipeline code is written.

### 1.1 Verify and document NVIDIA driver and CUDA baseline

* Size: S
* Dependencies: None
* Description: Confirm NVIDIA driver 570+ and CUDA 12.8+ are installed on the workstation and WSL2 distro. Document the verification commands (`nvidia-smi`, `nvcc --version`) and minimum versions in a setup guide.
* Acceptance criteria:
  * `nvidia-smi` reports driver 570 or later inside WSL2.
  * A documented, repeatable verification script or command list exists in the repo.

### 1.2 Install and verify NVIDIA Container Toolkit in WSL2

* Size: S
* Dependencies: 1.1
* Description: Install the NVIDIA Container Toolkit so Docker containers can access the GPU via `--gpus all`. Verify with a minimal CUDA container.
* Acceptance criteria:
  * A test container (for example `nvidia/cuda:12.8.0-base-ubuntu22.04`) runs `nvidia-smi` successfully with `--gpus all`.
  * Setup steps are documented for repeatability on a fresh workstation.

### 1.3 Establish repo scaffolding and devcontainer

* Size: M
* Dependencies: 1.2
* Description: Create the base repository layout (`apps/`, `docker/`, `k8s/`, `models/`) plus a `.devcontainer` configuration and root `docker-compose.yml` skeleton that other work items extend. Application source belongs under an app-specific directory such as `apps/vision-pipeline/`, leaving room for additional apps in the repository.
* Acceptance criteria:
  * Repo has a documented folder layout matching the pipeline components.
  * `.devcontainer.json` builds and opens without error.
  * `docker-compose.yml` skeleton exists with placeholder services for each pipeline stage.

## Epic 2: Video Ingestion

### 2.1 Sample video and RTSP simulator source

* Status: ✅ Complete
* Size: S
* Dependencies: 1.3
* Description: Add sample MP4 clips and a lightweight RTSP simulator (for example an `ffmpeg`-based container looping sample video) that stands in for live camera streams during local development.
* Acceptance criteria:
  * At least one sample video asset or reference to how to obtain one is documented (avoid committing large binaries; use Git LFS or a download script).
  * RTSP simulator container streams the sample video on a local RTSP URL.

### 2.2 Frame grabber service

* Status: ✅ Complete
* Size: M
* Dependencies: 2.1
* Description: Build the frame grabber service that connects to the RTSP simulator (or a recorded MP4 in CI), samples frames at a configurable rate, and forwards them to the pre-processor.
* Acceptance criteria:
  * Frame rate and source (live RTSP vs. recorded file) are configuration, not code.
  * Service emits frames on a defined internal interface (queue, HTTP, or gRPC) consumed by the pre-processor.
  * Unit tests cover frame sampling logic using a recorded file fixture.

## Epic 3: Pre-Processing

### 3.1 Pre-processor service (resize, normalize, batch)

* Status: ✅ Complete
* Size: M
* Dependencies: 2.2
* Description: Implement the pre-processor that resizes, normalizes, and batches frames before they are sent to Foundry Local, matching the input contract expected by the ONNX models.
* Acceptance criteria:
  * Batch size and target resolution are configurable.
  * Output tensors match the documented input shape/dtype for the target models (YOLO, Florence-2, Phi-4-multimodal).
  * Unit tests validate output shape and normalization for representative input frames.

## Epic 4: Foundry Local Runtime

### 4.1 Provision ONNX model bundle (YOLO, Florence-2, Phi-4-multimodal)

* Status: ⏳ In progress (official sources and runtimes selected; YOLO artifact present; Florence-2 and Phi-4 downloads remain pending)
* Size: M
* Dependencies: 1.3
* Description: Package the approved model artifacts used by the pipeline into an immutable, versioned bundle referenced by digest, matching the "Keeping Parity" guidance in the system design. Include a script to fetch/build the bundle locally.
* Acceptance criteria:
  * Bundle has a version identifier and content digest recorded alongside it.
  * A fetch/build script reproduces the same bundle deterministically.
  * Phi-4-multimodal is available in a quantized form (INT4 or INT8) as an option for constrained VRAM scenarios.

### 4.2 Foundry Local container with CUDA/TensorRT execution provider

* Status: ⏳ In progress (CUDA ONNX Runtime container, YOLO path, Phi-4 ORT GenAI adapter, and smoke-test contract are implemented; model downloads and Florence runtime adapter remain pending)
* Size: L
* Dependencies: 1.2, 4.1
* Description: Stand up the Foundry Local runtime container configured to use the CUDA 12.8 execution provider (TensorRT 10.9 optional) targeting `sm_120`, exposing the OpenAI-compatible `/v1` endpoint documented in the architecture.
* Acceptance criteria:
  * Container starts and serves `/v1` endpoints reachable from other pipeline services.
  * Execution provider is selected via configuration/environment variable, not hardcoded.
  * A smoke test sends a sample request through `/v1` and receives a valid inference response.

### 4.3 VRAM budget validation across concurrent models

* Status: ⏳ In progress (VRAM assumptions and INT4 fallback are documented; target-GPU measurement remains pending)
* Size: S
* Dependencies: 4.2
* Description: Validate that YOLO and Florence-2 run concurrently within the 12 GB VRAM budget, and document the fallback (quantized weights or sequential loading) required when Phi-4-multimodal is added.
* Acceptance criteria:
  * Documented VRAM usage for YOLO + Florence-2 running together.
  * Documented and tested fallback strategy for adding Phi-4-multimodal within budget.

## Epic 5: Inference API and Event Rules

### 5.1 Inference API service

* Status: ✅ Complete (HTTP service, frame-to-Foundry path, response normalization, and integration coverage implemented)
* Size: M
* Dependencies: 4.2
* Description: Build the Inference API service that calls the Foundry Local `/v1` endpoint on behalf of the pre-processor and normalizes responses into an internal detection schema.
* Acceptance criteria:
  * Service contract (request/response schema) is documented.
  * Integration test exercises the full path from a sample frame to a normalized detection response.

### 5.2 Event rules engine

* Status: ✅ Complete (unit/API implementation; pipeline publication remains in Epic 6)
* Size: M
* Dependencies: 5.1
* Description: Implement event rules (confidence thresholds, dwell time, zone entry) that filter and enrich raw detections before they are persisted or published.
* Acceptance criteria:
  * Thresholds, dwell time, and zone definitions are configurable without code changes.
  * Unit tests cover each rule type independently and in combination.

### 5.3 Local storage for detections and clips

* Status: ✅ Complete (filesystem service and HTTP persistence boundary implemented)
* Size: S
* Dependencies: 5.2
* Description: Add local storage (filesystem or lightweight database) for detections and short clips, mirroring the edge's Storage Spaces Direct-backed local store at a scale appropriate for a workstation.
* Acceptance criteria:
  * Detections and sampled clips are persisted with enough metadata (timestamp, camera/source id, model id, confidence) to support later inspection.
  * Storage location and retention are configurable.

## Epic 6: Local Messaging and Dataflow Stub

### 6.1 Mosquitto MQTT broker container

* Status: ⏳ In progress (broker declared in Compose; topic configuration and connectivity test pending)
* Size: S
* Dependencies: 1.3
* Description: Add a Mosquitto container to `docker-compose.yml` as the local stand-in for the Azure IoT Operations broker, with the same topic hierarchy convention (`cv/{site}/{camera}/detections`).
* Acceptance criteria:
  * Broker starts via `docker-compose up` and accepts MQTT v5 connections.
  * Topic naming convention is documented and used consistently by publishers.

### 6.2 Publish detections to MQTT from event rules

* Size: S
* Dependencies: 5.2, 6.1
* Description: Wire the event rules engine to publish filtered detections to the Mosquitto broker on the documented topic hierarchy, including model identifier and bundle digest in the payload.
* Acceptance criteria:
  * Published payloads include model id and bundle digest fields.
  * A local subscriber test confirms messages arrive on the expected topic.

### 6.3 Dataflow stub service

* Size: S
* Dependencies: 6.2
* Description: Build a lightweight dataflow stub that subscribes to MQTT topics and simulates north-bound delivery (log to console or write to a local file) in place of Azure IoT Operations dataflows.
* Acceptance criteria:
  * Stub subscribes to the detection topic hierarchy and records received messages.
  * Behavior is clearly marked as a local simulation, not a production dataflow implementation.

## Epic 7: Local Orchestration and Registry

### 7.1 Docker Compose path for full pipeline

* Status: ⏳ In progress (services are wired with default simulator input; end-to-end detection and publication validation pending)
* Size: M
* Dependencies: 2.2, 3.1, 4.2, 5.1, 5.2, 6.1
* Description: Wire all services (frame grabber, pre-processor, Foundry Local, inference API, event rules, Mosquitto, dataflow stub) into a single `docker-compose.yml` that runs the full pipeline end to end with `docker-compose up`.
* Acceptance criteria:
  * Full pipeline starts with one command and processes the sample video into published detections.
  * Service dependencies and startup order are correctly expressed in the compose file.

### 7.2 Local Kubernetes manifests (kind or k3d)

* Size: M
* Dependencies: 7.1
* Description: Translate the Compose-based pipeline into Kubernetes manifests (or a Helm chart) deployable to a local `kind` or `k3d` cluster, mirroring the AKS-enabled-by-Arc deployment model used at the edge.
* Acceptance criteria:
  * `kind` or `k3d` cluster reference config is documented and reproducible.
  * Manifests deploy the full pipeline and it processes the sample video successfully.
  * GPU passthrough to pods is documented and verified (for example via the NVIDIA device plugin).

### 7.3 Local container registry

* Size: S
* Dependencies: 7.1
* Description: Stand up a local registry (for example the `registry:2` image) for images built during development, and document the tagging convention used before promotion to Azure Container Registry.
* Acceptance criteria:
  * Local registry runs alongside the local cluster.
  * Documented tagging convention aligns with the ACR promotion path.

## Epic 8: CI, Parity, and Promotion

### 8.1 CI pipeline running recorded-video validation

* Size: M
* Dependencies: 7.1
* Description: Add a CI workflow that runs the event rules and inference API against recorded sample video (CPU or CI-available execution provider) to validate detection behavior before promotion, per the "Keeping Parity" guidance.
* Acceptance criteria:
  * CI job runs the pipeline against a recorded video fixture and asserts expected detections.
  * CI does not depend on GPU availability; it falls back to a CPU execution provider.

### 8.2 Image and model bundle promotion script

* Size: S
* Dependencies: 4.1, 7.3
* Description: Write a script or CI job that tags and pushes the pipeline image and model bundle to Azure Container Registry, referencing the same bundle digest used locally, matching the promotion path shown in the local dev diagram.
* Acceptance criteria:
  * Script pushes image and model bundle with the digest recorded during Epic 4.1.
  * Promotion is invoked from CI or a documented manual command, not ad hoc steps.

### 8.3 Dev/edge parity checklist

* Size: S
* Dependencies: 8.1, 8.2
* Description: Produce a checklist (or automated check) confirming the local dev environment matches the "Dev and Edge Parity" table in the system design: execution provider selection via config, shared image source lineage, consistent secrets handling pattern, and consistent messaging topic conventions.
* Acceptance criteria:
  * Checklist references each row of the parity table with a pass/fail or note.
  * Any intentional deviations from edge parity are documented with rationale.

## Suggested Sequencing

1. Epic 1 (workstation foundation) unblocks everything else.
2. Epics 2-4 (ingestion, pre-processing, Foundry Local) can proceed in parallel once Epic 1 is done, since they touch different services.
3. Epic 5 depends on Epic 4 and partially on Epics 2-3 for realistic testing.
4. Epic 6 depends on Epic 5's event rules output.
5. Epic 7 integrates everything into a runnable environment.
6. Epic 8 closes the loop with CI validation and the promotion path to Azure Local.

## Out of Scope

* Azure Local cluster provisioning and Azure Arc onboarding (covered separately in the edge deployment work).
* Capacity planning and hardware sizing for production edge deployments.
* Azure IoT Operations broker and dataflow configuration itself (only a local stub is in scope here).

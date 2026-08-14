---
title: Local Development Setup
description: Workstation setup and verification for the RTX 5070 local computer vision pipeline
author: Tiger PoC
ms.date: 2026-08-13
ms.topic: how-to
keywords:
  - WSL2
  - NVIDIA Container Toolkit
  - Docker
  - CUDA
  - local development
estimated_reading_time: 8
---

## Prerequisites

Use a Linux or WSL2 distribution with an NVIDIA RTX 5070. The supported baseline is:

* NVIDIA driver 570 or later
* CUDA 12.8 or later when the host CUDA toolkit is installed
* Docker Desktop with WSL integration, or Docker Engine with the NVIDIA Container Toolkit
* Docker Compose v2

The host CUDA toolkit is optional because CUDA runtime libraries are supplied by the container images. The GPU driver is still required on the host.

## Verify The Workstation

Run the repository verifier from the project root:

```bash
./scripts/verify-local-environment.sh
```

The verifier checks `nvidia-smi`, validates the driver baseline, reports the host CUDA toolkit version when `nvcc` is installed, and checks Docker and Compose availability. A missing `nvcc` produces a warning rather than a failure.

You can also inspect the GPU directly:

```bash
nvidia-smi
nvcc --version
```

## Enable Docker GPU Access In WSL2

For Docker Desktop, enable **Use the WSL 2 based engine** and enable the target distribution under **Settings > Resources > WSL Integration**. Restart WSL2, then verify `docker --version` and `docker compose version`.

For native Docker Engine in WSL2, install the NVIDIA Container Toolkit using the [NVIDIA Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), configure Docker, and restart it:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker info --format '{{json .Runtimes}}'
```

## Verify Container GPU Access

After Docker is available, run:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

The command passes when the container prints the RTX 5070 and the host driver version.

## Video Sources

Epic 2 supports both repeatable test input and real RTSP cameras on the local network.

The default Compose stack includes the simulator for repeatable local runs:

```bash
VIDEO_SOURCE=rtsp://rtsp-simulator:8554/camera-1 docker compose up
```

The simulator publishes an FFmpeg test pattern through MediaMTX. From the host, that stream is also available at `rtsp://localhost:8554/camera-1`.

To use a real camera, copy `.env.example` to `.env` and set the camera URL. For example:

```dotenv
VIDEO_SOURCE_TYPE=rtsp
VIDEO_SOURCE=rtsp://192.168.1.50:554/stream1
CAMERA_ID=loading-dock
FRAME_RATE=2
```

Use the URL format and credentials required by the camera. Keep `.env` out of source control. Containers use the same LAN routing as the Docker host; if a camera is reachable from WSL2 but not from a container, verify Docker Desktop networking and firewall rules.

For a recorded MP4, place it under `samples/` and configure:

```dotenv
VIDEO_SOURCE_TYPE=file
VIDEO_SOURCE=/media/sample.mp4
```

`FRAME_RATE` controls the number of frames sampled per second. The frame-grabber sends each JPEG frame to the pre-processor boundary at `POST /frames` with `X-Camera-Id`, `X-Frame-Sequence`, `X-Captured-At`, `X-Frame-Width`, and `X-Frame-Height` headers.

## Start The Development Scaffold

For a real camera, set `VIDEO_SOURCE` in `.env`, then start the stack. The frame-grabber exits with a clear source error if this value is blank:

```bash
docker compose up
```

For the generated test stream, use the simulator source:

```bash
VIDEO_SOURCE=rtsp://rtsp-simulator:8554/camera-1 docker compose up
```

To use a real camera instead, set `VIDEO_SOURCE_TYPE=rtsp` and a camera URL in `.env`.

Open the repository in VS Code and use **Dev Containers: Reopen in Container** to use the shared development environment.

## Container Guide

The Compose file describes the complete target pipeline, but only the Epic 2 video-ingestion services are implemented so far. The remaining services are named placeholders for later backlog items.

| Container | Default | Purpose | Current state |
|-----------|---------|---------|--------------|
| `frame-grabber` | Yes | Opens the configured recorded file or RTSP stream, samples frames at `FRAME_RATE`, JPEG-encodes them, and sends them to the pre-processor | Implemented in `apps/vision-pipeline/frame_grabber/service.py` |
| `pre-processor` | Yes | Receives JPEG frames and their metadata at `POST /frames`; this is the handoff boundary for the future resize, normalize, and batch service | Temporary receiver implemented; preprocessing is Epic 3 |
| `rtsp-simulator` | Yes | Provides an RTSP server at `rtsp://rtsp-simulator:8554/camera-1` for repeatable local tests | Implemented with MediaMTX |
| `sample-video` | Yes | Generates a synthetic test pattern with FFmpeg and publishes it to the RTSP simulator | Implemented for testing; it is not a real camera |
| `foundry-local` | Yes | CUDA-configurable local runtime exposing `/healthz` and `/v1` | YOLO ONNX inference; model weights are fetched separately |
| `inference-api` | Yes | Calls Foundry Local and normalizes inference responses | Implemented for frame requests |
| `event-rules` | Yes | Future confidence, dwell-time, and zone-entry rules engine | Placeholder for Epic 5 |
| `local-store` | Yes | Future local persistence for detections and clips | Placeholder for Epic 5 |
| `mosquitto` | Yes | Future local MQTT broker, replacing Azure IoT Operations for workstation development | Placeholder for Epic 6 |
| `dataflow-stub` | Yes | Future local subscriber that simulates north-bound dataflow delivery | Placeholder for Epic 6 |

### Video Data Flow

For a real camera or recorded file, the path is:

```text
camera or MP4 -> frame-grabber -> pre-processor
```

For the simulator, the path is:

```text
sample-video (FFmpeg) -> rtsp-simulator (MediaMTX) -> frame-grabber -> pre-processor
```

The simulator pair provides a repeatable camera-like source for local development. Configure a real camera URL when using production-like input.

### Foundry Local Runtime

The `foundry-local` service builds from `docker/foundry-local` and mounts the
versioned manifest and downloaded artifacts from `models/`. It exposes the
OpenAI-compatible model and chat completion routes used by later pipeline
services:

```bash
FOUNDRY_RUNTIME_MODE=mock docker compose up --build foundry-local
curl http://localhost:8000/healthz
curl http://localhost:8000/v1/models
```

Use `FOUNDRY_RUNTIME_MODE=mock` for a CPU-only contract smoke test. The default
`onnx` mode requires an installed model artifact and runs YOLO preprocessing,
ONNX inference, and detection post-processing. Set
`FOUNDRY_EXECUTION_PROVIDER` to select the provider; the local GPU default is
`CUDAExecutionProvider`.

Fetch and verify model artifacts before using ONNX mode:

```bash
./scripts/fetch-model-bundle.sh
./scripts/fetch-model-bundle.sh --verify
```

The manifest does not embed third-party URLs or weights until the exact ONNX
exports, licenses, and SHA-256 digests are approved.

### Why Placeholder Containers Exist

The placeholders make the intended Compose topology visible early and give later epics stable service names and dependency edges. They currently run an idle Alpine process; they do not perform inference, persistence, MQTT messaging, or event processing yet. They should be replaced as each corresponding backlog item is implemented.

## Repository Layout

```text
.
|-- apps/
|   `-- vision-pipeline/  Source for the computer vision pipeline application
|-- samples/              Local recorded video inputs (not committed)
|-- .devcontainer/        Shared VS Code development container configuration
|-- docker/                Shared container build contexts
|-- k8s/                   Shared local Kubernetes manifests
|-- models/                Downloaded or generated model bundles
|-- scripts/               Workstation and pipeline utility scripts
|-- docker-compose.yml     Shared local service scaffold
`-- docs/                  Architecture and setup documentation
```

Application source is scoped below `apps/` so additional applications can be added without creating multiple unrelated source trees at the repository root.
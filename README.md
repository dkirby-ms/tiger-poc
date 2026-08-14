---
title: Tiger PoC
description: Local edge computer vision proof of concept for Foundry Local, ONNX model runtimes, and RTSP-based video ingestion
author: Tiger PoC
ms.date: 2026-08-13
ms.topic: overview
keywords:
  - computer vision
  - edge ai
  - foundry local
  - rtsp
  - docker
estimated_reading_time: 8
---

## Overview

Tiger PoC is a local edge-computer-vision proof of concept built around a small Python microservice pipeline, Docker Compose orchestration, and a local Foundry runtime for ONNX-based model serving. The project targets workstation and edge-style development using an RTX-class GPU and RTSP or recorded video inputs.

The current implementation focuses on the video ingestion and inference boundary:

* capture frames from a real RTSP stream or file source
* forward sampled JPEG frames to a preprocessing boundary
* call a local inference endpoint
* normalize detections for downstream rules and persistence
* provide a local deployment scaffold that mirrors the eventual Azure Local design

This repository is intentionally structured as a local prototype and a reference architecture for later Azure Local deployment and cloud integration.

## What is in this repository

| Area | Purpose |
|------|---------|
| [apps/vision-pipeline](apps/vision-pipeline) | Python services for framing, preprocessing, inference, rules, and storage |
| [docker-compose.yml](docker-compose.yml) | Local Compose stack for the edge pipeline and supporting services |
| [models](models) | Downloaded or generated model bundles and manifest metadata |
| [apps/local-model-runtime](apps/local-model-runtime) | Local model runtime that serves the Foundry-compatible inference API |
| [docker](docker) | Container build contexts and supporting runtime tooling |
| [scripts](scripts) | Verification and setup helpers for workstation, model, and runtime checks |
| [docs](docs) | Architecture, setup, and operational guidance |
| [samples](samples) | Local recorded inputs and sample media |
| [k8s](k8s) | Shared Kubernetes-oriented deployment assets |
| [data](data) | Detection outputs and persistence examples |

## Solution architecture

The project models a lightweight vision pipeline that mirrors an edge deployment pattern:

```text
camera or file -> frame-grabber -> pre-processor -> inference-api -> event-rules -> local-store
                              |
                              v
                        Foundry Local
```

The local deployment stack includes the following services:

* `frame-grabber`: reads RTSP or file input, samples frames, and pushes JPEG payloads upstream
* `pre-processor`: receives frames and preserves the handoff boundary for resizing, normalization, and batching
* `local-model-runtime`: serves a local OpenAI-compatible model runtime from the bundled model directory
* `inference-api`: calls Foundry Local and normalizes responses into a shared detection schema
* `event-rules`: applies confidence, dwell-time, and zone logic
* `local-store`: persists detections and clips locally
* `rtsp-simulator`: provides a test RTSP feed for repeatable local runs
* `mosquitto` and `dataflow-stub`: placeholders for local messaging and north-bound flow simulation

This layout intentionally makes future service boundaries explicit while keeping the current codebase focused on working local ingestion and inference.

## Repository status

The repository is a working prototype with an implemented local development scaffold. Current scope is best described as:

* implemented: local video capture, frame delivery, model runtime verification, inference normalization, and service scaffold
* partial: preprocessing pipeline behavior, event rules logic, and durable local storage
* planned: broader AZURE Local and cloud integration, message transport, and production-style persistence

The docs describe the intended architecture and current backlog explicitly, so the local environment remains useful for testing and iteration without overstating production readiness.

## Prerequisites

To run the project locally, you will need:

* Linux or WSL2
* Docker Compose v2
* NVIDIA driver and container toolkit support for GPU-backed execution
* Python 3.11 for the app services
* A valid model bundle under [models](models)

The recommended workstation flow is described in [docs/local-development.md](docs/local-development.md). For GPU and Docker setup details, see that document and the model setup guide.

## Quick start

1. Create your local environment configuration from the sample file:

   ```bash
   cp .env.example .env
   ```

2. Set the camera or input source in `.env` before starting the default stack. For the built-in simulator, you can use:

   ```bash
   VIDEO_SOURCE=rtsp://rtsp-simulator:8554/camera-1 docker compose up --build
   ```

3. Verify the workstation setup:

   ```bash
   ./scripts/verify-local-environment.sh
   ```

4. Fetch and verify the model bundle:

   ```bash
   ./scripts/fetch-model-bundle.sh --verify
   ```

5. Validate the local Foundry runtime:

   ```bash
   ./scripts/verify-local-model-runtime.sh
   ```

6. Start the full stack:

   ```bash
   docker compose up --build
   ```

## Local development workflow

The application code is contained in [apps/vision-pipeline](apps/vision-pipeline). To work from that directory:

```bash
cd apps/vision-pipeline
python -m pip install -e '.[test]'
pytest
```

The tests cover runtime contract and model-manifest expectations, including the local bundle verification flow. The project is designed for iterative development using Docker Compose for infrastructure and pytest for service-level checks.

## Model bundle and Foundry runtime

The project expects model assets under [models](models), with the main bundle metadata defined in [models/bundle.json](models/bundle.json). The runtime model setup documentation is in [docs/model-setup.md](docs/model-setup.md).

The repository is designed around these model families:

* YOLO for object detection
* Florence-2 for visual understanding and multimodal capabilities
* Phi-4 multimodal for ONNX Runtime GenAI workloads

The default local setup uses a Foundry-compatible service exposed on port `8000` and expects the model bundle to be present before inference tests run.

## Key documentation

* [docs/system-design.md](docs/system-design.md) - reference architecture and edge design rationale
* [docs/local-development.md](docs/local-development.md) - GPU, Docker, and local startup guidance
* [docs/model-setup.md](docs/model-setup.md) - model acquisition, verification, and bundle structure
* [apps/vision-pipeline/README.md](apps/vision-pipeline/README.md) - app-level implementation notes

## Directory layout

```text
.
├── apps/
│   └── vision-pipeline/
├── data/
├── docker/
├── docs/
├── k8s/
├── models/
├── samples/
├── scripts/
├── .env.example
├── docker-compose.yml
├── README.md
└── .gitignore
```

## Security and operational notes

This repository is a development environment and proof of concept, not a hardened production deployment. Keep the following in mind while working in the repo:

* do not commit real camera URLs, tokens, or environment secrets
* keep model artifacts and bundle metadata versioned and verified
* use the local runtime and verification scripts before broad changes
* treat the placeholder services as explicit backlog items rather than production components

## Contribution guidance

This project is best developed in small, testable increments. A strong local workflow is:

1. verify the workstation and model bundle
2. run the local Foundry service
3. make a focused change in the Python app or service contract
4. validate with pytest and Compose-based smoke checks
5. update the relevant docs when behavior or setup changes

For day-to-day work, start with the app scope in [apps/vision-pipeline](apps/vision-pipeline) and use the supporting docs in [docs](docs) for environment setup and architecture.

## Summary

Tiger PoC demonstrates a practical local AI vision pipeline built for repeatable developer testing and early edge-system design. It prioritizes clarity, GPU-backed local execution, and architecture parity with a future Azure Local deployment, while keeping the current implementation focused on the working pieces of the system.

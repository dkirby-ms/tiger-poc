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
| [apps/pipeline_framework](apps/pipeline_framework) | Manifest-driven framing, preprocessing, inference, rules, and storage runtime |
| [docker-compose.yml](docker-compose.yml) | Local Compose stack for the edge pipeline and supporting services |
| [models](models) | Downloaded or generated model bundles and manifest metadata |
| [apps/local_model_runtime](apps/local_model_runtime) | Generic single-model service, run once per model, serving the Foundry-compatible inference API |
| [docker](docker) | Container build contexts and supporting runtime tooling |
| [scripts](scripts) | Verification and setup helpers for workstation, model, and runtime checks |
| [docs](docs) | Architecture, setup, and operational guidance |
| [pipelines](pipelines) | Executable pipeline manifests |
| [data](data) | Detection outputs and persistence examples |

## Solution architecture

The project models a lightweight vision pipeline that mirrors an edge deployment pattern:

```text
image, folder, or video -> letterbox -> model deployment -> threshold -> dwell -> JSONL
                              |
                              v
                        Foundry Local
```

The local deployment stack includes the following services:

* `pipeline_framework`: validates a typed DAG and runs bounded in-process channels
* `pre-processor`: receives frames and preserves the handoff boundary for resizing, normalization, and batching
* `model-yolo`, `model-florence-2`, `model-phi-4-multimodal`: one instance each of the same generic model service image, isolated per model and configured from [models/services.json](models/services.json)
* `infer.foundry.local`: resolves a ready model by deployment identity and normalizes detections
* `rule.threshold` and `rule.dwell`: produce one event per continuous matching episode
* `sink.jsonl`: persists versioned events with bounded file retention

This layout intentionally makes future service boundaries explicit while keeping the current codebase focused on working local ingestion and inference.

## Repository status

The repository is a working prototype with an implemented local development scaffold. Current scope is best described as:

* implemented: image, folder, recorded-video, and reconnecting RTSP input; bounded channels; manifest validation; local inference; threshold and dwell rules; retained JSONL output
* implemented: predictive request batching, workload-specific authentication, and local model lifecycle contracts
* planned: object tracking, clip and MQTT sinks, HTTP partitioning, and live Foundry Local operator integration

The docs describe the intended architecture and current backlog explicitly, so the local environment remains useful for testing and iteration without overstating production readiness.

## Prerequisites

To run the project locally, you will need:

* Linux or WSL2
* Docker Compose v2
* NVIDIA driver and container toolkit support for GPU-backed execution
* Python 3.11 for the app services
* A valid model bundle under [models](models)

Use [docs/model-setup.md](docs/model-setup.md) for model acquisition and artifact verification.

## Quick start

1. Prepare the local development environment:

   ```bash
   ./scripts/setup-local-dev.sh
   ```

   Add `--fetch-models` when the approved model artifacts are ready to
   download. Use `--check-only` to inspect host prerequisites without making
   changes.

2. Verify the workstation setup:

   ```bash
   ./scripts/verify-local-environment.sh
   ```

3. Fetch and verify the model bundle:

   ```bash
   ./scripts/fetch-model-bundle.sh --verify
   ```

4. Validate the local Foundry runtime:

   ```bash
   ./scripts/verify-local-model-runtime.sh
   ```

5. Validate and run a pipeline manifest:

   ```bash
   uv run --with-requirements requirements-dev.txt python -m apps.pipeline_framework validate pipelines/local-yolo.yaml
   uv run --with-requirements requirements-dev.txt python -m apps.pipeline_framework run pipelines/local-yolo.yaml
   ```

## Local development workflow

Run the complete test suite from the repository root:

```bash
uv run --with-requirements requirements-dev.txt pytest -q
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
* [docs/pipeline-framework.md](docs/pipeline-framework.md) - implemented core and target architecture
* [docs/model-setup.md](docs/model-setup.md) - model acquisition, verification, and bundle structure

## Directory layout

```text
.
├── apps/
│   ├── local_model_runtime/
│   └── pipeline_framework/
├── docs/
├── models/
├── pipelines/
├── scripts/
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

For day-to-day work, start with [apps/pipeline_framework](apps/pipeline_framework) and use [docs/pipeline-framework.md](docs/pipeline-framework.md) for the architecture and remaining migration phases.

## Summary

Tiger PoC demonstrates a practical local AI vision pipeline built for repeatable developer testing and early edge-system design. It prioritizes clarity, GPU-backed local execution, and architecture parity with a future Azure Local deployment, while keeping the current implementation focused on the working pieces of the system.

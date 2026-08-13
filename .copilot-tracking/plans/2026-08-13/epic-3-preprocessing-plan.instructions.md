---
description: Plan for implementing Epic 3 preprocessing in the Tiger PoC vision pipeline
applyTo: '**/*'
---

## User Requests

1. Implement the missing Epic 3 pre-processor stage for the local vision pipeline.
2. Keep batch size and target resolution configurable through environment variables.
3. Produce a tensor layout suitable for later model inference work and validate it with tests.

## Overview

The local pipeline already collects JPEG frames from the RTSP/file source, but it does not yet resize, normalize, or batch them in a way the inference layer can consume. This plan adds a dedicated preprocessing package, tests for the tensor contract, and switches the Docker service to run the new implementation.

## Context Summary

Referenced instructions and project context:

* [apps/vision-pipeline/README.md](apps/vision-pipeline/README.md)
* [docs/backlog-local-dev-environment.md](docs/backlog-local-dev-environment.md)
* [docs/system-design.md](docs/system-design.md)
* [apps/vision-pipeline/frame_grabber/service.py](apps/vision-pipeline/frame_grabber/service.py)
* [apps/vision-pipeline/frame_grabber/receiver.py](apps/vision-pipeline/frame_grabber/receiver.py)

## Implementation checklist

- [ ] Add preprocessing config and tensor conversion logic
- [ ] Add a dedicated pre-processor package and HTTP handler
- [ ] Update Docker Compose to invoke the new service
- [ ] Add pytest coverage for resize, normalization, batching, and config
- [ ] Install project dependencies and run the targeted tests

<!-- parallelizable: false -->

## Dependencies

* Python 3.11+
* OpenCV Python headless
* Pytest
* Existing frame-grabber HTTP contract

## Success criteria

* Preprocessing code exists under `apps/vision-pipeline/pre_processor`.
* `PreprocessorConfig.from_environment()` reads width, height, and batch size from env vars.
* `preprocess_frame()` and `preprocess_batch()` return float32 tensors in channel-first layout.
* Unit tests pass for the preprocessing contract.
* Docker Compose references the pre-processor as a real service implementation rather than the temporary receiver.

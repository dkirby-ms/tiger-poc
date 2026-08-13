---
title: Epic 3 Pre-Processing Research
description: Research and implementation plan for the local video preprocessing stage in the Tiger PoC vision pipeline
author: Tiger PoC
ms.date: 2026-08-13
ms.topic: reference
---

## Scope

This research covers the missing Epic 3 pre-processor stage, which turns JPEG frames from the frame grabber into normalized tensors suitable for model inference while keeping the configuration flexible enough to support different model contracts.

## Findings

* The repository already contains a frame-grabber service that emits JPEG frames to an HTTP boundary with metadata headers.
* The local design documents define the pre-processor as the resize, normalize, and batching step before Foundry Local.
* There is no implementation yet for preprocessing, batching, or model-specific tensor formatting.
* The project already uses pytest, OpenCV, and a simple Python package layout under `apps/vision-pipeline`.

## Selected approach

Implement a dedicated `pre_processor` package with a `PreprocessorConfig` dataclass and `preprocess_frame`/`preprocess_batch` functions that:

* decode JPEG bytes into an OpenCV image,
* resize using OpenCV to the configured target width and height,
* convert the image from BGR to RGB,
* transpose to channel-first layout `(C, H, W)`,
* normalize pixel values to the `[0.0, 1.0]` range as float32 tensors,
* support batching by stacking frames along the leading dimension.

This yields a stable internal tensor contract for later inference service work without hardcoding a single model implementation.

## Validation plan

* Add a pytest regression for resizing, channel ordering, and float32 normalization.
* Add a pytest regression for batching multiple images into a single tensor.
* Add a config test to confirm environment-driven width/height/batch settings.
* Install dependencies and run the targeted suite from `apps/vision-pipeline`.

## Artifacts referenced

* [docs/backlog-local-dev-environment.md](docs/backlog-local-dev-environment.md)
* [docs/system-design.md](docs/system-design.md)
* [apps/vision-pipeline/frame_grabber/service.py](apps/vision-pipeline/frame_grabber/service.py)
* [apps/vision-pipeline/frame_grabber/receiver.py](apps/vision-pipeline/frame_grabber/receiver.py)

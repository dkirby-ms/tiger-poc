---
title: Epic 3 Preprocessing Details
description: Implementation notes for Epic 3 preprocessing work in the local vision pipeline
author: Tiger PoC
ms.date: 2026-08-13
ms.topic: reference
---

## Phase details

### Phase 1: Tensor contract and config

* Create a `pre_processor` package under `apps/vision-pipeline`.
* Add `PreprocessorConfig` with target width, height, and batch size.
* Default values should be safe for local development and remain environment-driven.

### Phase 2: Preprocessing implementation

* Implement JPEG decode and resize logic using OpenCV.
* Convert BGR to RGB and reorder dimensions to `(C, H, W)`.
* Normalize each channel to `[0.0, 1.0]` and cast to `np.float32`.
* Batch multiple scenes using a leading dimension.

### Phase 3: HTTP boundary

* Provide a lightweight HTTP handler that accepts `POST /frames` and stores or returns a processed tensor representation.
* Keep the contract consistent with the existing frame-grabber metadata headers.

### Phase 4: Validation

* Run `pip install -e '.[test]'` in the app folder.
* Execute the targeted pytest suite and fix issues until it passes.

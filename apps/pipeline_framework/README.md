---
title: Pipeline Framework
description: Manifest-driven local video analysis runtime with bounded channels and reusable stages
author: Tiger PoC
ms.date: 2026-08-16
ms.topic: reference
---

## Run a pipeline

Validate the graph before acquiring files or model resources:

```bash
uv run --with-requirements requirements-dev.txt \
  python -m apps.pipeline_framework validate pipelines/local-yolo.yaml
```

Set the `source.file` path in the manifest to an image, image folder, or video,
then run it:

```bash
uv run --with-requirements requirements-dev.txt \
  python -m apps.pipeline_framework run pipelines/local-yolo.yaml
```

For a live RTSP feed, keep the camera URL outside the manifest:

```bash
read -rsp "RTSP URL: " TIGER_RTSP_URL
export TIGER_RTSP_URL
echo
uv run --with-requirements requirements-dev.txt \
  python -m apps.pipeline_framework validate pipelines/rtsp-yolo.yaml
uv run --with-requirements requirements-dev.txt \
  python -m apps.pipeline_framework run pipelines/rtsp-yolo.yaml
```

Press Ctrl+C to stop the live pipeline. Events are appended to
`data/rtsp-events.jsonl`. `source.rtsp` defaults to TCP, reconnects after open,
decode, or end-of-stream failures, and repeats the final configured backoff
until the feed returns. Set `transport: udp` only when the camera or network
requires it.

## Implemented stages

| Type                    | Behavior                                      |
|-------------------------|-----------------------------------------------|
| `source.file`           | Image, sorted image folder, or recorded video |
| `source.rtsp`           | Live RTSP with sampling and reconnect         |
| `transform.letterbox`   | Aspect-preserving resize and padding          |
| `infer.foundry.local`   | Ready deployment resolution and inference     |
| `rule.threshold`        | Label, confidence, and count evaluation       |
| `rule.dwell`            | One event per continuous matching episode     |
| `sink.jsonl`            | Versioned output with bounded byte retention  |

Every graph edge uses a bounded in-process channel with `block`,
`drop_oldest`, `drop_newest`, or `sample` overflow behavior. Runner results
report per-edge sent, received, dropped, depth, and closed values plus every
stage's health.

## Current limits

The executable schema supports one source, one input per downstream stage, and
fan-out. It rejects fan-in until merge ordering and multi-upstream closure are
defined. Dwell tracks continuous label presence per stream; stable object
identity requires the planned tracking stage.
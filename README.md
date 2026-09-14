---
title: Tiger POC
description: Portable factory perception with a local Android-to-vision development baseline
---

## Project

Tiger explores portable, composable perception workloads that connect to an
existing digital-twin platform. Start with the [core idea](docs/core-idea.md),
[MVP design](docs/mvp-design.md), and
[engineering standards](docs/engineering-standards.md).

## Current development baseline

The working local path is an Android camera sending H.264 over RTSP to a
Python/OpenCV/YOLO Docker container, which writes JSONL observations.
The Android app and vision container are separate applications. A future
brain container is not implemented, and no Rover controls are connected.

See the [development handoff](docs/development-status.md) for the current
state, known limitations, restart commands and remaining work.

| Area | Guide |
|------|-------|
| Contribution workflow and pinned HVE Core | [Contributing](CONTRIBUTING.md) |
| Android camera source | [Tiger Camera](apps/tiger-camera/README.md) |
| Vision image and Compose configuration | [Vision container](apps/detect/container/README.md) |
| Original detector example | [RTSP detector](apps/detect/README.md) |

This is a local development baseline, not a production camera service,
certified safety system, or completed digital-twin integration.

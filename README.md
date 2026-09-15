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
The Android app, vision service and advisory rules brain are separate applications.
The brain reports `occupied`, `clear` or `unknown` from person-in-zone evidence;
it has no LLM, motor controls or digital-twin connector. Camera capture auto-starts
in the foreground after permission and network checks, without an acknowledgement
checkbox. The latest installed APK has produced portrait person detections and
brain rule events; sustained performance remains unqualified.

See the [development handoff](docs/development-status.md) for the current
state, known limitations, restart commands and remaining work.

| Area | Guide |
|------|-------|
| Contribution workflow and pinned HVE Core | [Contributing](CONTRIBUTING.md) |
| Android camera source | [Tiger Camera](apps/tiger-camera/README.md) |
| Vision image and detector CLI | [Vision](apps/vision/README.md) |
| Advisory rules and evidence API | [Brain](apps/brain/README.md) |

## Repository layout

```text
apps/
  vision/        Dockerfile, README.md, pyproject.toml, uv.lock, src/, tests/
  brain/         Dockerfile, README.md, pyproject.toml, uv.lock, src/, tests/
  tiger-camera/  Android application
deploy/
  local/         compose.yaml, brain.compose.yaml, .env.example, tests/
data/            Ignored local observations and private camera configuration
models/          Ignored trusted model weights
docs/            Design, standards and development guides
lib/hve-core/    Pinned development tooling, not an application build system
.github/         Managed development workflow and instructions
```

Each Python app owns one production dependency manifest and lock. Local deployment
configuration belongs under `deploy/local`; its private `.env` stays ignored.
The root `manifest.yaml` remains an illustrative future workload contract, not the
executable local Compose configuration.

This is a local development baseline, not a production camera service,
certified safety system, or completed digital-twin integration.

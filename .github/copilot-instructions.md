---
description: Tiger POC project boundaries and HVE Core contribution workflow
---

# Tiger POC instructions

Read `docs/core-idea.md` and `docs/mvp-design.md` before making application changes.
Read and follow the canonical [Dark Factory Engineering Standards](../docs/engineering-standards.md)
for all design, implementation, deployment, and porting decisions.
This project is a portable factory-perception accelerator, not a companion robot.
Python is the application language. Use OpenCV/YOLO for vision, RTSP/ONVIF discovery
for video inputs, Docker packaging, and the platform standards in that document.
Specific dependency versions, model/runtime compatibility, deployment manifest
schemas, and the digital-twin target/API still require scoped decisions.
The existing detector has a shared Docker/Compose baseline in `apps/detect`
and `deploy/vision`. The separate Kotlin app in `apps/tiger-camera` is an approved
Android-only language exception. Live RTSP and local YOLO detections work.
Read `docs/development-status.md` for current capability limits and open items.
Do not treat remaining standards as implemented features: ONVIF discovery,
generic event mapping, a brain service and platform integrations remain pending.
Do not treat the tooling inside `lib/hve-core` as the application's build system.

Use the HVE Core Research, Plan, Implement, Review workflow.
The managed agents, instructions, prompts, and skills are installed under `.github`.
The pinned upstream source and its license notices are in `lib/hve-core`.
See `CONTRIBUTING.md` for installation, use, and controlled updates.
Project requirements and existing behavior take precedence over generic HVE examples.
Use the GitHub Fork + Pull Request contribution model even with upstream WRITE access.
Use Infrastructure as Code and reusable manifest-driven components for future deployments.

Preserve these boundaries: capture adapter, inference adapter, observation contract,
ontology/event mapper, and digital-twin connector. Runtime selection must not change
the common event contract. Keep a deterministic workload and local sink available
when a real model or twin platform is unavailable.
All solutions must be composable. Declare each component's inputs, outputs,
configuration, dependencies, and deployment requirements through reusable manifest
contracts. Keep environment-specific values separate from reusable definitions.

The candidate source is `https://github.com/lovelacer74/hve-copilot-rover`.
Reuse functionality selectively, not Rover's architecture wholesale. Assess
orchestration, provider, configuration, and telemetry logic before claiming reuse.
Replace or adapt existing vision implementations to Tiger's Python/OpenCV/YOLO
and RTSP/ONVIF standards. Decouple motion, clearance, and person-approach semantics
from factory observations and outputs. Leave the source repository unchanged.
Confirm the modules and behavior to port before copying application code.
Do not import rover-specific hardware setup, motor control, safety distances,
personal identity data, credentials, or runtime agents into the factory pipeline.
Reuse public module interfaces and bring relevant tests with each approved port.

Do not deploy cloud resources, push changes, or modify remote settings unless asked.
Do not log or commit secrets. Keep each change focused on one integration boundary.
Only run validation belonging to the component being changed.

---
title: Dark Factory Engineering Standards
description: Canonical technology, composability, deployment, and contribution standards for Tiger POC
---

## Purpose and status

These user-specified standards govern new Tiger POC work and assessment of functions
proposed for reuse. Read them with the [core idea](core-idea.md) and
[MVP design](mvp-design.md). They define the engineering direction, not a claim
that the technologies or integrations have been implemented.

The repository includes design documentation, HVE Core tooling and an RTSP
detector with a [shared vision container baseline](../apps/detect/container/README.md).
That baseline packages Python, OpenCV and Ultralytics YOLO in one service.
A future brain runs separately; no brain or platform integration is implemented.
The separate [Tiger Camera app](../apps/tiger-camera/README.md) is an approved
Kotlin exception for the Android source. Live RTSP into the vision container and
local detections with verified YOLO26 Nano weights have been exercised.
ONVIF discovery, generic observation mapping and platform integration remain
separate scoped work. See the [development handoff](development-status.md) for
capability limits and upstream design changes awaiting integration.

## Technology standards

| Area                 | Standard                                                     |
|----------------------|--------------------------------------------------------------|
| Languages            | Python                                                       |
| Vision frameworks    | OpenCV; YOLO                                                 |
| Video inputs         | RTSP; ONVIF discovery                                        |
| Packaging            | Docker containers                                            |
| Deployment target    | Azure Local; Arc-enabled Kubernetes; Foundry Local            |
| Data platform        | Azure IoT Operations; Azure IoT Hub; Microsoft Fabric         |
| AI platform          | Azure AI Foundry; Foundry Local; OpenAI models when applicable |
| Development workflow | GitHub repository; Fork + Pull Request model                  |
| Deployment workflow  | Infrastructure as Code; manifest-driven deployments           |

Foundry Local appears in both deployment and AI standards intentionally: it is
the local inference runtime/platform choice, not a replacement for infrastructure
or orchestration. Microsoft distinguishes
[Foundry Local](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local)
from [Foundry Local on Azure Local](https://learn.microsoft.com/azure/azure-sovereign-clouds/private/foundry-local/what-is-foundry-local-on-azure-local).
Assess the appropriate runtime, model support, and deployment prerequisites for
each selected component; this technology list does not establish that every
YOLO or OpenAI model runs on every target.

The data-platform standards do not select the existing digital-twin platform.
Keep its API isolated behind the digital-twin connector.

## Composable solutions

All solutions must be composable. Everything must be deployable through reusable,
manifest-driven components.

| Stage      | Component responsibilities       |
|------------|----------------------------------|
| Inputs     | Cameras; sensors; telemetry       |
| Processing | AI inference; rules; agents      |
| Outputs    | Telemetry; actions; Fabric analytics |

Preserve the capture adapter, inference adapter, observation contract, ontology/event
mapper, and digital-twin connector boundaries. Components communicate through
explicit contracts, not another component's internal implementation. Changing an
input, model, inference runtime, or rule must not require changing the common
event contract or rewriting an unrelated connector.

Sensors, telemetry, agents, actions, and Fabric analytics describe the wider
composition model; they do not expand the first MVP beyond its selected
line/process-monitoring scenario. An action output does not authorize physical
actuation or reuse of rover motor commands.

Keep a prerecorded input, deterministic workload, and local sink available for
repeatable development when a model, live camera, or destination is unavailable.
Those substitutes must exercise the same contracts as the intended integrations.
Composable boundaries do not require a separate service for every component.

## Reusable manifest contracts

For each future component, document its purpose and public input/output contracts.
Its reusable deployment manifest must declare component identity and version,
Docker image, configuration, dependencies and connections, runtime/resource
requirements, and the references needed for its deployment target.
Reference secrets through the selected platform's secret mechanism rather than
embedding credentials in manifests.

Use Infrastructure as Code for infrastructure and manifests for repeatable
component deployment. Separate reusable component definitions from
environment-specific values. Assemble or replace components through their
declared configuration and contracts rather than editing another component's code.
Define and assess the exact manifest schema during scoped design work; this
document does not introduce an executable schema or deployment.

## Contribution and migration direction

Use a GitHub Fork + Pull Request model, even when a contributor has upstream WRITE
access. Follow HVE Core Research, Plan, Implement, Review for scoped changes.
Creating a fork, publishing a branch, and deploying infrastructure remain separate
actions requiring authorization.

Use [hve-copilot-rover](https://github.com/lovelacer74/hve-copilot-rover) as a source
of reusable functionality, not an architecture to clone wholesale. Assess
orchestration, provider, configuration, and telemetry logic for selective reuse;
these are candidates, not confirmed reusable modules.

Replace or adapt Rover's existing vision implementations in favor of Tiger's
Python, OpenCV, YOLO, RTSP, and ONVIF discovery standards. Decouple detection and
inference from rover-specific motion, clearance, and person-approach semantics.
Map approved functionality to factory observations and the declared outputs.
Do not import hardware setup, motor control, personal identity data, credentials,
or Rover runtime agents into the factory pipeline.

Confirm each module's scope, public behavior, dependencies, license, and relevant
tests before porting it. Preserve the source repository unchanged. This migration
direction does not select the first module or authorize bulk copying.

See [Contributing to Tiger POC](../CONTRIBUTING.md) for workflow setup.

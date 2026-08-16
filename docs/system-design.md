---
title: Edge Computer Vision on Foundry Local and Azure Local
description: Reference architecture for running computer vision inference at the edge using Foundry Local on Azure Local with Azure Arc management
author: Tiger PoC
ms.date: 2026-08-14
ms.topic: concept
keywords:
  - azure local
  - foundry local
  - computer vision
  - edge inference
  - azure arc
estimated_reading_time: 6
---

## Architecture Diagram: Edge Computer Vision Architecture

```text
+=============================================================================+
|  Azure Cloud - Control, Model Supply & Analytics Plane                      |
|                                                                             |
|     +-----------------+     +-----------------+     +-----------------+     |
|     |    Azure Arc    |     | Foundry         |     | Container Reg.  |     |
|     +-----------------+     +-----------------+     +-----------------+     |
|                                                                             |
|     +-----------------+     +-----------------+     +-----------------+     |
|     |    Key Vault    |     |  Azure Monitor  |     |  Blob Storage   |     |
|     +-----------------+     +-----------------+     +-----------------+     |
|                                                                             |
|     +-----------------+     +-----------------+     +-----------------+     |
|     |   Event Hubs    |     | IoT Operations  |     |   Fabric / BI   |     |
|     +-----------------+     +-----------------+     +-----------------+     |
|                                                                             |
+=============================================================================+
                         ^                          |
         AIO dataflows:  |                          |   models, containers,
         events, clips   |                          v   policy, secrets
+=============================================================================+
|  Azure Local (Arc-enabled) - Edge Inference Plane                           |
|                                                                             |
|  :--- AKS enabled by Azure Arc ----------------------------------------:    |
|  :                                                                     :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :   |  Camera / RTSP  |-->|  Frame Grabber  |-->|  Pre-Processor  |   :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :                                                        |            :    |
|  :                                                        v            :    |
|  :   +-------------------------------------------------------------+   :    |
|  :   | Foundry Local inference operator                              |   :    |
|  :   | ModelDeployment CRDs, model cache, auth, Gateway routes      |   :    |
|  :   +----------------------------+--------------------------------+   :    |
|  :                                |                                    :    |
|  :       +------------------------+------------------------+           :    |
|  :       v                        v                        v           :    |
|  :   +-----------+            +-----------+            +-----------+   :    |
|  :   | YOLO      |            | Florence-2|            | Phi-4-mm  |   :    |
|  :   | predictive|            | predictive|            | generative|   :    |
|  :   | deployment|            | deployment|            | deployment|   :    |
|  :   +-----------+            +-----------+            +-----------+   :    |
|  :       |                        |                        |           :    |
|  :       +------------------------+------------------------+           :    |
|  :                                |                                    :    |
|  :            v                                                        :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :   |  Inference API  |-->|   Event Rules   |-->|   Local Store   |   :    |
|  :   +-----------------+   +--------+--------+   +-----------------+   :    |
|  :                                  |                                  :    |
|  :                                  v                                  :    |
|  :                         +-----------------+   +-----------------+   :    |
|  :                         | AIO MQTT Broker |-->|  AIO Dataflows  |   :    |
|  :                         +-----------------+   +-----------------+   :    |
|  :---------------------------------------------------------------------:    |
|                                                                             |
|     +-----------------+     +-----------------+     +-----------------+     |
|     |    Arc Agent    |     | Azure Local HCI |     |  S2D / Storage  |     |
|     +-----------------+     +-----------------+     +-----------------+     |
|                                                                             |
+=============================================================================+
```

### Legend

| Symbol  | Meaning                                                    |
|---------|------------------------------------------------------------|
| `-->`   | Data flow or dependency between components                 |
| `\|`    | Vertical data flow between tiers                           |
| `^` `v` | Direction of flow across the cloud and edge boundary       |
| `====`  | Primary boundary (cloud subscription, Azure Local cluster) |
| `:---:` | Secondary boundary (Kubernetes cluster on the edge)        |

### Key Relationships

* Cameras stream RTSP into the frame grabber, which samples frames and hands them to the pre-processor for resize, normalization, and batching.
* The pre-processor and inference API resolve each model to its own Foundry Local `ModelDeployment` endpoint. YOLO and Florence-2 use `/v1/predict`; Phi-4-multimodal uses `/v1/chat/completions`.
* Each `ModelDeployment` owns one model, its Deployment, Service, API key Secret, and optional Gateway route. Multiple models run concurrently as independent deployments rather than in one shared runtime process.
* The operator schedules each deployment against its requested compute and resource limits, selecting an appropriate ONNX Runtime execution provider for the target hardware.
* The inference API applies event rules (confidence thresholds, dwell time, zone entry) and writes only detections and short clips to local storage backed by Storage Spaces Direct.
* Event rules publish detections to the Azure IoT Operations MQTT broker running on the cluster. The broker is the single integration point at the edge, so downstream consumers subscribe to topics rather than calling the pipeline directly.
* Azure IoT Operations dataflows handle north-bound delivery, applying transformation and filtering before forwarding to Event Hubs and Blob Storage.
* The Arc agent registers the cluster with Azure Arc, which delivers GitOps configuration, container images from Azure Container Registry, and secrets from Key Vault.
* Models are packaged in Azure AI Foundry, published to the container registry, and pulled to the edge on a scheduled or approval-gated rollout.
* Only aggregated detections, metrics, and sampled clips flow upward through Azure IoT Operations dataflows to Event Hubs, Blob Storage, and Azure Monitor, keeping bandwidth predictable on constrained links.
* The solution continues to run during cloud disconnection; the MQTT broker keeps serving local subscribers and dataflows buffer north-bound messages until connectivity returns.

### Scope

This architecture describes the computer vision pipeline, not a sizing for a particular workload. Azure Local hardware is right-sized during deployment planning once camera count, resolution, frame rate, and model mix are known. The pipeline stays portable across whatever sizing results:

* Models run through ONNX Runtime, so the execution provider, compute target, resource limits, and replicas are deployment settings rather than code changes.
* Frame rate, batch size, and deployment selection are configuration, allowing the same pipeline to scale from a single camera to a dense multi-node cluster.
* Scale-out happens by adding nodes to the Azure Local cluster and letting Kubernetes schedule additional inference pods, not by rewriting the pipeline.

### Edge Messaging

Azure IoT Operations provides the MQTT broker and the north-bound dataflows. This is the agreed integration point for the edge.

* The broker speaks MQTT v5 and runs as a highly available service on the cluster, so it survives node loss without dropping subscribers.
* Event rules publish to a structured topic hierarchy such as `cv/{site}/{camera}/detections`, letting consumers subscribe by site or camera without filtering client-side.
* Detection payloads carry the model identifier and bundle digest, so downstream consumers can attribute results to a specific model version.
* Dataflows own transformation, filtering, and delivery to Event Hubs and Blob Storage, keeping cloud endpoint knowledge out of the pipeline code.
* Local subscribers such as HMI panels, PLC bridges, or alerting services attach to the same broker and continue to function while disconnected from Azure.

## Local Development Environment

Development and testing run on a workstation with an NVIDIA RTX 5070. The same container image, model files, and API contract used at the edge run locally, so only the execution provider and orchestration layer differ.

```text
+=============================================================================+
|  Local Dev Workstation - NVIDIA RTX 5070 (Blackwell, 12 GB)                 |
|                                                                             |
|  :--- WSL2 / Linux + Docker (NVIDIA Container Toolkit) ----------------:    |
|  :                                                                     :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :   |  Sample Video   |-->|  Frame Grabber  |-->|  Pre-Processor  |   :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :                                                        |            :    |
|  :                                                        v            :    |
|  :   +-------------------------------------------------------------+   :    |
|  :   | Foundry Local-on-Azure-Local contract mock                  |   :    |
|  :   | ModelDeployment status, per-deployment API keys and routes  |   :    |
|  :   +----------------------------+--------------------------------+   :    |
|  :                                |                                    :    |
|  :       +------------------------+------------------------+           :    |
|  :       v                        v                        v           :    |
|  :   +-----------+            +-----------+            +-----------+   :    |
|  :   | YOLO      |            | Florence-2|            | Phi-4-mm  |   :    |
|  :   | /v1/predict            | /v1/predict            | /v1/chat  |   :    |
|  :   +-----------+            +-----------+            +-----------+   :    |
|  :       |                        |                        |           :    |
|  :       +------------------------+------------------------+           :    |
|  :                                |                                    :    |
|  :            v                                                        :    |
|  :   +-----------------+   +-----------------+   +-----------------+   :    |
|  :   |  Inference API  |-->|   Event Rules   |-->|   Local Store   |   :    |
|  :   +-----------------+   +--------+--------+   +-----------------+   :    |
|  :                                  |                                  :    |
|  :                                  v                                  :    |
|  :                         +-----------------+   +-----------------+   :    |
|  :                         | Mosquitto MQTT  |-->|  Dataflow Stub  |   :    |
|  :                         +-----------------+   +-----------------+   :    |
|  :---------------------------------------------------------------------:    |
|                                                                             |
|     +-----------------+     +-----------------+     +-----------------+     |
|     |  Dev Container  |     | kind / k3d k8s  |     | Local Registry  |     |
|     +-----------------+     +-----------------+     +-----------------+     |
|                                                                             |
+=============================================================================+
                                     |
                                     v  promote image + model bundle
                          Azure Container Registry --> Azure Local
```

### Dev and Edge Parity

| Layer              | Local dev (RTX 5070)                 | Edge (Azure Local)                    |
|--------------------|--------------------------------------|---------------------------------------|
| Deployment contract| Docker Compose mock, one service/model| `ModelDeployment`, one deployment/model|
| Accelerator        | RTX 5070, full GPU                   | Right-sized per deployment            |
| Execution provider | CUDA 12.8 EP, TensorRT 10.9          | CUDA, OpenVINO, or DirectML           |
| Endpoint and auth  | Per-service path and development key  | Per-deployment route and API key Secret|
| Orchestration      | Docker Compose or kind                | AKS enabled by Azure Arc              |
| Image source       | Local registry                        | Azure Container Registry              |
| Secrets            | `.env` or user secrets                | Key Vault delivered via Arc           |
| Telemetry          | Console or local OTLP                 | Azure Monitor and Event Hubs          |
| Messaging          | Mosquitto broker container            | Azure IoT Operations broker           |
| Video source       | Recorded MP4 or RTSP simulator        | Live camera RTSP streams              |

### RTX 5070 Requirements

The RTX 5070 is Blackwell-generation with compute capability `sm_120`, which older CUDA toolchains do not target. Plan for the following:

* NVIDIA driver 570 or later, with CUDA 12.8 or later. Builds compiled only for `sm_89` and below fall back to JIT or fail outright.
* ONNX Runtime GPU package built against CUDA 12.8. Pin the version explicitly rather than relying on the default wheel.
* TensorRT 10.9 or later if the TensorRT execution provider is used for the detection models.
* NVIDIA Container Toolkit installed in WSL2 so containers see the GPU through `--gpus all`.
* 12 GB of VRAM is the working budget. Treat YOLO, Florence-2, and Phi-4-multimodal as separately scheduled deployments. Resource limits, node selection, and deployment order prevent their combined working sets from overcommitting the GPU.

### Keeping Parity

* Model the `ModelDeployment` lifecycle locally, including one model reference, readiness state, deployment-specific endpoint, and independent credential for each service.
* Run one generic model service implementation instantiated once per model, with the model bundle, workload type, endpoint, credential, and resource limits supplied as configuration. Adding a model is a catalog entry rather than a new service.
* Use the CRD's own field names and states locally: `workloadType`, `compute`, `runtime`, `replicas`, `port`, `resources.requests`, `resources.limits.gpu`, and the `Pending`, `Creating`, `Running`, `Updating`, `Error`, `Terminating` state machine.
* Group models by workload contract rather than by model identity: predictive models share `/v1/predict` semantics and generative models share `/v1/chat/completions` semantics, so routing and payload validation stay model-agnostic.
* Select the execution provider through deployment configuration, not code, so the same model service runs with CUDA locally and the host-appropriate provider at the edge.
* Version model files as an immutable bundle and reference the same bundle digest in both environments.
* Run the event rules and inference client against recorded video in CI, including predictive and generative endpoint contract tests, so routing behavior is validated before promotion.
* Treat throughput numbers from the RTX 5070 as a development reference point. Capacity planning for a given deployment happens separately, once the workload is defined.

<!-- markdownlint-disable-file -->
<!-- markdown-table-prettify-ignore-start -->
# Discovery Issue Analysis - Modular Pipeline Framework

* **Artifact(s)**: docs/pipeline-framework.md
* **Repository**: dkirby-ms/tiger-poc
* **Milestone**: Not assigned

## Review Findings

* The architecture is a credible phased migration, but the current checkout contains only `apps/local_model_runtime`; the documented `apps/vision-pipeline`, `k8s`, `data`, and several docs referenced by `README.md` are absent. Repository-layout alignment needs an explicit maintenance issue before contributors can follow the documented workflow.
* The proposed five core types are underspecified at important boundaries. Fan-in input alignment, source and sink cancellation, stage failure policy, and the meaning of `scope: pipeline` need normative contracts before third-party stages can interoperate.
* Remote channels need explicit delivery semantics. HTTP and MQTT behavior for retries, duplicate envelopes, ordering, authentication, serialization limits, and idempotent sinks is not defined, so "location transparency" is currently an aspiration rather than a testable contract.
* The Foundry payload, authentication, endpoint, and CRD claims are presented as corrections but are not represented by an external contract fixture in the repository. Phase 0 should capture evidence and Phase 3 should make the adapter change only behind recorded tests.
* `requirements.txt` currently contains only ONNX Runtime, NumPy, and Pillow. The proposed pydantic, PyAV, FastAPI, Prometheus, and OpenTelemetry stack needs a dependency and packaging decision rather than being assumed.
* The existing runtime exposes the exact seams named by the design: `workload_adapters.py`, `foundry_contract.py`, `deployment_registry.py`, `gateway.py`, and `http_service.py`. Existing tests assert the current single-image predictive payload and legacy auth behavior, so the contract migration must be deliberately versioned or updated with a compatibility decision.

## Planned Issues

### IS001 - Create - Build the next-generation video analysis platform

* **Working Title**: `feat(pipeline): build the next-generation video analysis platform`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Track the phased move from the current prototype to a flexible video analysis platform. Teams will be able to assemble video workflows from reusable building blocks, connect them to the right AI models, and run them locally or across services.

#### IS001 - Related and Discovered Information

* **Related Requirements from docs/pipeline-framework.md**
  * Target architecture, design goals, stage catalog, Foundry integration, migration phases 0-6, and testing strategy.
* **Related Codebase Items**
  * `apps/local_model_runtime/`
  * `tests/`

### IS002 - Create - Protect today's working behavior

* **Working Title**: `test(runtime): protect today's working behavior`
* **Working Labels**: maintenance
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Record how the current model services behave before the migration begins. This gives the team a reliable way to tell whether new work changes routing, security, readiness, request validation, or detection results unexpectedly.

#### IS002 - Related and Discovered Information

* **Related Requirements**: Phase 0 and Testing strategy in `docs/pipeline-framework.md`.
* **Related Codebase Items**: `apps/local_model_runtime/gateway.py`, `http_service.py`, `workload_adapters.py`, `tests/test_gateway.py`, `tests/test_model_service_http.py`, `tests/test_workload_adapters.py`.

### IS003 - Create - Make model delivery repeatable

* **Working Title**: `feat(models): make model delivery repeatable`
* **Working Labels**: feature, infrastructure
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Create a repeatable way to package, publish, retrieve, and verify AI models. Local development should continue to work while the same process prepares models for a registry-based environment.

#### IS003 - Related and Discovered Information

* **Related Requirements**: Phase 0 model packaging and Phase 4 model sourcing.
* **Related Codebase Items**: `apps/local_model_runtime/bundle_registry.py`, `models/bundle.json`, `scripts/fetch-model-bundle.sh`.

### IS004 - Create - Prepare a local environment for future model integration

* **Working Title**: `chore(infrastructure): prepare a local environment for future model integration`
* **Working Labels**: maintenance, infrastructure
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Prepare the parts of a local test environment that can be built before access to the preview model platform is available. The setup should be repeatable and should clearly report when it is ready for the remaining integration step.

#### IS004 - Related and Discovered Information

* **Related Requirements**: Phase 0 local development fidelity ladder and exit criteria.
* **Review Constraint**: Foundry operator artifacts require preview onboarding and must not be treated as available in this issue.

### IS005 - Create - Define the building blocks for video workflows

* **Working Title**: `feat(core): define reusable video workflow building blocks`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Define the common building blocks that every video workflow component will use. A new camera source, processing step, AI step, or destination should be able to plug in without changing the framework.

#### IS005 - Related and Discovered Information

* **Related Requirements**: Core abstractions and Phase 1.
* **Review Constraint**: Specify source, sink, fan-out, failure, cancellation, and `scope: pipeline` semantics before publishing the protocol.

### IS006 - Create - Run workflows from a configuration file

* **Working Title**: `feat(core): run video workflows from configuration`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Let teams describe a video workflow in a configuration file and run it without assembling the workflow in Python. The system should catch setup mistakes before starting and provide a small local example from video file to saved results.

#### IS006 - Related and Discovered Information

* **Related Requirements**: Pipeline manifest, registry, streams, and Phase 1.
* **Review Constraint**: Define fan-in alignment and unreachable-stage diagnostics as loader behavior, not implementation detail.

### IS007 - Create - Deliver the first complete video workflow

* **Working Title**: `feat(video): deliver the first complete video workflow`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Connect real video inputs to preprocessing, AI detection, and saved events. The first supported workflow should work with a recorded clip and provide a clear path to live camera streams.

#### IS007 - Related and Discovered Information

* **Related Requirements**: Stage catalog and Phase 2.
* **Related Codebase Items**: `apps/local_model_runtime/yolo_inference.py`, `workload_adapters.py`.
* **Review Constraint**: Resolve PyAV dependency, timestamp behavior, reconnect policy, and frame serialization format before RTSP is considered complete.

### IS008 - Create - Connect workflows to the right AI model

* **Working Title**: `feat(foundry): connect workflows to the right AI model`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Make workflow steps request a model by name instead of depending on a hard-coded address. The system should wait for the model to be ready, warm it before use, and report model health without bringing down the whole workflow.

#### IS008 - Related and Discovered Information

* **Related Requirements**: Foundry Local integration and Phase 3.
* **Related Codebase Items**: `apps/local_model_runtime/foundry_contract.py`, `deployment_registry.py`, `model_service.py`.

### IS009 - Create - Align model requests with the target platform

* **Working Title**: `fix(foundry): align model requests with the target platform`
* **Working Labels**: bug, breaking-change
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Update model requests and service endpoints so they match the target Foundry platform. Preserve the right security model for each type of AI request, support small batches of images, and make the service easier to test and operate.

#### IS009 - Related and Discovered Information

* **Related Requirements**: Corrections required and Phase 3.
* **Related Codebase Items**: `apps/local_model_runtime/workload_adapters.py`, `http_service.py`, `gateway.py`, `tests/test_foundry_local_deployment_contracts.py`.
* **Review Constraint**: Record operator request/response fixtures and a compatibility/versioning decision before changing existing tests.

### IS010 - Create - Run against the shared model platform

* **Working Title**: `feat(foundry): run against the shared model platform`
* **Working Labels**: feature, infrastructure
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Connect the local workflow framework to the shared Kubernetes-based model platform. The same workflow should work with local development services or the platform-managed model deployments once preview access is available.

#### IS010 - Related and Discovered Information

* **Related Requirements**: Phase 4 and local development fidelity tiers 2-3.
* **Review Constraint**: Validate CRD schema, API version, secret shape, RBAC, and preview availability before locking the implementation.

### IS011 - Create - Turn detections into useful events

* **Working Title**: `feat(events): turn detections into useful events`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Add the business logic and outputs that make detections useful: identify ongoing activity, apply thresholds and dwell rules, save clips and event records, publish notifications, and manage limited storage safely.

#### IS011 - Related and Discovered Information

* **Related Requirements**: Stage catalog, retention, and Phase 5.
* **Review Constraint**: Define event identity, clip consistency, retry behavior, and sink idempotency before enabling remote sinks.

### IS012 - Create - Make workflow health visible

* **Working Title**: `feat(observability): make workflow health visible`
* **Working Labels**: feature
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Give operators a clear view of workflow health and performance, including slow steps, backed-up queues, dropped video, model health, and the path of an event through the system.

#### IS012 - Related and Discovered Information

* **Related Requirements**: Observability by construction, StageHealth, ChannelStats, and testing strategy.
* **Review Constraint**: Define metric cardinality limits because stream and edge labels can become unbounded.

### IS013 - Create - Run workflows across multiple services

* **Working Title**: `feat(topology): run workflows across multiple services`
* **Working Labels**: feature, infrastructure
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Allow one workflow to run in a single process during development or across multiple services in deployment. Camera streams should be distributed predictably, and the results should remain consistent between the two arrangements.

#### IS013 - Related and Discovered Information

* **Related Requirements**: Service topology, deployment profiles, Phase 6, and channel implementations.
* **Review Constraint**: Specify retry, duplicate delivery, ordering, authentication, payload size, and idempotent processing semantics before implementing remote transport.

### IS014 - Create - Make the project easier to set up and understand

* **Working Title**: `docs(repo): make setup and project structure clear`
* **Working Labels**: documentation, maintenance
* **Working Milestone**: Not assigned
* **Similarity**: Pending GitHub search; no existing issue was assessed in this session.
* **Working Description**: Bring the setup guide and project documentation in line with the code. A new contributor should be able to find the right files, install the required dependencies, and follow a working quick-start path.

#### IS014 - Related and Discovered Information

* **Related Requirements**: Repository layout, technology choices, and local development fidelity.
* **Related Codebase Items**: `README.md`, `requirements.txt`, `docker-compose.yml`, `docs/pipeline-framework.md`.

## Similarity Search Status

No GitHub issue search was performed because the available session tools do not expose GitHub read APIs. All candidates are therefore provisional `Create` actions with similarity marked `Pending`; duplicate detection must run before execution.
<!-- markdown-table-prettify-ignore-end -->

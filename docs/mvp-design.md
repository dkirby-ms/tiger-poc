---
title: Portable Factory Perception MVP
description: A focused design for composing factory video workloads and connecting their outputs to an existing digital-twin platform.
---

## Summary

Build a small Azure-aligned accelerator that lets a demo or evaluation team assemble one factory video workload from reusable perception components and publish its results to an existing digital-twin platform.

The MVP focuses on one line or process-monitoring scenario. The same workload should be runnable with local inference on Foundry Local on Azure Local and with cloud inference through Foundry, with the integration contract staying stable.

This is a technical hypothesis, not yet a user-validated product requirement. The MVP should therefore optimize for learning and demonstrability over production completeness.

## User And Problem

The primary user is a demo or evaluation team preparing repeatable factory scenarios. Today, changing a model, camera input, or process rule can require rewriting the surrounding integration. That makes demonstrations slow to prepare and makes it difficult to compare edge and cloud execution.

The MVP tests whether a stable event contract and a small set of composable adapters reduce that friction.

## Hypothesis

If perception workloads expose a common, ontology-aware event contract, then a team can swap or recombine the camera adapter, inference provider, and process rule without changing the digital-twin integration.

The hypothesis is supported when the team can create a second variation of the initial scenario by changing one or more perception components while keeping the twin connector unchanged.

## MVP Scope

### In scope

* One camera or prerecorded video source
* One line or process-monitoring scenario
* A replaceable perception step that produces observations
* A small ontology for the selected scenario, such as `Line`, `Station`, `Product`, `ProcessState`, and `Observation`
* A rule or mapping step that turns observations into process events
* Two inference modes: Foundry Local on Azure Local and Foundry in the cloud
* One connector to an existing digital-twin platform, using a documented adapter boundary
* A simple configuration file for selecting the source, inference mode, ontology mappings, and destination
* Basic logs and a repeatable demo path

### Out of scope

* Production-grade fleet management
* Multi-camera synchronization
* Model training or model lifecycle management
* A new digital-twin platform
* A complete ontology for manufacturing
* High availability, autoscaling, or security certification
* Broad support for every factory use case
* A polished end-user application

## Proposed Design

```text
Video source
    |
    v
Capture adapter
    |
    v
Perception workload
(Foundry Local or Foundry)
    |
    v
Observation contract
    |
    v
Ontology and event mapper
    |
    v
Digital-twin connector
    |
    v
Existing digital-twin platform
```

Each block should have a narrow interface. The MVP can implement the interfaces in one repository and one deployable process; separate services are not required.

### Capture adapter

Reads a camera stream or prerecorded clip and emits timestamped frames. The adapter hides the input details from the perception workload.

### Perception workload

Consumes frames and emits observations. An observation should include at least:

* `subjectId`
* `observationType`
* `value`
* `timestamp`
* `confidence`
* `source`

The workload may use a simple existing model or mocked inference for the first demonstration. The interface matters more than model sophistication.

### Ontology and event mapper

Maps observations to a small, scenario-specific vocabulary and emits process events. Keep the ontology narrow enough to understand and inspect during a demo. Do not attempt to model the whole factory.

Example event:

```json
{
  "eventType": "ProcessStateChanged",
  "subjectId": "station-01",
  "state": "blocked",
  "timestamp": "2026-08-18T12:00:00Z",
  "confidence": 0.91,
  "source": "foundry-local"
}
```

### Digital-twin connector

Translates the common process event into the API or message format expected by the existing twin platform. This is the only component that should know the target platform's details.

For the MVP, the connector can target one platform and one event path. A local sink or recorded payload should be available when the real platform is not accessible.

### Configuration

Use one human-readable configuration file to select the runtime and mappings:

```yaml
source: sample-line-video
inference: foundry-local
ontology: line-monitoring-v1
destination: existing-twin
```

The exact file format can follow the repository's implementation language and tooling. Avoid building a separate configuration service.

## Runtime Modes

The same pipeline and event contract should support two modes:

* Edge mode runs inference through Foundry Local on Azure Local and publishes events from the local environment.
* Cloud mode runs inference through Foundry and publishes events through the same mapper and connector boundary.

The MVP does not need identical model outputs in both modes. It does need comparable event shapes and an explicit indication of which runtime produced each observation.

## Demo Flow

1. Start the pipeline against a prerecorded line-monitoring clip.
2. Select edge inference in the configuration.
3. Show observations and mapped process events.
4. Verify that the existing digital-twin platform receives the event.
5. Change the inference mode or swap one perception component.
6. Run the same clip again without changing the twin connector.
7. Compare the emitted event shape and basic latency or throughput measurements.

## Success Criteria

The MVP is successful when all of the following are true:

* The team can run one line-monitoring scenario from a documented command or script.
* The edge and cloud modes produce the same event contract.
* The digital-twin connector is unchanged when the inference mode is changed.
* A second scenario variation can be created by changing configuration or replacing one component, without rewriting the connector.
* A new team member can understand and run the demo from the repository documentation.
* The team records enough timing and output information to compare the two runtime modes.

Suggested initial targets:

* Assemble the first scenario in one working day after the base pipeline exists.
* Create the second variation in less than half a day.
* Keep the demo path under five minutes from startup to a visible twin event.

These targets are working assumptions and should be revised after the first user walkthrough.

## Validation Plan

The first validation should be a short internal or partner walkthrough with the people who prepare factory demonstrations.

Ask them to:

* Assemble the initial scenario from the documentation.
* Change the inference mode.
* Replace or adjust one perception component.
* Explain which parts they expect to reuse for another factory scenario.

Measure setup time, changes required, failures encountered, and whether the resulting event is understandable in the twin platform. If the team still needs to edit the connector for common variations, the contract or component boundary is not yet useful.

## Risks And Decisions

* The existing digital-twin platform and its event API are not specified yet. The first implementation should isolate this uncertainty behind a connector interface and confirm the target API early.
* Foundry Local and Foundry may expose different model capabilities or operational constraints. Treat runtime selection as an adapter boundary and test one representative model path in each mode.
* Ontology work can expand indefinitely. Limit the first vocabulary to the selected process scenario and document what is intentionally missing.
* A prerecorded video can hide real camera and network problems. Use it for repeatability, then perform one live-camera smoke test before calling the MVP complete.
* The concept currently comes from a technical hypothesis rather than direct user research. Do not interpret the success criteria as proof of customer demand.

## Implementation Sequence

1. Define the observation and process-event contracts with sample payloads.
2. Build the prerecorded-video capture adapter and a deterministic sample workload.
3. Add the ontology mapper and a local event sink.
4. Add the existing digital-twin connector.
5. Add the edge and cloud inference adapters behind the same interface.
6. Document and rehearse the demo flow.
7. Run the validation walkthrough and record what should be changed before expanding scope.

## Open Questions

* Which existing digital-twin platform and event API will the MVP use?
* Which process state or event is most useful for the first line-monitoring demonstration?
* Is a real model required for the first demo, or is a deterministic workload sufficient to validate composition?
* What evidence would justify expanding from one scenario to multiple dark-factory use cases?

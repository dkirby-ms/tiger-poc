<!-- markdownlint-disable-file -->
# Epic 5 research

## Goal
Implement the inference API, event rules engine, and local detection storage needed by the local pipeline.

## Findings
* The repo currently includes frame grabber and pre-processor services but no inference or downstream filtering layer.
* The architecture expects a Foundry Local /v1-compatible endpoint and event-rule filtering before local persistence and MQTT publication.
* Existing tests validate preprocessing and frame sampling separately; there is no coverage for the Epic 5 normalization contract.

## Proposed implementation
1. Add an inference API module that normalizes Foundry Local responses into a common detection schema.
2. Add an event-rules module that filters raw detections by threshold, dwell time, and optional zone rules.
3. Add a local storage module that writes detections and clip metadata to disk with retention support.
4. Add targeted pytest coverage for each module before validation.

## Success criteria
* A mock Foundry response can be normalized into a detection list.
* Event rules suppress low-confidence or short-lived detections.
* Local storage writes detection JSON and optional clip metadata to a configured directory.

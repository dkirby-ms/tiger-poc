<!-- markdownlint-disable-file -->
# Epic 5 implementation plan

## User Requests
1. Implement the Inference API service that normalizes Foundry Local responses into a consistent internal detection schema.
2. Implement the Event Rules engine that filters on confidence, dwell time, and zone matching.
3. Implement local persistence for detections and clips with configurable storage and retention.

## Overview
The current pipeline stops at preprocessing. This work adds the missing inference and rule-evaluation layer needed for the rest of the backlog while preserving a simple local-only data model.

## Context Summary
* Source layout is under `apps/vision-pipeline/` with package-scoped modules.
* Relevant instructions are the Python script and pytest conventions in the repo extension instructions.
* Existing services are built with dataclasses, environment-based configuration, and simple HTTP or file-backed interfaces.

## Implementation Checklist
- [ ] Add failing tests for inference normalization, event rules, and local storage
- [ ] Implement inference API data model and normalization helpers
- [ ] Implement event-rules filtering logic
- [ ] Implement local detection store and retention behavior
- [ ] Update package metadata and run pytest validation

<!-- parallelizable: false -->

## Dependencies
* Python script instructions
* Python test instructions
* `frame_grabber` and `pre_processor` service patterns

## Success Criteria
* `pytest` passes for all new Epic 5 coverage.
* The modules are importable from the vision-pipeline package namespace.
* The code matches the local dev backlog expectations without requiring a full GPU runtime.

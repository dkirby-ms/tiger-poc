<!-- markdownlint-disable-file -->
# Implementation Plan: Issue 8 Foundry Local deployment contracts

## Overview

Implement the deployment contract validation for the three local Foundry deployments so the system proves one model per deployment, correct route usage, isolated credentials, payload semantic separation, and readiness gating before promotion.

## Objectives

### User Requirements

* Verify that the architecture defines three independent Foundry Local deployments with distinct routes and auth boundaries — Source: docs/system-design.md and .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md
* Validate that YOLO and Florence-2 use /v1/predict while Phi-4-multimodal uses /v1/chat/completions — Source: docs/system-design.md and the issue research note
* Add CI coverage for predictive and generative endpoint contract tests before promotion — Source: docs/system-design.md
* Record the enforcement mechanism for the contract gate and any workflow-level follow-up when no repo CI file currently exists — Source: plan validation findings

### Derived Objectives

* Build a deployment contract matrix that asserts model identity, route mapping, and unique secrets for each deployment — Derived from: route isolation and auth separation in the design
* Add contract tests for wrong-route, wrong-auth, and non-ready behavior so failure handling is isolated per deployment — Derived from: readiness and failure-related design requirements
* Keep the checks deterministic and local so they validate routing behavior without depending on a broad end-to-end runtime — Derived from: local dev parity and CI gate guidance

## Context Summary

### Project Files

* docs/system-design.md - Defines the edge deployment pattern, the three model families, and the per-deployment route and secret model
* README.md - Describes the local development scaffold and the expectation that Foundry-compatible checks run in CI
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md - Captures the issue-specific contract findings and the recommended test matrix

### References

* docs/system-design.md - Local development parity and deployment lifecycle notes
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md - Verified contract requirements and test recommendations

### Standards References

* No repository instruction file directly governs this issue beyond the project design and the research artifact.

## Implementation Checklist

### [x] Implementation Phase 1: Establish the deployment contract fixtures

<!-- parallelizable: true -->

* [x] Step 1.1: Define the three deployment identities and expected contracts
  * Details: .copilot-tracking/details/2026-08-14/issue-8-foundry-local-deployment-contracts-details.md (Lines 1-34)
* [x] Step 1.2: Add the local contract fixture or runtime data for YOLO, Florence-2, and Phi-4-multimodal
  * Details: .copilot-tracking/details/2026-08-14/issue-8-foundry-local-deployment-contracts-details.md (Lines 35-72)
* [x] Step 1.3: Validate phase changes
  * Run the smallest relevant tests for the fixture and manifest updates
  * Skip broad project validation when parallel phases share the same scope

### [x] Implementation Phase 2: Add the contract assertion suite

<!-- parallelizable: true -->

* [x] Step 2.1: Implement route and payload contract assertions for predictive vs generative endpoints
  * Details: .copilot-tracking/details/2026-08-14/issue-8-foundry-local-deployment-contracts-details.md (Lines 73-126)
* [x] Step 2.2: Add auth separation, readiness, and non-ready failure gate tests
  * Details: .copilot-tracking/details/2026-08-14/issue-8-foundry-local-deployment-contracts-details.md (Lines 127-172)
* [x] Step 2.3: Validate phase changes
  * Run the contract suite for the modified deployment assertions
  * Ensure failures are isolated and actionable

### [x] Implementation Phase 3: Validation

<!-- parallelizable: false -->

* [x] Step 3.1: Run the relevant project validation commands
  * Execute the contract test suite and any direct lint or test commands covering the modified area
  * Treat the repo's standard pytest contract command as the local gate for issue 8 until a dedicated workflow entry is added
* [x] Step 3.2: Fix minor validation issues
  * Iterate on mismatched payload expectations, route assertions, or fixture data issues when they are small and isolated
* [x] Step 3.3: Report blocking issues
  * Document any remaining gap that requires follow-on research or a larger implementation change
  * If the repo adds a CI workflow later, bind the same contract suite to that workflow before promotion
  * Avoid widening scope past the issue-8 contract suite

## Planning Log

See .copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md for discrepancy tracking, implementation paths considered, and follow-on work.

## Dependencies

* pytest or the repo's existing Python test runner
* local Foundry-compatible runtime or deterministic mock contract stack
* model bundle metadata and route expectations from the design docs

## Success Criteria

* The test suite proves one model per deployment and the route-specific contract for each service — Traces to: docs/system-design.md and issue research
* The suite rejects wrong-path and wrong-auth requests without falling back to another deployment — Traces to: issue research and design assumptions
* The suite enforces readiness gating and per-deployment failure isolation in CI or the repo's standard local validation gate — Traces to: local parity requirements and issue research
* The enforcement path is explicitly recorded even when the repo does not yet have a dedicated workflow file for the contract gate — Traces to: plan validation follow-up

---
title: Issue 8 Phase 1 Validation
description: RPI validation of Phase 1 for the Foundry Local deployment contract fixtures against the implementation, issue plan, and research artifacts.
author: Tiger PoC
ms.date: 2026-08-14
ms.topic: reference
keywords:
  - issue 8
  - validation
  - foundry local
  - deployment contract
  - rpi
estimated_reading_time: 5
---

## Executive Summary

Status: Partial

Phase 1 is implemented and validated for the fixture layer: the runtime defines the three deployment identities, unique secrets, and the required route split between predictive and generative contracts, and the test suite proves the contract boundaries. The remaining gap is repository-level enforcement: the plan and issue research call for CI coverage, but no workflow file currently binds the contract suite, so the validation gate remains the local pytest command instead of a tracked repo workflow.

## Scope and Evidence Reviewed

* Plan: [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md)
* Research: [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md)
* Change log: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md)
* Design: [docs/system-design.md](docs/system-design.md)
* Runtime fixture: [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py)
* Contract tests: [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py)

## Validation Against Phase 1 Requirements

### Required plan item: three deployment identities and expected contracts

Evidence confirms the runtime establishes exactly three deployments and preserves per-deployment model identity, route, secret, and readiness state:

* [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L5-L15) defines the `DeploymentContract` record and initializes three contracts: `yolo`, `florence-2`, and `phi-4-multimodal`.
* [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L17-L30) sets the per-model routes and secrets with `yolo` and `florence-2` on `/v1/predict` and `phi-4-multimodal` on `/v1/chat/completions`.
* [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L6-L22) asserts the deployment count, model identities, route split, and unique secret set.

The requirement is met and matches the design statement that the system is a three-deployment model and not a shared runtime process: [docs/system-design.md](docs/system-design.md#L84-L93) and [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L22-L55).

### Required plan item: route isolation and payload semantics

Evidence confirms route-specific dispatch and predictive-versus-generative payload validation:

* [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L32-L47) enforces route matching and payload semantics by checking `image` for `/v1/predict` and `messages` for `/v1/chat/completions`.
* [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L24-L45) asserts predictive success for YOLO and generative success for Phi-4, and rejects the mismatched payload shape.
* [docs/system-design.md](docs/system-design.md#L88-L97) states the route split: YOLO and Florence-2 use `/v1/predict`; Phi-4-multimodal uses `/v1/chat/completions`.

This matches the research requirement to validate predictive and generative endpoint contracts before promotion: [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L58-L121).

### Required plan item: auth separation and readiness gating

Evidence confirms unique secrets and non-ready rejection without fallback:

* [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L49-L72) rejects unauthorized requests and returns `not_ready` when a deployment is marked unavailable.
* [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L47-L70) verifies wrong-secret rejection, wrong-route rejection, and readiness gating after `set_ready("yolo", False)`.
* The design and research explicitly require isolated credentials and readiness states for each deployment: [docs/system-design.md](docs/system-design.md#L171-L200) and [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L122-L179).

## Findings

### Pass: Phase 1 fixture requirements are implemented as designed

Severity: None (pass)

* The fixture creates the required three deployment identities with distinct routes and credentials.
* The harness enforces predictive versus generative payload behavior.
* Ready-state toggles and wrong-secret/wrong-route rejection are implemented and asserted.

Evidence:

* [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L5-L72)
* [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L6-L70)

### Major: The repo does not yet enforce the issue-8 contract suite in CI

Severity: Major

The plan requires CI coverage before promotion and the issue log calls out the fact that the repo does not yet include a dedicated workflow for routing enforcement. The implementation satisfies the local validation gate, but not the repo-level enforcement gate described in the plan.

Evidence:

* The plan states the expected CI gate: [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L6-L36)
* The change log records the gap: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L24-L30)
* The local test suite is the current gate: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L34-L35)

This is a requirement gap, not a contract logic defect. The contract logic is present and valid, but the repo-level workflow step remains a follow-on action.

### Minor: The issue is validated against the local deterministic harness rather than a full Foundry Local integration stack

Severity: Minor

The implementation is intentionally deterministic and local by design, which matches the plan's scoping requirement. However, it does not yet exercise a full runtime deployment stack with actual Foundry Local endpoints or gateway wiring.

Evidence:

* The plan explicitly scopes to a deterministic local contract harness: [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L15-L25)
* The runtime file is a local deterministic mock: [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L1-L72)

This is acceptable for Phase 1 but should be considered a follow-on validation when a repo workflow or integration stack is available.

## Coverage Assessment

Phase 1 coverage is high and consistent with the plan's success criteria:

* Exactly three deployment subjects are defined and tested: Pass
* Distinct route mapping is enforced: Pass
* Distinct secrets are enforced: Pass
* Predictive and generative payload semantics are enforced: Pass
* Readiness gating is enforced: Pass
* Repo-wide CI enforcement remains unimplemented: Major gap

Overall coverage for the fixture and contract-harness portion of Phase 1: 90 percent; the only material gap is the missing workflow-level enforcement path.

## Recommended Next Validations

* Verify whether the project will add a dedicated GitHub or Azure pipeline workflow for the issue-8 contract suite before promotion.
* Bind the `pytest -q tests/test_foundry_local_deployment_contracts.py` gate to that workflow once the repo adds CI configuration.
* Run the broader project test set after the workflow bridge is added, not only the focused contract suite.
* Revisit the local contract harness against the real Foundry Local or gateway configuration once runtime deployment metadata is available.

## Clarifying Questions

No blocking clarifying questions at this time. The implementation and design artifacts are sufficient to validate the Phase 1 contract fixture and identify the remaining workflow gap.

## Validation Command Evidence

The local contract suite was executed with fresh verification:

```bash
cd /home/dakir/tiger-poc && python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py
```

Result: `3 passed in 0.01s`

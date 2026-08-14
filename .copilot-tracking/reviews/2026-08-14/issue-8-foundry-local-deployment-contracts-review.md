<!-- markdownlint-disable-file -->
# Task Review: Issue 8 Foundry Local deployment contracts

## Review metadata

* Review date: 2026-08-14
* Related plan: [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md)
* Changes log: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md)
* Research note: [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md)

## Summary

The implementation satisfies the issue-8 contract requirements for the three local Foundry deployments. The runtime enforces deployment identity, route isolation, unique auth, payload semantics, and readiness gating. The only significant remaining gap is repo-level CI enforcement for the suite, which the plan and change log both note as a follow-up item because no dedicated workflow currently exists.

### Severity counts

* Critical: 0
* Major: 1
* Minor: 1

## Synthesized RPI validation findings

### Phase 1: Establish deploy contract fixtures

Status: Pass

Evidence:

* The runtime defines the three deployment identities and per-deployment metadata in [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L5-L72).
* The route mapping matches the design: YOLO and Florence-2 use `/v1/predict`, while Phi-4-multimodal uses `/v1/chat/completions` in [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L11-L19).
* The contract matrix is consistent with the issue research at [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L20-L36) and [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L71-L89).

### Phase 2: Add contract assertion suite

Status: Pass

Evidence:

* Predictive versus generative payload semantics are asserted in [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L19-L45).
* Wrong-route and wrong-auth cases are rejected without fallback in [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L47-L70).
* Non-ready deployments are explicitly gated in [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L28-L41) and [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L55-L70).

### Phase 3: Validation

Status: Pass

Evidence:

* The plan records the local validation gate at [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L66-L82).
* The changes log records the exact pytest validation command and result in [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L27-L34).

## Implementation quality findings

### Functional correctness

Status: Pass

* The runtime enforces one model per deployment, route correctness, and auth separation in [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L5-L78).
* The tests prove the desired isolation and failure behavior in [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L4-L70).

### Architectural alignment

Status: Pass with follow-up gap

* The implementation aligns closely with the architecture and research requirements documented in [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L20-L220).
* The main remaining architectural gap is operational: repo CI is not yet bound to the contract suite, despite the design and plan expecting CI coverage before promotion.

## Validation command output

Command run:

```bash
cd /home/dakir/tiger-poc && python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py
```

Observed output:

```text
...                                                                      [100%]
3 passed in 0.01s
```

## Major findings

### 1. CI enforcement is still missing

Severity: Major

Evidence:

* The issue plan explicitly calls for CI coverage before promotion at [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L12-L18).
* The design research states that predictive and generative endpoint contract tests should run in CI before promotion at [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L195-L220).
* The changes log documents this as a follow-up gap: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L24-L35).

Impact:

* The contract suite is valid locally and passes, but the repo does not yet enforce it in a persistent CI gate. This is operationally important for promotion and release assurance.

## Minor findings

### 2. Response semantics are validated, but HTTP status codification is not pinned in the contract layer

Severity: Minor

Evidence:

* The harness returns status strings like `wrong_route`, `unauthorized`, and `not_ready` from [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L24-L78).
* The issue research and the plan focus on contract isolation and readiness, not a full HTTP status-code contract matrix.

Impact:

* The current implementation proves boundary behavior well for local validation, but it does not yet define a formal HTTP status mapping for external API consistency if the runtime is promoted as a gateway service.

## Missing work and deviations

### Deferred from scope

* Add or bind a GitHub Actions or other CI workflow to the issue-8 pytest contract suite before promotion.

### Discovered during review

* Define an explicit HTTP status contract for route/auth/readiness failures if the local harness is promoted to a production-facing API layer.

## Follow-up work recommendations

### From the plan and issue scope

1. Add a repo CI workflow that executes `python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py` for issue-8 gate enforcement.
2. Bind the gate to merge or promotion checks once the repo has a standard workflow structure.

### From review findings

1. Add a small HTTP semantics layer if the contract harness is evolved beyond local validation.
2. Keep the current local pytest suite as the deterministic safety net while CI enforcement is added.

## Overall status

Status: Needs Rework

Reason:

* The local issue-8 implementation is correct and passes validation.
* The remaining gap is not a bug in the contract logic; it is the missing repo-level CI enforcement required by the plan and design for promotion readiness.

## Reviewer notes

The issue-8 deployment contract implementation is in good shape and satisfies the core engineering requirement: three independent deployments, unique auth, route isolation, correct payload semantics, and readiness gating. The remaining work is a process gate rather than a functionality defect, and it should be treated as a follow-on release requirement rather than a blocker to the local contract behavior itself.

# RPI Validation: Issue 8 Foundry Local Deployment Contracts - Phase 2

## Validation Scope

Validated against the implementation artifacts and the issue-discovery materials for Phase 2 of Issue 8:

- Plan: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md)
- Changes log: [..copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](../../../.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md)
- Research: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md)
- Implementation: [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py)
- Tests: [tests/test_foundry_local_deployment_contracts.py](../../../tests/test_foundry_local_deployment_contracts.py)

## Validation Status

Partial

## Executive Summary

Phase 2 is materially compliant with the design and issue requirements for route isolation, payload semantics, auth separation, readiness gating, and failure isolation. The runtime enforces one model per deployment, unique routes and secrets, correct predictive vs. generative payload validation, and a non-ready rejection path without falling back to a sibling deployment.

The remaining gap is process-level rather than logic-level: the repo still does not include a dedicated CI workflow that enforces the same contract suite, so promotion gating remains local-only and must be recorded as follow-up work before broader release promotion.

## Requirements Extracted from Phase 2

The Phase 2 checklist defines the expected scope explicitly:

- Add route and payload contract assertions for predictive and generative endpoints: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L58-L61)
- Add auth separation, readiness, and non-ready failure gate tests: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L59-L61)
- Ensure failures are isolated and actionable: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L60-L61)

The issue design confirms the required contract matrix:

- YOLO and Florence-2 are predictive deployments on /v1/predict; Phi-4-multimodal is generative on /v1/chat/completions: [docs/system-design.md](../../../docs/system-design.md#L31-L35), [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L39-L46)
- One model per deployment, one route, one secret, one readiness state: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L52-L67)
- Predictive and generative payloads must not be interchanged: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L100-L129)
- Readiness and failure gating must reject traffic without silent fallback: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L134-L150)

## Matched Requirements and Evidence

### 1. Route model matches the design

Evidence of correct route mapping:

- System design states that YOLO and Florence-2 use /v1/predict while Phi-4-multimodal uses /v1/chat/completions: [docs/system-design.md](../../../docs/system-design.md#L31-L35)
- Contract runtime assigns the expected route for each deployment and validates route equality before accepting traffic: [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L11-L19), [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L25-L41)
- Tests assert the route split and unique deployment metadata: [tests/test_foundry_local_deployment_contracts.py](../../../tests/test_foundry_local_deployment_contracts.py#L4-L17)

### 2. Predictive vs. generative payload semantics match the design

Evidence:

- Research states predictive requests use /v1/predict and generative requests use /v1/chat/completions with different payload semantics: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L100-L129)
- Runtime payload validation checks for image-based predictive inputs and message-based chat-completion inputs, and rejects the opposite shape: [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L34-L41), [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L42-L78)
- Tests explicitly verify both valid success paths and wrong-payload rejections: [tests/test_foundry_local_deployment_contracts.py](../../../tests/test_foundry_local_deployment_contracts.py#L19-L39)

### 3. Auth separation is enforced per deployment

Evidence:

- Research states each deployment owns an independent API key Secret, and auth is checked per deployment: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L71-L89)
- Runtime enforces secret equality against the model-specific secret and returns unauthorized without fallback: [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L20-L19), [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L31-L41), [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L52-L58)
- Tests assert a cross-deployment secret is rejected: [tests/test_foundry_local_deployment_contracts.py](../../../tests/test_foundry_local_deployment_contracts.py#L41-L48)

### 4. Readiness and failure behavior match the design

Evidence:

- Research expects non-ready deployments to be rejected and failure isolation to remain local to the deployment: [..copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](../../../.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L134-L150)
- Runtime checks readiness before route, auth, and payload validation and returns a not_ready result without attempting a sibling fallback: [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L28-L41), [apps/local_model_runtime/foundry_contract.py](../../../apps/local_model_runtime/foundry_contract.py#L45-L58)
- Tests confirm wrong auth, wrong route, and non-ready rejection paths: [tests/test_foundry_local_deployment_contracts.py](../../../tests/test_foundry_local_deployment_contracts.py#L41-L58)

## Findings

### Severity: Critical

- None.

### Severity: Major

1. CI enforcement gap remains unresolved.
   - Evidence: The plan explicitly calls for CI coverage before promotion and for recording the enforcement mechanism when the repo lacks a workflow: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L12-L18), [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L69-L76)
   - Evidence: The release changes log explicitly records that no dedicated workflow file exists yet and that local pytest is the current gate: [..copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](../../../.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L25-L34)
   - Assessment: This is a release-process gap, not a route/auth/payload logic defect. It does not invalidate Phase 2’s contract assertions, but it means the repo is not yet fully aligned with the design’s promotion requirement.

### Severity: Minor

1. Local-only gate is acceptable for this issue but should be tracked as a follow-up.
   - Evidence: The project validation step treats the repo’s standard pytest command as the local gate until a dedicated workflow is added: [..copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](../../../.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L70-L76)
   - Assessment: This is not a defect in the contract logic; it is a follow-up operational item for CI enforcement.

## Coverage Assessment

Coverage is strong for the relevant Phase 2 contract dimensions:

- Route boundaries: covered and correct
- Payload semantics: covered and correct
- Auth separation: covered and correct
- Readiness gating: covered and correct
- Failure isolation: covered and correct

The implementation aligns with the issue research and the system design. The only partial item is the missing repo CI enforcement path for the same contract suite.

## Validation Command Evidence

The local contract suite passed on the current branch:

- Command: `python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py`
- Result: `3 passed in 0.01s`

This confirms the runtime behavior asserted in the implementation and the tests is active in the workspace at validation time.

## Clarifying Questions / Follow-up Required

1. Should the team treat the missing repo CI workflow as a hard blocker before release promotion, or is the local pytest contract gate sufficient for the current milestone?
2. If a workflow is required, should the same issue-8 suite be bound to an existing GitHub Actions workflow or should a new workflow be added explicitly for this contract gate?

## Final Assessment

Phase 2 is functionally aligned with the issue design and is validated as contract-compliant for route, payload, auth, readiness, and isolation behavior. The main remaining gap is that the project still lacks a dedicated CI enforcement path for the same suite, which should be addressed before the stack is treated as fully promotion-ready.

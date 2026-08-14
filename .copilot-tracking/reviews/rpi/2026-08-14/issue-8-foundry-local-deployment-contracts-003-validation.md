# RPI Validation: Issue 8 Foundry Local Deployment Contracts — Phase 3

## Scope

This validation compares the phase 3 requirements in the implementation plan against the implementation changes, the research note, and the issue planning log for Issue 8.

## Validation Status

Status: Passed

Phase 3 closure is supported by the completed validation steps in the plan, the local contract harness implementation, and the passing pytest contract suite. The remaining issues are documented follow-ups rather than unimplemented phase-3 requirements.

## Artifacts Reviewed

- Plan: [.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L66-L82)
- Changes log: [.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L1-L34)
- Research note: [.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L20-L36)
- Planning log: [.copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md](.copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md#L1-L49)
- Runtime implementation: [apps/local_model_runtime/foundry_contract.py](apps/local_model_runtime/foundry_contract.py#L14-L78)
- Contract tests: [tests/test_foundry_local_deployment_contracts.py](tests/test_foundry_local_deployment_contracts.py#L11-L69)

## Phase 3 Requirement Comparison

### Step 3.1: Run relevant project validation commands

Requirement: Execute the contract test suite and any direct lint or test commands covering the modified area; treat the repository pytest contract command as the local gate until a dedicated workflow exists.

Evidence:
- The plan explicitly records the validation step in the phase 3 checklist: [plan](.copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md#L66-L82).
- The issue-8 changes log records the local validation gate and the exact test command in the release summary: [changes](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L27-L34).

### Step 3.2: Fix minor validation issues

Requirement: Iterate on mismatched payload expectations, route assertions, or fixture data issues when they are small and isolated.

Evidence:
- The contract harness is deterministic and enforces route, payload, auth, and readiness checks directly in one execution path: [runtime](apps/local_model_runtime/foundry_contract.py#L14-L78).
- The tests exercise the corrected success and failure cases for payload semantics, wrong auth, and non-ready deployment behavior: [tests](tests/test_foundry_local_deployment_contracts.py#L11-L69).

### Step 3.3: Report blocking issues

Requirement: Document remaining gaps that require follow-on work, without widening scope beyond the issue-8 contract suite.

Evidence:
- The planning log explicitly records the remaining high-priority follow-up for CI binding: [planning log](.copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md#L40-L49).
- The changes log also notes that no dedicated CI workflow file exists yet and that the local pytest suite remains the gate until a workflow is added: [changes](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L27-L33).

## Validation Command Evidence

Command executed:

```bash
cd /home/dakir/tiger-poc && python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py
```

Observed output:

```text
...                                                                      [100%]
3 passed in 0.01s
```

This confirms the issue-8 contract suite passed in the local repo validation gate.

## Findings

### Major

1. CI enforcement for the issue-8 contract gate is not yet bound to a repo workflow.
   - Why it matters: The design and research explicitly require predictive and generative endpoint contract tests in CI before promotion, not only in the local validation gate. See the research statement: [research](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L30-L36) and the follow-up note: [research](.copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md#L152-L220).
   - Evidence: The planning log identifies this as the high-priority follow-up gap, with explicit workflow-binding guidance: [planning log](.copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md#L40-L49). The changes log also records the absence of the workflow file and the fallback local gate: [changes](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L27-L33).
   - Severity rationale: This is a meaningful gap against the promotion requirement, but it is documented as follow-up work and not a failure of the implemented local contract suite.

### Minor

2. Exact production status codes for wrong-route and wrong-auth responses are not fully specified in the repo docs.
   - Why it matters: The research describes the boundary contract but does not pin a complete status-code matrix for every failure scenario.
   - Evidence: The planning log notes this as a medium-impact unaddressed research item: [planning log](.copilot-tracking/plans/logs/2026-08-14/issue-8-foundry-local-deployment-contracts-log.md#L5-L19).
   - Severity rationale: This is a documentation and contract-precision gap, not a functional failure in the current local test harness.

## Coverage Assessment

Coverage is strong for the implemented phase-3 requirements:

- One model per deployment is enforced by the contract definitions and the suite: [runtime](apps/local_model_runtime/foundry_contract.py#L14-L21), [tests](tests/test_foundry_local_deployment_contracts.py#L11-L27)
- Route isolation for predictive vs generative endpoints is enforced: [runtime](apps/local_model_runtime/foundry_contract.py#L32-L73), [tests](tests/test_foundry_local_deployment_contracts.py#L29-L58)
- Auth separation and non-ready rejection are validated: [runtime](apps/local_model_runtime/foundry_contract.py#L46-L78), [tests](tests/test_foundry_local_deployment_contracts.py#L61-L69)
- Local validation command is recorded and passes: [changes](.copilot-tracking/changes/2026-08-14/issue-8-foundry-local-deployment-contracts-changes.md#L34), [validation command above]

## Final Assessment

The phase 3 validation objective is satisfied. The implementation proves the deployment contract behavior required by Issue 8 in the local repo gate, and the remaining follow-up items are explicitly documented in the plan and changes log rather than left undocumented.

## Recommended Next Validations

- Bind the issue-8 contract suite to the repo's CI workflow once an actual workflow file exists.
- Add the explicit wrong-route/wrong-auth status-code matrix if production behavior must be pinned more tightly.
- If an Azure Local or hosted edge parity environment becomes available, run the same contract checks against the live deployment topology.

## Clarifying Questions

None required to validate the phase 3 closure against the current artifacts. The only missing information is the eventual CI workflow location and the production status-code expectations, which are already captured as documented follow-ups rather than unresolved defects.

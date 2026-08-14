<!-- markdownlint-disable-file -->
# Planning Log: Issue 8 Foundry Local deployment contracts

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* DR-01: Exact production Foundry Local response codes for wrong-route and wrong-auth behavior are not fully specified in the repo docs.
  * Source: .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md
  * Reason: The issue research describes the boundary contract but does not define a full failure matrix for every status code.
  * Impact: Medium
* DR-02: The issue requires a CI contract gate before promotion, but the implementation plan does not name the exact CI entry point or workflow that enforces it.
  * Source: docs/system-design.md and .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md
  * Reason: The design and research call for predictive and generative endpoint contract tests in CI before promotion, but the plan stops at a generic "pytest -q" validation command without binding it to a repo CI workflow.
  * Impact: Medium

### Plan Deviations from Research

* DD-01: The implementation will favor a deterministic local contract harness instead of a broad production-grade endpoint matrix.
  * Research recommends: Run deployment contract tests across a local Foundry-compatible mock or stack with explicit route, auth, and payload assertions.
  * Plan implements: A focused contract suite that validates the deployment boundaries and CI gate requirements without a full production failover matrix.
  * Rationale: The repo context is a local proof-of-concept and the issue asks specifically for contract validation before promotion.

## Implementation Paths Considered

### Selected: Deterministic contract harness for local deployment assertions

* Approach: Build a small, repeatable test harness around local Foundry-compatible runtime metadata and request validation that asserts one-model-per-deployment, per-deployment route, unique secret, payload type, and readiness behavior.
* Rationale: This approach matches the repo's local dev parity story and the design's explicit CI requirement for predictive and generative endpoint contract tests.
* Evidence:.docs/system-design.md and .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md

### IP-01: Broad end-to-end smoke test only

* Approach: Run a generic local smoke test without asserting deployment identity, path isolation, or credential separation.
* Trade-offs: Lower effort, but it does not actually prove the deployment contract and would miss cross-deployment leakage or wrong-route acceptance.
* Rejection rationale: It does not satisfy the issue's requirement to validate auth boundaries and route correctness in CI.

## Suggested Follow-On Work

* WI-01: Add an explicit status-code matrix for wrong-route and wrong-auth failures — Medium priority
  * Source: issue research and design notes
  * Dependency: The contract suite is implemented and the API responses are observed in the local runtime
* WI-02: Bind the issue-8 contract suite to the repo's actual CI workflow when one exists or add the workflow file that enforces the gate — High priority
  * Source: design requirement and plan validation review
  * Dependency: The repo CI workflow is introduced or extended to run the contract suite before promotion
* WI-03: Expand the contract suite to cover a hosted Azure Local parity run — Medium priority
  * Source: docs/system-design.md parity section
  * Dependency: Access to the edge deployment environment and a managed secret configuration

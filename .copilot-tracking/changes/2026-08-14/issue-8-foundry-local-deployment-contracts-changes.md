<!-- markdownlint-disable-file -->
# Release Changes: Issue 8 Foundry Local deployment contracts

**Related Plan**: issue-8-foundry-local-deployment-contracts-plan.instructions.md
**Implementation Date**: 2026-08-14

## Summary

Added a deterministic local Foundry deployment contract harness and a focused pytest suite covering identity, route, payload, auth, and readiness isolation for the three local model deployments.

## Changes

### Added

* apps/local_model_runtime/__init__.py - package export for the local Foundry contract runtime
* apps/local_model_runtime/foundry_contract.py - deterministic deployment contract runner that enforces one model per deployment, route matching, payload semantics, auth checks, and readiness gating
* tests/test_foundry_local_deployment_contracts.py - pytest coverage for the three deployment contracts and route/auth/readiness edge cases

### Modified

* .copilot-tracking/plans/2026-08-14/issue-8-foundry-local-deployment-contracts-plan.instructions.md - marked all implementation phases complete after validation

### Removed

* None

## Additional or Deviating Changes

* The repo does not yet include a dedicated CI workflow file for issue-8 routing enforcement; the validation gate remains the local pytest contract suite until a workflow is added.
  * Reason: The design and research call for CI enforcement, but no existing repository workflow currently binds the contract suite.

## Release Summary

The issue-8 contract work now proves the three local deployment boundaries: YOLO and Florence-2 each use /v1/predict with distinct secrets and predictive payload semantics, while Phi-4-multimodal uses /v1/chat/completions with its own secret and chat-completion semantics. The local contract runner rejects wrong routes, wrong auth, wrong payloads, and non-ready deployments without silent fallback to a sibling deployment. Validation evidence: `python3 -m pytest -q tests/test_foundry_local_deployment_contracts.py` passed with 3/3 tests green.

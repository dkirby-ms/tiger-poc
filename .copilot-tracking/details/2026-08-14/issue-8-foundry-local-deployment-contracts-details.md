<!-- markdownlint-disable-file -->
# Implementation Details: Issue 8 Foundry Local deployment contracts

## Context Reference

Sources:
* docs/system-design.md
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md

## Implementation Phase 1: Establish the deployment contract fixtures

<!-- parallelizable: true -->

### Step 1.1: Define the three deployment identities and expected contracts

Create the contract matrix for the three Foundry Local deployments: YOLO and Florence-2 are predictive deployments routed through /v1/predict, while Phi-4-multimodal is a generative deployment routed through /v1/chat/completions. Each deployment must define a single model identity, a distinct route, a unique secret, and a readiness state.

Files:
* docs/system-design.md - architecture and parity requirements for deployment separation and lifecycle
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md - issue-specific contract summary and recommended matrix

Discrepancy references:
* Addresses: DR-01 and DD-01 in the planning log to move from architecture intent to explicit contract validation

Success criteria:
* The suite enumerates exactly three deployment subjects and their expected routes
* The metadata includes one model identifier and one auth secret per deployment
* The fixture preserves the distinction between predictive and generative payload semantics

Context references:
* docs/system-design.md (Lines 90-96) - route and model separation
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md (Lines 22-57) - the architecture-derived deployment model

Dependencies:
* Reviewed design documentation and the issue-specific research note
* Local test harness or contract mock capable of serving deployment metadata

### Step 1.2: Add the local contract fixture or runtime data for YOLO, Florence-2, and Phi-4-multimodal

Add a deterministic local fixture that mirrors the Foundry-compatible runtime contract. The fixture should expose deployment metadata, supported routes, secret values, and readiness toggles so the tests can assert behavior without relying on broad runtime integration.

Files:
* apps/local-model-runtime or the nearest contract test fixture area - service and runtime contract scaffolding
* models/bundle.json - model identity metadata used to validate one-model-per-deployment assumptions

Success criteria:
* Each deployment can be loaded independently from the fixture without sharing a global model or secret
* Readiness can be toggled for each deployment without affecting siblings
* The fixture supports route-level interactions for both predictive and generative request classes

Context references:
* models/bundle.json - bundle definition names the model families used by each deployment
* docs/system-design.md (Lines 177-200) - local parity and lifecycle expectations

Dependencies:
* Step 1.1 completion
* Access to the local runtime or test mock capable of returning a recognized schema

### Step 1.3: Validate phase changes

Run the smallest relevant checks for the fixture and deployment metadata to ensure the contract model is consistent before writing the assertions.

Validation commands:
* pytest -q or the repo's local test command for the target fixture area - verifies the added contract fixture set
* Any direct model-manifest or runtime-setup check used by the local stack - verifies deployment metadata integrity

## Implementation Phase 2: Add the contract assertion suite

<!-- parallelizable: true -->

### Step 2.1: Implement route and payload contract assertions for predictive vs generative endpoints

Add tests that call each deployment using the expected route and payload semantics, then assert that the response type matches the contract. The predictive services must reject generative payload shapes, and the generative service must reject predictive payload shapes. This is the core boundary test for the issue.

Files:
* apps or test area for local runtime validation - contract tests for route and payload behavior
* docs/system-design.md - uses route and payload semantics to define acceptance criteria

Discrepancy references:
* Addresses: the route isolation risk captured in the research note and the selected implementation path in the planning log

Success criteria:
* YOLO and Florence-2 accept valid /v1/predict payloads and reject chat-completion payloads
* Phi-4-multimodal accepts valid /v1/chat/completions payloads and rejects predictive payloads
* Responses are evaluated by schema type and not by a generic fallback path

Context references:
* docs/system-design.md (Lines 90-96) - route mapping guidance
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md (Lines 75-121) - payload and route contract expectations

Dependencies:
* Step 1.2 completion
* Deterministic fixture support for predictive and generative requests

### Step 2.2: Add auth separation, readiness, and non-ready failure gate tests

Add a second layer of assertions for credentials and lifecycle. The contract test must prove that each deployment has a unique secret, that the correct secret is required for success, and that a deployment in a non-ready state is not accepted. It should also verify that a failure in one deployment does not silently redirect traffic to another deployment.

Files:
* apps or test area for local runtime validation - auth and readiness assertions
* docs/system-design.md - per-deployment credential and lifecycle expectations

Success criteria:
* Requests with the wrong secret are rejected for each deployment
* Non-ready deployments reject calls before they are considered routable
* A failed or non-ready deployment does not cause another deployment to absorb traffic

Context references:
* .copilot-tracking/research/2026-08-14/issue-8-foundry-local-deployment-contracts-research.md (Lines 128-179) - readiness and failure gating requirements
* docs/system-design.md (Lines 196-200) - lifecycle requirements for ModelDeployment readiness and parity

Dependencies:
* Step 2.1 completion
* Fixture supports readiness toggling and secret validation

### Step 2.3: Validate phase changes

Run the local contract suite for the modified route, auth, and readiness assertions. Ensure that the failure cases are precise and actionable rather than relying on generic service-level errors.

Validation commands:
* pytest -q on the specific contract test subset - verifies route/auth/readiness cases
* Optional local runtime command used by this repo - confirms the contract mock or local API remains healthy

## Implementation Phase 3: Validation

<!-- parallelizable: false -->

### Step 3.1: Run full project validation

Execute the relevant validation commands for the repo after the contract suite is added. This is the final gate before the issue is considered ready.

Validation commands:
* pytest -q - verifies the contract suite and surrounding app tests
* Any lint or static validation used by the project when it applies to the updated files

### Step 3.2: Fix minor validation issues

Iterate on small issues such as incorrect expected status codes, mismatched payload names, or fixture metadata drift. Keep the fixes narrow and contract-focused.

### Step 3.3: Report blocking issues

When validation reveals broader architectural or runtime gaps beyond the issue scope, note the gap and recommend targeted follow-up planning rather than broad refactoring.

## Dependencies

* pytest or the project's targeted test runner
* local contract fixture or Foundry-compatible runtime capable of per-deployment auth and route checks

## Success Criteria

* The suite proves each deployment is independently addressable, authenticated, and ready
* The suite fails on wrong-path and wrong-secret requests without silent fallback
* The project can run the contract checks as a CI gate before promotion

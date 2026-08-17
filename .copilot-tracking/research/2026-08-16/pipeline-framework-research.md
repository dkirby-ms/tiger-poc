<!-- markdownlint-disable-file -->
# Pipeline Framework Implementation Research

## Scope

Implement the work described by the pipeline framework issue plan without
creating GitHub issues. Complete all locally testable behavior and isolate work
that requires Foundry Local preview artifacts or an Arc-enabled cluster.

## Findings

* The repository currently contains only the local model serving plane.
* `LocalFoundryDeploymentRuntime` is a usable local inference boundary and can
  remain behind an injected pipeline stage until the control-plane split.
* The smallest repository-consistent package location is
  `apps/pipeline_framework/`.
* A bounded in-process runner, typed manifest, file source, local inference,
  threshold and dwell rules, and JSONL sink are fully local.
* Predictive operator compatibility requires an `items` request array and
  `X-API-Key`; generative requests retain bearer authentication.
* Foundry Local operator installation, real `ModelDeployment` reconciliation,
  Arc validation, and Azure IoT Operations validation require external access.
* The host has Python 3.12 and `uv`, but no `python` alias or installed pytest.

## Selected approach

Build a cohesive local vertical slice before service partitioning. Preserve the
existing local runtime behind a control-plane protocol, validate every change
with tests, then add local HTTP partitioning only after the in-process contracts
are stable. This provides useful behavior without pretending the preview-only
operator path has been verified.

## References

* `docs/pipeline-framework.md`
* `.copilot-tracking/research/subagents/2026-08-16/pipeline-framework-local-implementation.md`
* `apps/local_model_runtime/foundry_contract.py`
* `apps/local_model_runtime/workload_adapters.py`
* `apps/local_model_runtime/http_service.py`

## Success criteria

* Existing runtime behavior is characterized before intentional contract edits.
* A manifest validates and runs a bounded file-to-JSONL pipeline.
* Channel overflow and lifecycle behavior are deterministic and tested.
* Local model resolution gates startup on readiness and keeps secrets out of
  manifests.
* Predictive and generative HTTP authentication match the documented target.
* Rule and retention behavior degrades into measured drops rather than crashes.
* External integration gaps are documented with exact prerequisites.

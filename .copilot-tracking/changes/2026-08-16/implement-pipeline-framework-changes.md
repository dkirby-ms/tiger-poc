<!-- markdownlint-disable-file -->
# Pipeline Framework Changes

## Summary

Implemented the local manifest-driven pipeline, corrected model contracts,
added OCI artifact tooling, and aligned setup and documentation.

## Added

* `apps/pipeline_framework/` core, stages, CLI, and reference documentation
* `pipelines/local-yolo.yaml`
* Pipeline core, stage, and end-to-end tests
* `requirements-dev.txt`
* `scripts/package-model-artifact.sh`

## Modified

* Local model runtime predictive payload, authentication, and control plane
* Model gateway header forwarding and verification script
* Development setup, Compose registry profile, and model setup documentation
* Existing model contract tests

## Validation

* 132 pytest tests passed
* Pipeline manifest validation passed
* Bash syntax validation passed
* Editor diagnostics reported no errors

## Deviations

* Used `apps/pipeline_framework/` instead of a multi-package target layout to
  match the current repository.
* Kept the existing HTTP server implementation. A FastAPI migration does not
  add capability required by the local vertical slice.
* Did not run OCI or Compose integration because ORAS is absent and Docker WSL
  integration is disabled.

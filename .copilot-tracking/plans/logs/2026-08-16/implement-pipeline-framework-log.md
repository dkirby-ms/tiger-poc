<!-- markdownlint-disable-file -->
# Pipeline Framework Planning Log

## Status

Local framework, contract, artifact tooling, setup, and documentation phases
are complete. Distributed HTTP partitioning and live platform integrations
remain pending.

## Discrepancies

* The issue plan describes a mature multi-package tree, but the current
  repository has no packaging metadata. The first implementation uses the
  existing `apps/` convention.
* The README references directories and files that do not exist. Documentation
  alignment is part of Phase 4.
* The host has no installed pytest and no `python` alias. Validation will use
  `uv` and `python3`.

## Implementation paths considered

* Selected: cohesive local vertical slice with explicit extension points.
* Rejected: create all target directories as placeholders before behavior
  exists, because it would overstate implementation progress.
* Deferred: live operator integration, because preview artifacts are not
  publicly available and no target cluster credentials were supplied.

## Validation log

* Baseline attempt: blocked before collection because pytest is not installed.
* Isolated baseline: 111 tests passed through `uv`.
* Pipeline core: 10 tests passed after repairing nonblocking channel close.
* Pipeline local workflow: 17 tests passed.
* Final suite: 132 tests passed.
* Example manifest validation passed.
* Bash syntax checks passed.
* Compose validation unavailable because Docker Desktop WSL integration is disabled.
* OCI round trip unavailable because ORAS is not installed.

## Suggested follow-on work

* Verify the operator contract against recorded responses when preview access
  becomes available.
* Add an object tracker before claiming object-level dwell semantics.
* Measure batch wait time against an agreed event-latency budget.

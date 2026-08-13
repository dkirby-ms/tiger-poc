<!-- markdownlint-disable-file -->
# Epic 5 changes log

## Related plan
* [.copilot-tracking/plans/2026-08-13/epic-5-inference-event-rules-plan.instructions.md](../../plans/2026-08-13/epic-5-inference-event-rules-plan.instructions.md)

## Implementation date
2026-08-13

## Summary of changes
* Added a normalized inference model for Foundry Local responses.
* Added event-rule filtering for confidence and dwell-time thresholds.
* Added a local detection store with JSON and clip persistence.
* Added regression tests for inference, event rules, and local persistence.

## Changed files
### Added
* [apps/vision-pipeline/inference_api/__init__.py](../../apps/vision-pipeline/inference_api/__init__.py)
* [apps/vision-pipeline/inference_api/service.py](../../apps/vision-pipeline/inference_api/service.py)
* [apps/vision-pipeline/event_rules/__init__.py](../../apps/vision-pipeline/event_rules/__init__.py)
* [apps/vision-pipeline/event_rules/service.py](../../apps/vision-pipeline/event_rules/service.py)
* [apps/vision-pipeline/local_store/__init__.py](../../apps/vision-pipeline/local_store/__init__.py)
* [apps/vision-pipeline/local_store/service.py](../../apps/vision-pipeline/local_store/service.py)
* [apps/vision-pipeline/tests/test_epic_5.py](../../apps/vision-pipeline/tests/test_epic_5.py)

### Modified
* [apps/vision-pipeline/pyproject.toml](../../apps/vision-pipeline/pyproject.toml)

### Removed
* None

## Validation
* `cd /home/saitcho/tiger-poc/apps/vision-pipeline && PYTHONPATH=. .venv/bin/pytest -q`
* Result: 10 passed in 0.19s

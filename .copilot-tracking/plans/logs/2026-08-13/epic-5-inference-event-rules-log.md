<!-- markdownlint-disable-file -->
# Epic 5 planning log

## Discrepancy log
* The editable-install metadata initially omitted the newly added packages; pytest could not import the Epic 5 modules until the package list was updated.
* The repo resolves Python imports via `PYTHONPATH=.` in this session, so package discovery was validated using the project root rather than a fresh pip install.

## Implementation paths considered
* Selected: add lightweight data model + normalization + rules + persistence with direct tests and local config.
* Alternative: skip explicit event-rules store and encode all logic in the inference API. Rejected because it would conflate concerns and make later Epic 6 work harder.

## Follow-on work
* Epic 6: MQTT publication from filtered detections.
* Epic 4: model bundle hardening and execution-provider config validation.
* Epic 7: compose integration for the end-to-end local pipeline.

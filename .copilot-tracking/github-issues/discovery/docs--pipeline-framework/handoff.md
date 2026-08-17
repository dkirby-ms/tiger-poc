<!-- markdownlint-disable-file -->
<!-- markdown-table-prettify-ignore-start -->
# GitHub Issue Operations Handoff

## Planning Files

* `.copilot-tracking/github-issues/discovery/docs--pipeline-framework/issue-analysis.md`
* `.copilot-tracking/github-issues/discovery/docs--pipeline-framework/issues-plan.md`
* `.copilot-tracking/github-issues/discovery/docs--pipeline-framework/planning-log.md`
* `.copilot-tracking/github-issues/discovery/docs--pipeline-framework/handoff.md`

## Summary

| Action    | Count |
|-----------|-------|
| Create    | 14    |
| Update    | 0     |
| Link      | 0     |
| Close     | 0     |
| Comment   | 0     |
| No Change | 0     |

All entries are provisional planning records. No GitHub issue, label, milestone, comment, or relationship was created.

## Issues

### Create

* [ ] `{{TEMP-1}}` `feat(pipeline): build the next-generation video analysis platform`
  * Labels: feature; Milestone: none; Parent: none
  * Body: Parent epic for the move from the current prototype to a flexible video analysis platform.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-2}}` `test(runtime): protect today's working behavior`
  * Labels: maintenance; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Record current model service behavior so the migration does not introduce accidental changes.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-3}}` `feat(models): make model delivery repeatable`
  * Labels: feature, infrastructure; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Create a repeatable way to publish, retrieve, and verify AI models while preserving local development.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-4}}` `chore(infrastructure): prepare a local environment for future model integration`
  * Labels: maintenance, infrastructure; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Prepare the local environment needed for future shared-model integration.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-5}}` `feat(core): define reusable video workflow building blocks`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Define reusable components for video sources, processing, AI analysis, and outputs.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-6}}` `feat(core): run video workflows from configuration`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Let teams describe and run workflows from configuration, with early checks for setup mistakes.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-7}}` `feat(video): deliver the first complete video workflow`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Connect recorded and live video to preprocessing, AI detection, and saved events.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-8}}` `feat(foundry): connect workflows to the right AI model`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Connect workflow AI steps to named models, with readiness, startup preparation, and health reporting.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-9}}` `fix(foundry): align model requests with the target platform`
  * Labels: bug, breaking-change; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Update model requests and service endpoints to match the target platform, including security and batching.
  * Similarity: Pending GitHub search. Human review required because this changes public behavior.
* [ ] `{{TEMP-10}}` `feat(foundry): run against the shared model platform`
  * Labels: feature, infrastructure; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Connect workflows to platform-managed models when preview access is available.
  * Similarity: Pending GitHub search. Human review required because preview APIs and secrets are not yet available.
* [ ] `{{TEMP-11}}` `feat(events): turn detections into useful events`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Add tracking, business rules, saved clips, notifications, and safe storage management.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-12}}` `feat(observability): make workflow health visible`
  * Labels: feature; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Show operators where workflows are slow, backed up, dropping video, or waiting on a model.
  * Similarity: Pending GitHub search.
* [ ] `{{TEMP-13}}` `feat(topology): run workflows across multiple services`
  * Labels: feature, infrastructure; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Run the same workflow locally or across multiple services while keeping results consistent.
  * Similarity: Pending GitHub search. Human review required for delivery semantics.
* [ ] `{{TEMP-14}}` `docs(repo): make setup and project structure clear`
  * Labels: documentation, maintenance; Milestone: none; Parent: `{{TEMP-1}}`
  * Body: Bring setup instructions, project structure, and dependency guidance in line with the code.
  * Similarity: Pending GitHub search.

## Review Gates

* [ ] Run GitHub duplicate and similarity searches for each candidate before any execution.
* [ ] Decide whether `IS009` is a breaking change or needs a compatibility endpoint/version.
* [ ] Resolve fan-in, remote delivery, retry, idempotency, and metric-cardinality contracts before implementation.
* [ ] Confirm Foundry preview API/CRD/secret details before planning `IS010` as executable work.

## Next Step

Use this handoff as a local backlog draft. A later execution workflow must hydrate existing issues, classify Match/Similar/Distinct/Uncertain, replace temporary IDs, and request approval before mutations under Partial Autonomy.
<!-- markdown-table-prettify-ignore-end -->

<!-- markdownlint-disable-file -->
<!-- markdown-table-prettify-ignore-start -->
# Issues Plan

* **Repository**: dkirby-ms/tiger-poc
* **Milestone**: Not assigned
* **Execution status**: Planning only. Do not create or update GitHub issues from this handoff without a later duplicate search and approval.

## IS001 - Create - Build the next-generation video analysis platform

Parent tracking issue for the move from the current prototype to a flexible video analysis platform.

IS001 - Similarity: Pending GitHub search; provisional Create.

* IS001 - issue_number: `{{TEMP-1}}`
* IS001 - title: `feat(pipeline): build the next-generation video analysis platform`
* IS001 - state: not-created
* IS001 - labels: feature
* IS001 - milestone: none
* IS001 - assignees: none

### IS001 - body

```markdown
## Summary

## Summary

Build a flexible platform for assembling video analysis workflows from reusable components. The platform should support local development first, then larger deployments, while connecting each workflow to the right AI model and making system health visible.

## Acceptance Criteria

* The work is delivered in small, testable steps from protecting current behavior through running workflows across services.
* Teams can add new video sources, processing steps, AI models, and outputs without rewriting the platform.
* The local development path remains useful while the shared model platform is unavailable.
* The platform reports slowdowns, dropped video, and unavailable models clearly.
```

### IS001 - Relationships

* IS001 - parent-of - `{{TEMP-2}}` through `{{TEMP-14}}`: migration work items for the framework.

## Child Issues

### IS002 - Create - Protect today's working behavior

Record the current behavior before making changes. Acceptance criteria: existing routes continue to work; credentials stay with the intended model service; readiness and invalid requests produce clear responses; a fixed image produces repeatable detection results; tests run with the current dependency set.

IS002 - Similarity: Pending GitHub search; provisional Create.

* IS002 - issue_number: `{{TEMP-2}}`
* IS002 - title: `test(runtime): protect today's working behavior`
* IS002 - state: not-created
* IS002 - labels: maintenance
* IS002 - milestone: none
* IS002 - assignees: none

### IS003 - Create - Make model delivery repeatable

Create a repeatable way to package, publish, retrieve, and verify an AI model. Acceptance criteria: the model can be pushed to and pulled from a local registry; its identity is checked; the pulled file can be loaded; local file-based development still works.

IS003 - Similarity: Pending GitHub search; provisional Create.

* IS003 - issue_number: `{{TEMP-3}}`
* IS003 - title: `feat(models): make model delivery repeatable`
* IS003 - state: not-created
* IS003 - labels: feature, infrastructure
* IS003 - milestone: none
* IS003 - assignees: none

### IS004 - Create - Prepare a local environment for future model integration

Prepare the local pieces needed for a future shared-model integration. Acceptance criteria: the setup is repeatable; the local registry is reachable; the required platform components report healthy; the setup clearly identifies the remaining preview-only step.

IS004 - Similarity: Pending GitHub search; provisional Create.

* IS004 - issue_number: `{{TEMP-4}}`
* IS004 - title: `chore(infrastructure): prepare a local environment for future model integration`
* IS004 - state: not-created
* IS004 - labels: maintenance, infrastructure
* IS004 - milestone: none
* IS004 - assignees: none

### IS005 - Create - Define the building blocks for video workflows

Define the common building blocks used by every workflow component. Acceptance criteria: each video item keeps its identity and timing; sources, processing steps, AI steps, and outputs have clear lifecycle and health rules; new components can validate their settings before starting; shared tests verify the common behavior.

IS005 - Similarity: Pending GitHub search; provisional Create.

* IS005 - issue_number: `{{TEMP-5}}`
* IS005 - title: `feat(core): define reusable video workflow building blocks`
* IS005 - state: not-created
* IS005 - labels: feature
* IS005 - milestone: none
* IS005 - assignees: none

### IS006 - Create - Run workflows from a configuration file

Let teams describe and run a workflow from a configuration file. Acceptance criteria: invalid or incomplete workflows are rejected before they start; a simple video-file-to-results example runs locally; the system limits queues so a slow step does not consume unlimited memory; dropped items are counted.

IS006 - Similarity: Pending GitHub search; provisional Create.

* IS006 - issue_number: `{{TEMP-6}}`
* IS006 - title: `feat(core): run video workflows from configuration`
* IS006 - state: not-created
* IS006 - labels: feature
* IS006 - milestone: none
* IS006 - assignees: none

### IS007 - Create - Deliver the first complete video workflow

Connect real video inputs to preprocessing, AI detection, and saved events. Acceptance criteria: a recorded clip produces ordered detection events; live camera reconnects are handled; image timing is preserved; batching and dropped-video behavior are tested; the end-to-end test has a clear response-time target.

IS007 - Similarity: Pending GitHub search; provisional Create.

* IS007 - issue_number: `{{TEMP-7}}`
* IS007 - title: `feat(video): deliver the first complete video workflow`
* IS007 - state: not-created
* IS007 - labels: feature
* IS007 - milestone: none
* IS007 - assignees: none

### IS008 - Create - Connect workflows to the right AI model

Connect workflow AI steps to models by name rather than by hard-coded address. Acceptance criteria: the requested model is resolved at startup; work waits until the model is ready; startup prepares the model for its first request; model health is reflected in workflow health; image and conversational requests use the appropriate request format.

IS008 - Similarity: Pending GitHub search; provisional Create.

* IS008 - issue_number: `{{TEMP-8}}`
* IS008 - title: `feat(foundry): connect workflows to the right AI model`
* IS008 - state: not-created
* IS008 - labels: feature
* IS008 - milestone: none
* IS008 - assignees: none

### IS009 - Create - Align model requests with the target platform

Update model requests and service endpoints to match the target platform. Acceptance criteria: recorded examples verify request and response formats; each request type uses the intended authentication method; small image batches preserve order; the team documents whether existing clients remain supported; service tests run without live servers.

IS009 - Similarity: Pending GitHub search; provisional Create.

* IS009 - issue_number: `{{TEMP-9}}`
* IS009 - title: `fix(foundry): align model requests with the target platform`
* IS009 - state: not-created
* IS009 - labels: bug, breaking-change
* IS009 - milestone: none
* IS009 - assignees: none

### IS010 - Create - Run against the shared model platform

Connect the workflow framework to the shared model platform. Acceptance criteria: the platform's deployment and credential formats are verified; access is limited to what the service needs; model creation, readiness, and removal are covered; the same workflow runs with local services and platform-managed models when preview access is available.

IS010 - Similarity: Pending GitHub search; provisional Create.

* IS010 - issue_number: `{{TEMP-10}}`
* IS010 - title: `feat(foundry): run against the shared model platform`
* IS010 - state: not-created
* IS010 - labels: feature, infrastructure
* IS010 - milestone: none
* IS010 - assignees: none

### IS011 - Create - Turn detections into useful events

Add the business logic and outputs that turn detections into useful events. Acceptance criteria: activity is tracked per camera; threshold and dwell rules produce repeatable results; event records and clips are saved; old data is removed before storage fills; storage pressure becomes visible dropped work; retries do not create duplicate notifications.

IS011 - Similarity: Pending GitHub search; provisional Create.

* IS011 - issue_number: `{{TEMP-11}}`
* IS011 - title: `feat(events): turn detections into useful events`
* IS011 - state: not-created
* IS011 - labels: feature
* IS011 - milestone: none
* IS011 - assignees: none

### IS012 - Create - Make workflow health visible

Give operators a clear view of workflow health and performance. Acceptance criteria: slow steps, backed-up queues, sent and dropped video, and model health are visible; dashboards do not grow without limit as cameras are added; a single event can be followed through the workflow; degraded models do not crash the runner.

IS012 - Similarity: Pending GitHub search; provisional Create.

* IS012 - issue_number: `{{TEMP-12}}`
* IS012 - title: `feat(observability): make workflow health visible`
* IS012 - state: not-created
* IS012 - labels: feature
* IS012 - milestone: none
* IS012 - assignees: none

### IS013 - Create - Run workflows across multiple services

Allow the same workflow to run locally or across multiple services. Acceptance criteria: streams are distributed predictably when services are added; retries and duplicate deliveries have defined behavior; access and message sizes are controlled; local and multi-service runs produce equivalent results; outputs do not repeat events after a retry.

IS013 - Similarity: Pending GitHub search; provisional Create.

* IS013 - issue_number: `{{TEMP-13}}`
* IS013 - title: `feat(topology): run workflows across multiple services`
* IS013 - state: not-created
* IS013 - labels: feature, infrastructure
* IS013 - milestone: none
* IS013 - assignees: none

### IS014 - Create - Make the project easier to set up and understand

Bring the setup guide and project documentation in line with the code. Acceptance criteria: links point to real files or planned additions; quick-start commands work with the current project; new dependencies are listed; the documentation clearly distinguishes what is available now from what is planned.

IS014 - Similarity: Pending GitHub search; provisional Create.

* IS014 - issue_number: `{{TEMP-14}}`
* IS014 - title: `docs(repo): make setup and project structure clear`
* IS014 - state: not-created
* IS014 - labels: documentation, maintenance
* IS014 - milestone: none
* IS014 - assignees: none

## Relationships

* IS002 through IS014 - sub-issues-of - `{{TEMP-1}}`: all migration work belongs to the framework epic.
<!-- markdown-table-prettify-ignore-end -->

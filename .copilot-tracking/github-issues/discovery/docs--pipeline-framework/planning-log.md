<!-- markdownlint-disable-file -->
<!-- markdown-table-prettify-ignore-start -->
# Discovery - Issue Planning Log

* **Repository**: dkirby-ms/tiger-poc
* **Milestone**: Not assigned
* **Previous Phase**: Just Started
* **Current Phase**: Phase-3 Handoff

## Status

14 candidate issues derived from 1 design document; 0 GitHub issues searched; 14 issues planned; 0 mutations performed.

**Summary**: Artifact-driven discovery is complete locally. The design was reviewed against the current checkout and converted into a provisional parent epic plus 13 child issues. Similarity and duplicate detection remain pending because GitHub read tools are unavailable in this session.

## Discovered Artifacts and Related Files

* AT001 - `docs/pipeline-framework.md` - Complete - Processing
* AT002 - `README.md` - Complete - Related
* AT003 - `requirements.txt` - Complete - Related
* AT004 - `apps/local_model_runtime/` - Complete - Related
* AT005 - `tests/` - Complete - Related
* AT006 - `docker-compose.yml` - Complete - Related

## Discovered GitHub Issues

* None searched. No GitHub API tools were available.

## Issue Progress

* IS001 - feature - Complete - Create, provisional pending duplicate search
* IS002 - maintenance - Complete - Create, provisional pending duplicate search
* IS003 - feature/infrastructure - Complete - Create, provisional pending duplicate search
* IS004 - maintenance/infrastructure - Complete - Create, provisional pending duplicate search
* IS005 - feature - Complete - Create, provisional pending duplicate search
* IS006 - feature - Complete - Create, provisional pending duplicate search
* IS007 - feature - Complete - Create, provisional pending duplicate search
* IS008 - feature - Complete - Create, provisional pending duplicate search
* IS009 - bug/breaking-change - Complete - Create, provisional pending duplicate search
* IS010 - feature/infrastructure - Complete - Create, provisional pending duplicate search
* IS011 - feature - Complete - Create, provisional pending duplicate search
* IS012 - feature - Complete - Create, provisional pending duplicate search
* IS013 - feature/infrastructure - Complete - Create, provisional pending duplicate search
* IS014 - documentation/maintenance - Complete - Create, provisional pending duplicate search

## Doc Analysis - issue-analysis.md

### `docs/pipeline-framework.md`

The document was read through the migration plan, testing strategy, decisions, and remaining risks. The backlog preserves the six migration phases and separates cross-cutting contracts, observability, documentation, and infrastructure work where those items have distinct acceptance tests.

## Review Notes

* Current code is concentrated in `apps/local_model_runtime`, not the proposed `packages/` and `services/` layout.
* Current predictive adapters accept `image`; the design proposes an `items` batch envelope.
* Current HTTP code uses `http.server`; the design proposes FastAPI.
* Current requirements do not include the proposed framework dependencies.
* Fan-in, remote delivery, retry/idempotency, and metric cardinality require decisions before implementation.

## Phase Transition Record

* Phase-1 Discover Issues: Complete
* Phase-2 Plan Issues: Complete
* Phase-3 Assemble Handoff: Complete
* GitHub mutation: Not requested and not performed.
<!-- markdown-table-prettify-ignore-end -->

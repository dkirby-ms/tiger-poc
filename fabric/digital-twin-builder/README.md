---
title: Digital Twin Builder Maintenance Runbook
description: Portal-first creation, export, versioning, refresh, and rollback for Tiger POC twins
ms.date: 2026-09-14
ms.topic: how-to
---

## Export Status

No tenant-backed digital twin builder item has been created or exported in this
repository. Therefore, `definition.json`, `EntityTypes/`,
`EntityTypeRelationships/`, `MappingOperations/`, and
`ContextualizationOperations/` are intentionally absent. Do not hand-author these
parts or treat placeholders as known-good definitions.

Live creation is blocked until every [Fabric prerequisite](../prerequisites.md) is
passed. The first committed definition must come from a validated portal export.

## Create the First Item in the Portal

1. Confirm the curated `lines`, `stations`, `process_events`, and
   `stations_current` tables contain the expected fixture rows.
2. Create a digital twin builder item and associate the approved Lakehouse.
3. Define a `Line` entity keyed by stable `lineId` and map the `lines` table with
   exact equality.
4. Define a `Station` entity keyed by stable `stationId` and map the `stations`
   table with exact equality.
5. Define `Line contains Station` and contextualize it by exact `lineId` equality
   across the two static tables.
6. Map curated `process_events` as Station time series using exact equality between
   `Station.stationId` and `process_events.stationId`.
7. Run mappings and contextualization. Verify one Line, one Station, their
   `contains` relationship, and Station process-state history in Explorer.
8. Query generated `dom` views for consumption. Never modify generated base tables.

## Export and Sanitize

1. Export the validated item definition through the supported Fabric item workflow.
2. Save the prior export outside the new version before making changes.
3. Inspect every part for credentials. Remove secrets rather than parameterizing
   them.
4. Replace workspace, Lakehouse, entity, relationship, mapping, contextualization,
   and operation IDs with documented deployment parameters where the import workflow
   supports substitution.
5. Retain the portal-generated casing and structure. Do not normalize values from
   examples because current reference documentation contains casing inconsistencies.
6. Commit `definition.json` and all exported part directories only after an import
   into the target environment validates successfully.

## Version and Refresh

Use semantic versions for the sanitized export:

* Increment patch for labels or non-semantic metadata.
* Increment minor for backward-compatible properties, mappings, or contextualization.
* Increment major for key, entity, relationship, or time-series changes that require
  migration.

For a mapping change, pause dependent refresh schedules, export the current version,
apply the non-breaking change in the portal, run mappings and contextualization, and
verify Explorer plus `dom` views before resuming schedules. Record the mapping start,
source Lakehouse availability time, and twin visibility time separately from
Eventhouse ingestion latency.

## Rollback and Recovery

1. Stop mapping and contextualization refresh schedules.
2. Preserve the failed export and its execution evidence for diagnosis.
3. Import the immediately previous sanitized, known-good export with target
   environment parameters.
4. Rerun static mappings, time-series mapping, and relationship contextualization.
5. Verify entity counts, exact keys, relationship count, process-state history, and
   generated `dom` views.
6. Resume schedules only after the owner records recovery evidence and elapsed time.

Rollback must never update generated base tables directly. Back up source Lakehouse
tables and exported item definitions according to the approved recovery objectives.

Digital twin builder remains an asynchronous analytical projection. Introduce Azure
Digital Twins as the authoritative graph only through a planned source-of-truth
transition when live graph mutation, application write APIs, or commands are needed.
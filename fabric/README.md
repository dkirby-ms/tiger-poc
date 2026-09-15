---
title: Fabric Analytics Runbook
description: Eventstream fan-out, Lakehouse curation, and validation runbook for Tiger POC
ms.date: 2026-09-14
ms.topic: how-to
---

## Data Path

The canonical v1 event remains unchanged at the edge. Eventstream accepts the event
through a custom endpoint and fans the same accepted record to Eventhouse and the
raw Lakehouse table. Digital twin builder reads curated Lakehouse tables only.

## Before Live Configuration

1. Complete [Fabric Live Prerequisites](prerequisites.md) and
   [Fabric Security and Recovery Checklist](security-checklist.md).
2. Run the prerequisite command and retain its exit code as evidence.
3. Stop if any gate is missing, invalid, denied, or unreachable.

> [!IMPORTANT]
> Live operations are currently blocked. No tenant environment or portal export is
> available, so this repository contains no claim of live Eventstream, Lakehouse, or
> digital twin builder validation.

## Create the Eventstream Fan-Out

1. In the Fabric portal, create an Eventstream item in the approved workspace.
2. Add a custom endpoint source and select the Event Hubs-compatible protocol.
3. Store endpoint credentials outside source control. Use `subjectId` as the
   partition key at publication.
4. Add an Eventhouse destination named `raw_process_events` for immediate checks.
5. Add a Lakehouse destination named `raw_process_events` for durable analytical
   processing.
6. Configure the Lakehouse transformation to flatten the canonical event fields:
   `value.state` becomes `state`, `source.runtime` becomes `sourceRuntime`, and
   `source.model` becomes `sourceModel`.
7. Add the transformation-owned `subjectType` value `Station`. Preserve the original
   `subjectId`; do not add Fabric item IDs to the wire event.
8. Preserve Eventstream metadata as `eventstreamEnqueuedAt`,
   `eventstreamPartitionId`, and `eventstreamOffset`.

## Prepare Lakehouse Tables

Create the tables before continuous ingestion. Do not rely on the first event to
infer Delta schemas because later fields can otherwise be dropped.

1. Create `raw_process_events` from
   [raw-process-events-schema.json](lakehouse/raw-process-events-schema.json).
2. Create append-only `process_events` from
   [process-events-schema.json](lakehouse/process-events-schema.json).
3. Create `stations_current` with the same curated columns, keyed by `stationId`.
4. Create `rejected_process_events` with `reason`, `eventId`, `subjectId`, and
   `detail` string columns.
5. Import [lines.csv](lakehouse/lines.csv) and
   [stations.csv](lakehouse/stations.csv) as static Delta tables.

## Run Curation

Upload the project wheel or make `src/tiger_poc` available to the Fabric notebook,
then run [curate_process_events.py](lakehouse/curate_process_events.py). The adapter
reads raw rows, delegates decisions to the tested pure-Python curation module, and
uses Delta merge keys to protect both history and current state.

Replaying an `eventId` does not append history. A sequence that does not exceed the
station's current sequence does not append history or replace current state. Rows
that cannot map exactly to `Station` are written to the rejection table.

## Validate Before Twin Mapping

1. Run [validation.kql](eventhouse/validation.kql) against the deterministic fixture.
2. Verify raw and curated table columns against both committed schemas.
3. Replay a duplicate and a stale sequence and confirm no curated change.
4. Execute the adapter in the target Fabric runtime; local validation intentionally
   does not install PySpark or Delta.
5. Record publisher-to-Eventhouse latency separately from Lakehouse-to-twin mapping
   latency.

Continue with the [digital twin builder runbook](digital-twin-builder/README.md) only
after these checks pass.

## Conditional Live Smoke Test

Run this procedure only after every prerequisite has a named owner, evidence link,
and passing status.

1. Copy the live manifest to an untracked working file and assign a unique test
   `deviceId` while keeping `schemaVersion`, mapper, partition key, and connector
   settings unchanged.
2. Set the credential environment variable named by the manifest. Do not print or
   store its value in evidence.
3. Record the UTC publication start, then run:

   ```bash
   uv run python scripts/run_pipeline.py --config pipelines/fabric-eventstream.yaml
   ```

4. In Eventhouse, identify the new record by its unique `eventId` and test
   `deviceId`. Record `emittedAt`, `eventstreamEnqueuedAt`, duplicate count, sequence,
   partition, and offset.
5. Confirm the same `eventId` reaches `raw_process_events`, then `process_events`,
   and that `stations_current` contains the expected highest sequence.
6. Run the digital twin builder mappings and record when the Station process-state
   event becomes visible. Do not edit generated base tables.
7. Calculate publisher-to-Eventhouse, Eventhouse-to-raw-Lakehouse,
   raw-to-curated-Lakehouse, and curated-Lakehouse-to-twin latency separately.
8. Compare the total publication-to-visible-twin time with the working target of
   five minutes. This target is a demo assumption, not a production SLA.

## Live Evidence Record

| Evidence | Expected result | Current status |
|----------|-----------------|----------------|
| Prerequisite command and portal approvals | Every gate passes with an owner and link | Blocked: tenant environment unavailable |
| Unique `eventId` in Eventhouse | One accepted event; duplicate query returns zero | Blocked: no live endpoint |
| Raw Lakehouse row | Same canonical identity and complete schema | Blocked: no live endpoint |
| Curated history and current state | One history row and highest valid station sequence | Blocked: no live endpoint |
| Digital twin builder visibility | Station time-series event visible after mapping | Blocked: no portal export or enabled tenant |
| Segmented latency record | Four UTC latency segments and total duration recorded | Blocked: no live observations |

## Troubleshooting Boundaries

* A local test failure belongs to the event contract, mapper, outbox, connector, or
  fixture path and must be resolved before live work.
* A prerequisite exit code of `2`, `3`, or `4` is an environment blocker, not proof
  of an application defect.
* Eventhouse success with no Lakehouse row narrows the issue to Eventstream routing,
  destination schema, or Lakehouse availability.
* A curated rejection belongs to duplicate, sequence, schema, or Station mapping
  logic. Preserve the rejected row and reason.
* Curated success with no visible twin narrows the issue to mapping execution,
  contextualization, tenant capability, or asynchronous refresh.
* Preview limits, regional availability, capacity, portal export, and SLA approval
  require Fabric owner evidence and cannot be established by offline tests.
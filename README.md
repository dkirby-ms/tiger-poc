---
title: Tiger Fabric Digital Twin POC
description: Local setup, deterministic rehearsal, and conditional Fabric smoke-test guidance
ms.date: 2026-09-14
ms.topic: overview
---

## Architecture

Tiger maps deterministic or model-derived observations to a versioned process-event
contract. A bounded SQLite outbox protects remote publication. Fabric Eventstream
fans accepted events to Eventhouse and Lakehouse; digital twin builder maps curated
Lakehouse tables asynchronously.

Fabric is not a device registry or an edge queue. The connector is transport-only,
and preview Fabric twins are non-authoritative. See [MVP Design](docs/mvp-design.md)
and [Production Evolution](docs/production-evolution.md) for the boundaries and
decision triggers.

## Local Setup

Install Python 3.11 and `uv`, then create the project environment:

```bash
uv sync --group dev
```

No Fabric credential is required for local execution. The offline manifest writes
canonical JSON Lines output under `.data/`.

## Deterministic Local Demo

From the repository root, run:

```bash
uv run python scripts/run_pipeline.py --config pipelines/local-demo.yaml
```

Expected terminal output:

```text
Published 1 process event(s)
```

The command appends one canonical event to `.data/local-demo-events.jsonl`. Archive
or remove that generated file before a clean rehearsal because the local sink is
append-only.

## Offline Validation

Run formatting, lint, and the focused pipeline suite:

```bash
uv run ruff format --check tests/test_pipeline.py
uv run ruff check tests/test_pipeline.py
uv run pytest -q tests/test_pipeline.py
```

The edge/cloud acceptance test uses the same deterministic frames, mapper, outbox
contract, and connector implementation. It requires schema version `1.0` and the
same nested payload keys and value types. Runtime and model-derived values may differ.

## Fabric Configuration

The live manifest is [pipelines/fabric-eventstream.yaml](pipelines/fabric-eventstream.yaml).
It names environment variables but contains no secret values. Connection-string mode
reads `FABRIC_EVENTSTREAM_CONNECTION_STRING`. Managed-identity deployments instead
use the namespace and event hub variable names defined by the strict configuration
model.

Complete [Fabric Live Prerequisites](fabric/prerequisites.md) before any live action:

```bash
uv run python scripts/check_fabric_prerequisites.py --probe-tls
```

> [!WARNING]
> Live validation is currently blocked because no tenant environment or portal
> export is available. A passing local run proves code behavior only. It does not
> prove Fabric region, capacity, access, networking, mapping, or twin visibility.

## Conditional Live Demo

When every prerequisite is evidenced, follow the
[Fabric Analytics Runbook](fabric/README.md). Publish one uniquely identified fixture
through the custom endpoint and retain evidence for Eventhouse, raw Lakehouse,
curated Lakehouse, and digital twin builder. Record each latency segment separately;
do not report the five-minute working demo target as a production SLA.

## Cleanup

Local cleanup is limited to generated artifacts:

* Archive or remove `.data/local-demo-events.jsonl` after evidence is retained.
* Preserve `.data/tiger-outbox.db` until all queued events are acknowledged or an
  approved loss decision is recorded.

Live cleanup is conditional on tenant access. Remove test routes, destinations,
tables, and twin items only after exporting required evidence and confirming that no
shared resource depends on them. Revoke temporary SAS credentials or role assignments
through the owning secret and identity systems.
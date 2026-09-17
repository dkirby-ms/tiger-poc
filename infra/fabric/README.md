---
title: Signed-In Fabric Bootstrap
description: Provision Fabric items, initialize mappings, and resume safely.
---

## Scope

[deploy.py](deploy.py) provisions an Eventhouse, KQL database, two lakehouses,
Eventstream, digital twin, and three mapping flows using your Azure CLI user login.
It does not create a workspace, capacity, credentials, or role assignments.
For local detection, publishing, and dashboards, use the [root guide](../../README.md).

> [!IMPORTANT]
> `apply` creates definitions and reference data, not running publishers or twin
> instances. Earlier presence definitions were tested through staged imports;
> a fresh complete import, QR integration, ingestion, and mapping execution still
> need live validation. Provisioning and flow execution consume Fabric capacity.

## Prerequisites

* New or manually cleared workspace on active, supported capacity; Contributor or higher access
* Digital twin builder preview enabled; its flows do not support Autoscale Billing for Spark
* Python 3.11+, `uv`, and Azure CLI with an interactive user login, not a service principal

The script checks capacity assignment, not capacity health or effective permissions.
Complete authentication privately; never put tokens or connection strings in config or logs.

## Plan And Apply

Run from the repository root:

```bash
az login --tenant "<tenant-id>" --allow-no-subscriptions
uv run infra/fabric/deploy.py plan
uv run infra/fabric/deploy.py apply --workspace "<workspace-id>" --tenant "<tenant-id>"
uv run infra/fabric/deploy.py status --workspace "<workspace-id>" --tenant "<tenant-id>"
```

`plan` lists items and validates artifacts without cloud calls; `uv` may download
dependencies. `status` requires an existing checkpoint and reports inventory and
raw-event freshness, not end-to-end health. [config.json](config.json) controls
names, artifact paths, presence types, and OneLake latency; use `--config` to override.

### WSL With An Approved Package Feed

When required, configure the approved feed before running `uv`:

```bash
export UV_PYTHON="$(command -v python3)"
export UV_PYTHON_DOWNLOADS=never
export UV_DEFAULT_INDEX=https://packagefeedproxy.microsoft.io/pypi/simple
```

Use an approved installed Python 3.11+ and no unapproved fallback indexes.
For the reproduced WSL TLS handshake issue, add `--tls12` to `apply` or `status`.
It retains certificate verification and affects only the Fabric/KQL HTTP client,
not Azure CLI, `uv`, or the OneLake SDK.

## Publish And Initialize

With the default `tiger` prefix:

1. Open `tiger_ingest` > `CameraEvents` and privately configure the
   [publishers](../../README.md#publish-events) with its Custom App credentials.
   Azure CLI login does not authorize publishing to that source.
2. Verify destination `ProcessEventsRaw` in `tiger_events_db` preserves top-level
   JSON fields. Start publishing and check the [sample queries](../../apps/fabric/kql/03_sample_queries.kql).
3. Wait for both `ConfirmedPresenceEvents` and `BoxIdentificationEvents` to be
   readable through `tiger_reference` OneLake shortcuts. Empty tables may not be
   ready; publish valid events and retry incomplete setup with the same checkpoint.
   Do not insert synthetic occupancy merely to initialize a table.
4. Run `tiger_reference_flow`, then `tiger_relationships_flow`, waiting after each.
   Verify 1 plant, 3 cells, 5 positions, 3 cases, and 3 relationship types.
   Run `tiger_timeseries_flow` and verify timestamps and mapped history before scheduling.
5. Import and configure the [dashboard](../../README.md#dashboard); bootstrap does not deploy it.

## Optional Job API

Prefer portal execution until a supported Digital twin builder job type is
confirmed for your tenant. `run` and `schedule` are unverified adapters; do not
guess a job type. Once confirmed:

```bash
uv run infra/fabric/deploy.py run --workspace "<workspace-id>" \
  --job-type "<confirmed-job-type>" --phase reference
uv run infra/fabric/deploy.py run --workspace "<workspace-id>" \
  --job-type "<confirmed-job-type>" --phase events
uv run infra/fabric/deploy.py schedule --workspace "<workspace-id>" \
  --job-type "<confirmed-job-type>" --interval 15 --until "<future-UTC-timestamp>"
```

Scheduling requires successful API-managed reference and event runs, a future
expiration, and a 15-720 minute interval. Portal runs do not satisfy those
checkpoints. Only time-series mapping is scheduled. Avoid overlapping runs;
inspect Fabric after an interrupted schedule request before retrying.

## State And Recovery

Keep `data/fabric/<workspace-id>.json` across retries; `--state` overrides its path.
Run one deployment process per workspace. Repeating `apply` with unchanged artifacts
and state skips completed work. Reference loads replace owned reference tables,
not event history.

Changed fingerprints, name collisions, and missing owned items stop deployment.
There is no adoption, automatic migration, rollback, or deletion. Inspect Fabric
after timeouts before retrying: creation may have completed remotely. Never discard
state to bypass a conflict. Use the [migration steps](../../README.md#existing-deployments)
for existing deployments; use a separate prefix and state file for a replacement model.

### Import Failure Diagnostics

For a failed import, retain the checkpoint and add diagnostics to the same `apply` arguments:

```bash
uv run infra/fabric/deploy.py apply --workspace "<workspace-id>" --tls12 \
   --diagnostics-dir data/fabric/diagnostics
```

This can create remaining items; it is not read-only. Do not repeat unchanged,
non-retriable failures. Diagnostics exclude request bodies and authentication
headers but can contain sensitive service details; keep them private and out of git.
KQL and OneLake SDK failures are not captured. Preserve operation IDs for support.

## Verification And API References

For KQL connection errors, check DNS, proxy/VPN, HTTPS port 443, and certificates
for the database Query URI. Never disable TLS verification. Resume with the same
checkpoint after restoring connectivity.

```bash
PYTHONPATH=.:apps/detect uv run --project apps/detect --extra fabric --with azure-storage-file-datalake --with httpx \
  python -m pytest infra/fabric/tests apps/detect/tests/test_fabric.py apps/detect/tests/test_fabric_contracts.py -q
uv run --project apps/detect ruff check infra/fabric
```

Tests validate artifacts and mocked deployment/resume, not live Fabric behavior.
See Microsoft's [twin definition contract](https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/digital-twin-builder-definition)
and [job API](https://learn.microsoft.com/rest/api/fabric/core/job-scheduler/run-on-demand-item-job).

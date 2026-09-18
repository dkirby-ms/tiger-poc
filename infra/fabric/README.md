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
> Automatic initialization is currently blocked in the tested workspace: on
> 2026-09-17, Fabric rejected `ExecuteOperations` with HTTP 400 `InvalidJobType`.
> Use `--definitions-only` for provisioning without mappings. This is not complete
> twin initialization. Provisioning and flow execution consume capacity.

## Prerequisites

* New or manually cleared workspace on active, supported capacity; Contributor or higher access
* Digital twin builder preview enabled; its flows do not support Autoscale Billing for Spark
* Python 3.11+, `uv`, and Azure CLI with an interactive user login, not a service principal

The script checks capacity assignment, not capacity health or effective permissions.
Complete authentication privately; never put tokens or connection strings in config or logs.

### Check And Resume Capacity

Before running `apply`, check that the assigned Fabric capacity is active. Replace
the resource group and capacity name with your environment:

```bash
export RESOURCE_GROUP="rg-fabric-cus"
export CAPACITY_NAME="cusf4"

CAPACITY_ID=$(az fabric capacity show \
   --resource-group "$RESOURCE_GROUP" \
   --capacity-name "$CAPACITY_NAME" \
   --query id \
   -o tsv)
CAPACITY_STATE=$(az fabric capacity show \
   --ids "$CAPACITY_ID" \
   --query properties.state \
   -o tsv)

printf 'Fabric capacity state: %s\n' "$CAPACITY_STATE"
```

`Active` means the capacity is running. If the reported state is not `Active`,
resume it and verify the resulting state:

```bash
if [[ "$CAPACITY_STATE" != "Active" ]]; then
   az fabric capacity resume --ids "$CAPACITY_ID"
   az fabric capacity show \
      --ids "$CAPACITY_ID" \
      --query "{name:name, state:properties.state}" \
      -o table
fi
```

The resume operation can take time to complete. Rerun the state check and wait
for `Active` before starting the bootstrap.

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

With a supported execution job type, `apply` waits for OneLake source tables,
runs reference mappings, relationships,
then event history, and waits for completion after each stage. Repeat the same
command after an interruption: completed stages are skipped and recorded active
jobs are polled, not resubmitted. `--timeout` bounds each wait (default: 1800 seconds).
Use `--definitions-only` to provision without running mappings.

After provisioning, `apply` generates `<checkpoint-stem>.dashboard.json` beside
the checkpoint, including when `--definitions-only` is used. The default output
is `data/fabric/<workspace-id>.dashboard.json`. It reads the deployed database's
query endpoint and fills in the workspace and database IDs while preserving all
query bindings. The shared template remains unchanged. Repeating `apply`
regenerates the file; back up any local customizations first. Import this generated
file into Fabric; the command does not create or replace a cloud dashboard.

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

The automatic sequence below requires resolving the job-type blocker above.
With a supported execution job type, leave `apply` running while configuring
publishing in another terminal. With the default `tiger` prefix:

1. Open `tiger_ingest` > `CameraEvents` and privately configure the
   [publishers](../../README.md#publish-events) with its Custom App credentials.
   Azure CLI login does not authorize publishing to that source.
2. Verify destination `ProcessEventsRaw` in `tiger_events_db` preserves top-level
   JSON fields. Start publishing and check the [sample queries](../../apps/fabric/kql/03_sample_queries.kql).
3. `apply` waits for `ConfirmedPresenceEvents` and `BoxIdentificationEvents` through
   `tiger_reference` OneLake shortcuts and runs the three flows automatically.
   Empty tables may not be ready; publish valid events for both scenarios. On a
   readiness timeout, fix ingestion and repeat `apply` with the same checkpoint.
   Do not insert synthetic occupancy merely to initialize a table.
4. After setup completes, verify 1 plant, 3 cells, 5 positions, 3 cases, and
   3 relationship types, then inspect mapped event timestamps.
5. Import and configure the [dashboard](../../README.md#dashboard); bootstrap does not deploy it.

## Optional Job API

The orchestration code sequences flows without separate commands, but public
execution is not yet working in the tested workspace. After a supported job type
is confirmed, these advanced commands refresh mappings or schedule history updates:

```bash
uv run infra/fabric/deploy.py run --workspace "<workspace-id>" \
   --phase all
uv run infra/fabric/deploy.py schedule --workspace "<workspace-id>" \
   --interval 15 --until "<future-UTC-timestamp>"
```

The current default, `ExecuteOperations`, comes from
[Microsoft's monitoring-log reference](https://learn.microsoft.com/fabric/fundamentals/item-job-event-logs#supported-item-and-job-types),
not an execution contract. The live API rejected it as `InvalidJobType`;
monitoring job names do not establish public execution support. Do not retry it
unchanged or guess replacement names. A supported public execution contract must
be confirmed before this workflow can complete. `--job-type` remains an override
for a confirmed type. Scheduling also needs tenant validation.

Scheduling requires successful API-managed reference and event runs, a future
expiration, and a 15-720 minute interval. Portal runs do not satisfy those
checkpoints. Only time-series mapping is scheduled. Avoid overlapping runs;
inspect Fabric after an interrupted schedule request before retrying.

## State And Recovery

Keep `data/fabric/<workspace-id>.json` across retries; `--state` overrides its path.
Run one deployment process per workspace; do not overlap setup with portal runs.
Repeating `apply` with unchanged artifacts and state skips completed work.
Reference loads replace owned reference tables,
not event history.

Changed fingerprints, name collisions, and missing owned items stop deployment.
There is no adoption, automatic migration, rollback, or deletion. Inspect Fabric
after timeouts before retrying: creation may have completed remotely. Never discard
state to bypass a conflict. Use the [migration steps](../../README.md#existing-deployments)
for existing deployments; use a separate prefix and state file for a replacement model.

If a job submission's response is lost, setup stops rather than risking duplicate
execution. Inspect Fabric job history and reconcile the recorded `Submitting`
stage before retrying. Keep the checkpoint; do not reset it to bypass this guard.

Explicit HTTP submission rejections are recorded as `Rejected`, not `Submitting`.
Fix their cause before retrying. Error output includes the service error code and
request ID when available; diagnostics retain the full private response.

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

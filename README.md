---
title: Tiger Perception POC
description: Run camera-based presence and QR examples locally, then publish events to Microsoft Fabric.
---

## Overview

Run RTSP presence and QR detection with a local browser viewer. Optionally publish
JSONL events to Fabric Eventstream and Eventhouse for dashboards and twin history.

| Example | Manifest | Event |
|---------|----------|-------|
| Cell A Jeep | [cell-a-jeep.yaml](apps/detect/manifests/cell-a-jeep.yaml) | `ObjectPresent` |
| Cell C QR boxes | [cell-c-qr.yaml](apps/detect/manifests/cell-c-qr.yaml) | `BoxIdentified` |
| Cell A / B chairs | [cell-a.yaml](apps/detect/manifests/cell-a.yaml), [cell-b.yaml](apps/detect/manifests/cell-b.yaml) | `ObjectPresent` |
| Cell B pallets | [cell-b-pallet.yaml](apps/detect/manifests/cell-b-pallet.yaml) | `PalletPresent` |

Compose runs Jeep and QR; chairs and pallets are alternatives. Pallets require
trusted custom weights. The bundled YOLO model does not support pallets.

## Run Locally

Use Linux/WSL, Docker Engine, and Compose. Run commands from the repository root.
Privately set `CAMERA_A_RTSP_URL` and `CAMERA_C_RTSP_URL` in gitignored `apps/.env`.
Use complete RTSP URLs with camera LAN addresses, not container-local `localhost`.
Never commit credentials.

```bash
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
mkdir -p data
docker compose --env-file apps/.env -f apps/docker-compose.yml up --build -d
```

Open <http://127.0.0.1:8765> and select a Scenario. Set `VIEWER_PORT` if occupied.
Selection does not stop containers. Keep the unauthenticated viewer on loopback.

```bash
docker compose --env-file apps/.env -f apps/docker-compose.yml logs -f detect detect-qr
docker compose --env-file apps/.env -f apps/docker-compose.yml down
```

Export UID/GID in each shell and ensure your user can write `data/`. Jeep and QR
events go to `data/cell-a/jeep-events.jsonl` and `data/cell-c/events.jsonl`, with
status and previews beside them. Never run two detectors against the same outputs.
Builds need the approved package feed, Docker Hub, GHCR, and Debian access.

### Without Docker

Install Python 3.14+ and `uv`. Start the detector, then the viewer in another terminal:

```bash
uv sync --project apps/detect
uv run --project apps/detect apps/detect/rtsp_yolo.py --manifest apps/detect/manifests/cell-c-qr.yaml --env-file apps/.env
```

```bash
uv run --directory apps/detect python -m tiger_perception.viewer --manifest manifests/cell-c-qr.yaml --port 8765
```

Add `--check` for camera-free preflight; stop with `Ctrl+C`. Substitute manifests
for other examples; Cell B needs `CAMERA_B_RTSP_URL`. A viewer accepts two manifests.

## Configuration And Evidence

Configure camera, provider, timing, region, and outputs in the [manifest](apps/detect/manifests).
Paths are manifest-relative. Use distinct outputs and source/subject IDs per workload.
`region.bounds` uses normalized `[left, top, right, bottom]`, matching box centers.

* Presence emits initial state and confirmed transitions, not every frame.
* Failed/stale evidence means unavailable, not empty. Events are not health heartbeats.
* QR accepts `CASE-` plus three ASCII digits. Use the [printable labels](docs/inventory-labels/index.html).
  Codes must face the camera and remain legible. Tape and physical box outlines are not detected.
* Cases confirm independently. Continuous visibility emits once; missed reads rearm
  identification, not departure. QR history is not current inventory.
* QR confidence `1.0` means decoded payload, not probability. Empty-presence confidence is `0.0`.
* Restarts can emit new initial events. Delivery is at-least-once; deduplicate by
  `eventId`. Keep timestamps and the [event contract](apps/detect/tiger_perception/schemas/process-event-v1.json).

## Fabric Setup

For a new workspace on supported capacity, use the [Fabric bootstrap](infra/fabric/README.md).
`plan` is offline. `apply` provisions items and attempts ordered twin mapping
initialization, but live execution is currently blocked by Fabric's
`InvalidJobType` rejection of `ExecuteOperations`; see the
[bootstrap guide](infra/fabric/README.md#optional-job-api).
Use `--definitions-only` for provisioning without mappings. Keep the checkpoint;
do not repeat the rejected job type unchanged. Publishers are configured separately.
Digital twin builder requires preview access. Existing deployments need migration below.

For manual setup, create an Eventhouse/KQL database and execute each complete command
block separately, in order: [tables and seeds](apps/fabric/kql/01_create_tables.kql),
then [typed policies and views](apps/fabric/kql/02_update_policy.kql). Seed once;
expect 1 plant, 3 cells, 5 positions, and 3 cases. Wait for async view creation to finish.

Send the Eventstream Custom App source to `ProcessEventsRaw`, preserving JSON fields.
The named JSON mapping does not configure Eventstream mappings. Alternatively, use
[Azure Event Hubs](infra/digital-twin-poc/README.md).

| Event | Typed history | Latest evidence |
|-------|---------------|-----------------|
| `ObjectPresent` / `PalletPresent`, boolean value | `ConfirmedPresenceEvents` | `CurrentPositionOccupancy` |
| `BoxIdentified`, case ID string | `BoxIdentificationEvents` | `LastCaseIdentification` |

QR uses case ID in `subjectId`/`value` and area in `observation.positionId`, never occupancy.
The [twin design](apps/fabric/digital_twin/ontology_definition.json) maps typed history
through OneLake, not latest-state views. Plant registration is not location;
case IDs must be globally unique in this POC.

### Existing Deployments

Do not rerun all seeds or bypass the bootstrap's fingerprint guard by deleting its
checkpoint. Existing deployments need explicit portal/API migration:

1. Pause publishers and drain or pause ingestion. Preserve event files and checkpoints.
2. Add only missing Cell C and case references from the table script. Create the QR
   table, extraction function, and update policy from the policy script; leave presence unchanged.
3. Update policies do not copy old raw history. If needed, run
   `.set-or-append BoxIdentificationEvents <| ExtractBoxIdentifications()` once while
   ingestion is paused, then create `LastCaseIdentification` and wait for backfill.
4. Enable OneLake availability and the QR history shortcut, update reference tables
   and Case mappings, then run reference mappings before history mappings.
5. Back up and replace the dashboard, verify queries, and resume publishers. Deduplicate replayed events.

### Publish Events

Privately place the Custom App source connection string in
`apps/secrets/fabric-connection-string`. Keep it readable only by the configured user;
local Compose secrets are not an encrypted secret store. Both Compose files are required:

```bash
docker compose --env-file apps/.env -f apps/docker-compose.yml -f apps/docker-compose.fabric.yml --profile fabric up --build -d
docker compose --env-file apps/.env -f apps/docker-compose.yml -f apps/docker-compose.fabric.yml --profile fabric logs -f publisher publisher-qr
```

The two publishers share a destination but use independent `publisher-state` and
`publisher-qr-state` volumes. First runs send the existing backlog. Failures stop
publishing after bounded retries; fix the cause and rerun `up` to resume.

```bash
docker compose --env-file apps/.env -f apps/docker-compose.yml -f apps/docker-compose.fabric.yml --profile fabric down
```

Never use `down -v` for normal restarts. Do not truncate or replace followed files,
share checkpoints, or reuse delivery state for another destination. Reconcile
acknowledged events before changing inputs or resetting state.

For a host relay, install the `fabric` extra and configure
`FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE` privately; the relay does not load
`apps/.env`. Azure Event Hubs also supports `FABRIC_EVENTSTREAM_NAMESPACE` and
`FABRIC_EVENTSTREAM_EVENTHUB_NAME` with `DefaultAzureCredential` and a sender role.
Check [relay options](apps/detect/tiger_perception/fabric.py) with `--help`.

### Dashboard

`apply` generates `data/fabric/<workspace-id>.dashboard.json` with the deployed
database connection already bound to all ten queries. With `--state`, the output
is named `<checkpoint-stem>.dashboard.json` beside that checkpoint. Use
`--definitions-only` to provision and export without executing twin flows.

Back up an existing dashboard, then use **Manage > Replace with file** to import
the generated file, not the generic
[source template](apps/fabric/dashboards/fabric_realtime_dashboard.json).
Verify all ten tiles across both pages before saving or enabling refresh.
The source template stays portable; generated files contain deployment identifiers,
not credentials. For manual setup, edit the template's existing data source and
preserve its ID; adding another source does not rebind the queries.

Use [sample KQL](apps/fabric/kql/03_sample_queries.kql) for event inspection or
[Power BI DirectQuery](apps/fabric/dashboards/powerbi_directquery_kql.m) for occupancy.
QR tiles show identification history, not stock. Set your endpoint/database before querying.

## Validation And Troubleshooting

```bash
uv run --project apps/detect --extra fabric python -m pytest apps/detect/tests -q
uv run --project apps/detect ruff check apps/detect
uv run --directory apps/detect --extra fabric python -m tiger_perception.fabric --demo --dry-run
```

QR Fabric integration needs live validation; offline tests do not prove camera,
KQL, dashboard, or twin behavior. Some tests reference a missing root manifest.
See the [validation record](docs/milestone-1-validation.md) for physical test gaps.

* No frames: check RTSP path, credentials, camera session limits, routing, and codec.
* Stale evidence: check lighting, focus, frame age, and compute load before relaxing thresholds.
* Output locked or unwritable: stop the competing owner and verify host UID/GID and permissions.
* Publisher stopped: inspect logs, secret permissions, input integrity, and checkpoint state.
* Missing KQL table: confirm the selected database with `.show tables`; create it before seeding.
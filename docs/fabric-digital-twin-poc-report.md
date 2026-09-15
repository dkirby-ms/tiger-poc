---
description: Historical POC report with current detect execution commands and artifact ownership.
---

# Factory Edge Perception to Microsoft Fabric POC Report

**Date:** 2026-09-15  
**Workload:** Portable Factory Perception MVP (Milestone 2 - Microsoft Fabric & Digital Twin Integration)  
**Branch:** `feature/fabric-digital-twin-poc`  

---

## Executive Summary

> [!NOTE]
> Architecture and service verification claims below describe the original POC.
> For current contracts, setup limitations and supported commands, use the
> [detect guide](../apps/detect/README.md) and [Fabric guide](../apps/fabric/README.md).

This document details the research, architecture planning, and implementation of connecting edge manufacturing perception workloads to **Microsoft Fabric Real-Time Intelligence**. 

The solution enables localized computer vision pipelines (or non-video equipment sensors) across multiple factory cells to stream standardized `ProcessEvent` records to Fabric, continuously update a **Digital Twin Builder** ontology graph (`Plant` $\rightarrow$ `Cell` $\rightarrow$ `PalletPosition`), and render near real-time operational status on sub-second **Fabric Real-Time Dashboards** and **Power BI DirectQuery** reports.

---

## 1. Research & Architectural Decisions

### 1.1 Ingestion & Transport Connectivity
* **Standardization:** Process observations adhere to the versioned `process-event-v1.json` schema, encapsulating `eventId`, `sourceId`, `subjectId`, `observationType: PalletPresent`, boolean `value`, `confidence`, timestamps, and plant/cell metadata.
* **Hybrid Connectivity Pattern:** Edge nodes communicate with Fabric through a dual-mode `FabricEventstreamSink`:
  1. **Production Mode:** AMQP / HTTPS directly to Fabric Eventstream (via Azure Event Hubs endpoint or Eventstream REST URL).
  2. **Dry-Run / Local Mode:** Validates schema, logs structured output to console, and mirrors events to local JSON Lines (`.jsonl`) files when cloud credentials are not present.

### 1.2 Fabric Eventhouse & Digital Twin Model
* **Eventhouse / KQL Database:** 
  - `ProcessEventsRaw`: Ingests streaming payloads.
  - `CurrentPalletOccupancy`: Materialized view maintaining the latest confirmed boolean occupancy per position using `arg_max(capturedAt, *)`.
  - Static Reference Hierarchy: `Plants` $\rightarrow$ `Cells` $\rightarrow$ `PalletPositions`.
* **Digital Twin Builder (Preview):** 
  - Defined an ontology where `Plant` `containsCell` `Cell`, and `Cell` `monitorsPosition` `PalletPosition`.
  - Telemetry binding maps `ProcessEventsRaw.subjectId` to `PalletPosition.palletPositionId` to update `isOccupied`, `confidence`, and `lastObservedTimestamp`.

### 1.3 Real-Time Visualization
* **Fabric Real-Time Dashboard:** Low-latency, zero-DAX configuration with 5-second auto-refresh visualizing position counts, occupancy percentage, live status matrix, transition event logs, and edge-to-cloud ingestion latency.
* **Power BI DirectQuery (KQL):** M query script for Power BI Desktop with Automatic Page Refresh (APR).

---

## 2. Directory Structure & Artifact Inventory

The workspace is organized into clean functional modules:

```text
tiger-poc/
├── docs/
│   ├── mvp-design.md                     # Base MVP specification
│   ├── demo-script.md                    # 2-minute partner demo script
│   └── fabric-digital-twin-poc-report.md # Research, planning & implementation report (this document)
│
├── infra/
│   └── digital-twin-poc/                 # Infrastructure as Code (Bicep)
│       ├── main.bicep                    # Event Hubs namespace, topics & Managed Identity orchestration
│       ├── main.bicepparam               # Parameter file for dev environment
│       ├── types.bicep                   # Shared Bicep type definitions
│       ├── modules/
│       │   ├── eventhub.bicep            # Event Hubs resource & Send/Listen SAS policies
│       │   └── identity.bicep            # User-Assigned Managed Identity
│       └── README.md                     # IaC deployment guide
│
└── apps/
    ├── detect/                           # Detection, canonical contracts and optional Fabric relay
    │   ├── pyproject.toml                # Detection dependencies and optional fabric extra
    │   ├── README.md                     # Camera execution and Fabric relay guide
    │   ├── manifests/
    │   │   ├── cell-a.yaml               # Cell A household-object trial
    │   │   ├── cell-b.yaml               # Cell B household-object trial
    │   │   └── cell-b-pallet.yaml        # Cell B pallet model template
    │   ├── tiger_perception/
    │   │   ├── __init__.py
    │   │   ├── contracts.py              # Typed ProcessEvent and Observation dataclasses
    │   │   ├── presence.py               # Stateful presence rule (confirmation windows & suppression)
    │   │   ├── sinks.py                  # Canonical validation and LocalJsonlSink
    │   │   ├── fabric.py                 # Fabric publisher, JSONL relay and multi-cell demo
    │   │   ├── replay.py                 # Local event replay
    │   │   ├── runner.py                 # Manifest-driven pipeline runner
    │   │   └── schemas/
    │   │       └── process-event-v1.json # ProcessEvent JSON Schema
    │   └── tests/                        # Full unit test suite (contracts, rules, sinks, replay)
    │
    └── fabric/                           # Microsoft Fabric & Real-Time Intelligence Artifacts
        ├── README.md                     # Step-by-step Fabric setup guide
        ├── kql/
        │   ├── 01_create_tables.kql      # Raw streaming table, reference tables (Plant/Cell/Position)
        │   ├── 02_update_policy.kql      # Materialized views & continuous state aggregations
        │   └── 03_sample_queries.kql     # Current state, transition history, and latency queries
        ├── digital_twin/
        │   ├── ontology_definition.json  # Digital Twin Builder ontology (Plant -> Cell -> Position)
        │   └── twin_instances.json       # Seed twin instance graph
        └── dashboards/
            ├── fabric_realtime_dashboard.json # Fabric Real-Time Dashboard configuration (5s auto-refresh)
            └── powerbi_directquery_kql.m      # Power BI DirectQuery KQL connector & setup
```

---

## 3. Implementation Verification & Test Results

### 3.1 Unit Testing
The original POC recorded nine passing tests for its former standalone prototype.
That historical result is not a verification of the current implementation.
The supported suite in [apps/detect/tests](../apps/detect/tests) covers contracts,
presence rules, Fabric publishing and multi-cell replay. After consolidation,
91 tests passed locally; live Fabric delivery and KQL execution remain unverified.

### 3.2 Bicep Compilation & IaC Linting
Bicep templates compile cleanly to ARM JSON without warnings:

```bash
bicep build infra/digital-twin-poc/main.bicep -> Success (0 diagnostics)
```

---

## 4. Operational Execution Instructions

### 4.1 Infrastructure Deployment (Azure CLI & Bicep)

Provision the Azure Event Hubs namespace, authorization policies, and User-Assigned Managed Identity that serve as the ingestion bridge for Microsoft Fabric Eventstream:

```bash
# 1. Set environment variables
export RESOURCE_GROUP="rg-tiger-edge-dev"
export LOCATION="eastus"

# 2. Create the resource group (if not already existing)
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}"

# 3. Validate and preview the Bicep deployment (What-If)
az deployment group what-if \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file infra/digital-twin-poc/main.bicep \
  --parameters infra/digital-twin-poc/main.bicepparam

# 4. Deploy the infrastructure
az deployment group create \
  --name "deploy-tiger-edge-$(date +%s)" \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file infra/digital-twin-poc/main.bicep \
  --parameters infra/digital-twin-poc/main.bicepparam

# 5. Extract output connection strings for edge configuration
EDGE_CONNECTION_STRING=$(az deployment group show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "deploy-tiger-edge-$(date +%s)" \
  --query "properties.outputs.edgeEventHubConnectionString.value" -o tsv)

echo "Edge Producer Connection String: ${EDGE_CONNECTION_STRING}"
```

### 4.2 Running Detection And Publisher Tests

Run unit tests across edge contracts, presence evaluation rules, sinks, and replay generators:

```bash
uv run --project apps/detect --extra fabric pytest apps/detect/tests
```

### 4.3 Running Edge Simulation (Dry-Run Mode)

Simulate cell A object and cell B pallet presence transitions locally with schema
validation and JSONL trace output:

```bash
# Dry-run to local file and stdout logs
uv run --directory apps/detect --extra fabric python -m tiger_perception.fabric \
  --demo --dry-run \
  --output ../../data/simulation.jsonl \
  --interval 1.0 \
  --iterations 1
```

### 4.4 Running Live Ingestion to Microsoft Fabric

Stream confirmed process events directly into Microsoft Fabric Eventstream over the Event Hub / AMQP endpoint:

```bash
# Set Fabric Eventstream / Azure Event Hub connection string
export FABRIC_EVENTSTREAM_CONNECTION_STRING="${EDGE_CONNECTION_STRING}"

# Run live streaming simulation
uv run --directory apps/detect --extra fabric python -m tiger_perception.fabric \
  --demo \
  --live-fabric \
  --interval 2.0 \
  --iterations 5
```

### 4.5 Running Edge Pipeline with Workload Manifests

Launch these camera workloads in separate terminals. They write local JSONL;
Fabric publication is a separate relay step, not a camera-runner flag.

```bash
# Launch Cell A workload
uv run --project apps/detect apps/detect/rtsp_yolo.py \
  --manifest apps/detect/manifests/cell-a.yaml --env-file apps/.env

# Launch Cell B workload
uv run --project apps/detect apps/detect/rtsp_yolo.py \
  --manifest apps/detect/manifests/cell-b.yaml --env-file apps/.env
```

After stopping the workloads, relay their completed event files with the destination
configured in the process environment:

```bash
uv run --directory apps/detect --extra fabric python -m tiger_perception.fabric \
  --input ../../data/cell-a/events.jsonl ../../data/cell-b/events.jsonl \
  --live-fabric
```

### 4.6 Setting up Microsoft Fabric Eventhouse & Digital Twin

1. **Create Fabric Eventstream:**
   - In your Fabric workspace, select **New** -> **Eventstream**.
   - Add a **Custom App** source (or select **Azure Event Hubs** using the connection string from step 4.1).
   - Add a destination targeting your Fabric **KQL Database** / Eventhouse. Table name: `ProcessEventsRaw`.

2. **Execute KQL Setup Scripts:**
   - Open your Fabric KQL Database Queryset and execute in order:
     - [apps/fabric/kql/01_create_tables.kql](../apps/fabric/kql/01_create_tables.kql) (creates `ProcessEventsRaw`, reference tables `Plants`, `Cells`, `PalletPositions`).
     - [apps/fabric/kql/02_update_policy.kql](../apps/fabric/kql/02_update_policy.kql) (creates materialized view `CurrentPalletOccupancy`).
     - [apps/fabric/kql/03_sample_queries.kql](../apps/fabric/kql/03_sample_queries.kql) (test queries).

3. **Configure Digital Twin Builder (Preview):**
   - In Fabric Real-Time Intelligence, navigate to **Digital Twin Builder**.
   - Import the ontology model from [apps/fabric/digital_twin/ontology_definition.json](../apps/fabric/digital_twin/ontology_definition.json).
   - Import graph instance seeds from [apps/fabric/digital_twin/twin_instances.json](../apps/fabric/digital_twin/twin_instances.json).
   - Map streaming telemetry from table `ProcessEventsRaw` (`subjectId` -> `palletPositionId`) to update `isOccupied`, `confidence`, and `lastObservedTimestamp`.

4. **Deploy Real-Time Visualizations:**
   - **Fabric Real-Time Dashboard:** Create a new Real-Time Dashboard and import [apps/fabric/dashboards/fabric_realtime_dashboard.json](../apps/fabric/dashboards/fabric_realtime_dashboard.json) (configured for 5-second automatic refresh).
   - **Power BI Desktop:** Open Power BI Desktop, choose **Get Data** -> **Fabric KQL Database**, select **DirectQuery** mode, paste the query from [apps/fabric/dashboards/powerbi_directquery_kql.m](../apps/fabric/dashboards/powerbi_directquery_kql.m), and enable **Automatic Page Refresh** on 5-second intervals.

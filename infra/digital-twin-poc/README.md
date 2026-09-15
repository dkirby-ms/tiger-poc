# Factory Edge to Microsoft Fabric Infrastructure

This directory contains Bicep Infrastructure-as-Code templates for provisioning supporting Azure connectivity resources that bridge factory edge perception workloads into Microsoft Fabric Eventstream.

## Architecture

```text
[Edge Workload / Replay Simulator]
        |
        | HTTPS / AMQP (Send Policy)
        v
[Azure Event Hubs / Custom Endpoint]
        |
        | Eventstream Source Connector (Listen Policy)
        v
[Microsoft Fabric Eventstream]
        |
        +---> [Fabric Eventhouse / KQL Database] ---> [Real-Time Dashboard & Power BI]
        |
        +---> [Fabric Digital Twin Builder (Ontology)]
```

## Resources Deployed

- **Azure Event Hubs Namespace (`Standard`) & Event Hub (`process-events`)**: Ingestion point for custom edge application events.
- **Authorization Rules**:
  - `EdgeSenderPolicy`: `Send` rights for the edge producer.
  - `FabricConsumerPolicy`: `Listen` rights for Fabric Eventstream ingestion.
- **User-Assigned Managed Identity**: For passwordless Azure authentication.

## Deployment Commands

Deploy the infrastructure using Azure CLI:

```bash
az group create --name rg-tiger-edge-dev --location eastus
az deployment group create \
  --resource-group rg-tiger-edge-dev \
  --template-file infra/digital-twin-poc/main.bicep \
  --parameters infra/digital-twin-poc/main.bicepparam
```

The output will contain `edgeEventHubConnectionString` to supply to the edge application or simulator.

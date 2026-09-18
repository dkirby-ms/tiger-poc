---
title: Factory Edge to Microsoft Fabric Infrastructure
description: Deploy Event Hubs and a scoped producer identity without exposing credentials in deployment outputs.
---

Optional Azure transport: edge relay -> Event Hubs -> Fabric Eventstream.
Skip this deployment when using a Fabric Custom App source directly.

## Resources Deployed

* Event Hubs namespace (`Standard` by default) and `process-events` hub
* User-assigned managed identity with Azure Event Hubs Data Sender scoped to the hub
* `FabricConsumerPolicy` with `Listen` rights for optional SAS authentication

No Fabric items, compute host, Key Vault, or consumer role assignment are created.
Deployment outputs contain no keys or connection strings. Azure resources incur charges.

## Deployment Commands

Sign in with Azure CLI, select your subscription, and review
[main.bicepparam](main.bicepparam). You need Bicep and permission to create resources
and role assignments (`Microsoft.Authorization/roleAssignments/write`). Run from the repository root:

```bash
RESOURCE_GROUP="rg-tiger-edge-dev"
DEPLOYMENT_NAME="deploy-tiger-edge-$(date +%Y%m%dT%H%M%S)"

az group create --name "$RESOURCE_GROUP" --location eastus --output none
az deployment group create \
        --name "$DEPLOYMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
  --template-file infra/digital-twin-poc/main.bicep \
        --parameters infra/digital-twin-poc/main.bicepparam \
        --output none

az deployment group show \
        --name "$DEPLOYMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query 'properties.outputs.{namespace:eventHubNamespaceHostname.value,hub:eventHubName.value,eventHubId:eventHubId.value,clientId:managedIdentityClientId.value,identityResourceId:managedIdentityResourceId.value}' \
        --output json
```

Continue only after success. Retain `DEPLOYMENT_NAME` for lookups; the output query selects nonsecret values only.

## Producer Authentication

Attach `managedIdentityResourceId` to your Azure compute host and set the relay environment:

| Environment variable | Deployment output |
| --- | --- |
| `FABRIC_EVENTSTREAM_NAMESPACE` | `eventHubNamespaceHostname` |
| `FABRIC_EVENTSTREAM_EVENTHUB_NAME` | `eventHubName` |
| `AZURE_CLIENT_ID` | `managedIdentityClientId` |

Allow time for RBAC propagation. `DefaultAzureCredential` can select earlier
credentials before managed identity. On WSL/laptops, sign in as a developer and
grant that principal Data Sender on `eventHubId` separately; `AZURE_CLIENT_ID`
does not impersonate managed identity locally. Continue with [publishing](../../README.md#publish-events).

## Fabric Consumer Authentication

The producer's sender role does not authorize Fabric to read. Prefer Workspace
identity: enable it in Fabric, grant it Data Receiver on `eventHubId`, and select
it in the Event Hubs connection. These steps are manual; see
[Microsoft's connector setup](https://learn.microsoft.com/en-us/fabric/real-time-intelligence/event-streams/add-source-azure-event-hubs).

For SAS fallback, obtain the `FabricConsumerPolicy` Listen key privately and enter
it directly in Fabric's credentials UI. Keep retained copies in an approved vault;
never put secrets in logs, outputs, or git. Do not disable SAS until all clients
have migrated. Continue with [Fabric setup](../../README.md#fabric-setup).


| Environment variable | Deployment output |


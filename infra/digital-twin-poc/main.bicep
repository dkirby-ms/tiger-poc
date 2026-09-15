/*
  Main orchestration template for Factory Edge to Microsoft Fabric Ingestion Infrastructure.
*/

import { Environment, ResourceTags } from './types.bicep'

@description('Azure deployment location.')
param location string = resourceGroup().location

@description('Deployment environment.')
param environment Environment = 'dev'

@description('Unique suffix for resource names.')
param resourceSuffix string = uniqueString(resourceGroup().id)

@description('Base name for the factory edge ingestion resources.')
param baseName string = 'tiger-edge'

@description('Event Hubs SKU configuration.')
param skuName 'Basic' | 'Standard' | 'Premium' = 'Standard'

@description('Tags applied to all provisioned resources.')
param tags ResourceTags = {
  project: 'factory-perception-poc'
  environment: environment
  workload: 'edge-to-fabric-digital-twin'
}

var formattedSuffix = take(resourceSuffix, 6)
var eventHubNamespaceName = '${baseName}-ehns-${environment}-${formattedSuffix}'
var eventHubName = 'process-events'
var identityName = '${baseName}-id-${environment}-${formattedSuffix}'

/*
  Deploy User-Assigned Managed Identity
*/
module identityModule 'modules/identity.bicep' = {
  name: 'deploy-identity'
  params: {
    location: location
    identityName: identityName
    tags: tags
  }
}

/*
  Deploy Event Hubs Namespace and Topic for Fabric Eventstream ingestion
*/
module eventHubModule 'modules/eventhub.bicep' = {
  name: 'deploy-eventhub'
  params: {
    location: location
    namespaceName: eventHubNamespaceName
    eventHubName: eventHubName
    skuName: skuName
    tags: tags
  }
}

@description('Event Hubs Namespace Name.')
output eventHubNamespaceName string = eventHubNamespaceName

@description('Event Hub Topic Name.')
output eventHubName string = eventHubName

@description('Edge Producer Connection String for environment variable configuration.')
#disable-next-line outputs-should-not-contain-secrets
output edgeEventHubConnectionString string = eventHubModule.outputs.edgeSenderConnectionString

@description('Fabric Eventstream Consumer Connection String.')
#disable-next-line outputs-should-not-contain-secrets
output fabricEventstreamConnectionString string = eventHubModule.outputs.fabricConsumerConnectionString

@description('Managed Identity Client ID.')
output managedIdentityClientId string = identityModule.outputs.clientId

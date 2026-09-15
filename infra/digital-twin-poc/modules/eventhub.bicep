/*
  Azure Event Hubs module for Fabric Eventstream Custom App ingestion endpoint.
*/

@description('Azure region for the Event Hubs namespace.')
param location string

@description('Name of the Event Hubs namespace.')
param namespaceName string

@description('Name of the Event Hub for process events.')
param eventHubName string

@description('SKU name for Event Hubs namespace.')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param skuName string = 'Standard'

@description('Capacity units for the namespace.')
param skuCapacity int = 1

@description('Message retention in days.')
param messageRetentionInDays int = 1

@description('Partition count for the Event Hub.')
param partitionCount int = 2

@description('Resource tags.')
param tags object

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  sku: {
    name: skuName
    tier: skuName
    capacity: skuCapacity
  }
  tags: tags
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubNamespace
  name: eventHubName
  properties: {
    messageRetentionInDays: messageRetentionInDays
    partitionCount: partitionCount
  }
}

resource edgeSenderAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2024-01-01' = {
  parent: eventHub
  name: 'EdgeSenderPolicy'
  properties: {
    rights: [
      'Send'
    ]
  }
}

resource fabricConsumerAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2024-01-01' = {
  parent: eventHub
  name: 'FabricConsumerPolicy'
  properties: {
    rights: [
      'Listen'
    ]
  }
}

@description('Resource ID of the Event Hubs Namespace.')
output namespaceId string = eventHubNamespace.id

@description('Name of the Event Hub.')
output eventHubName string = eventHub.name

@description('Service Bus / Event Hubs Endpoint URL.')
output serviceBusEndpoint string = eventHubNamespace.properties.serviceBusEndpoint

@description('Primary connection string for Edge sender with Send permission.')
#disable-next-line outputs-should-not-contain-secrets
output edgeSenderConnectionString string = edgeSenderAuthRule.listKeys().primaryConnectionString

@description('Primary connection string for Fabric Eventstream with Listen permission.')
#disable-next-line outputs-should-not-contain-secrets
output fabricConsumerConnectionString string = fabricConsumerAuthRule.listKeys().primaryConnectionString

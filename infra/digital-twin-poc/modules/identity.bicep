/*
  Managed Identity module for edge-to-cloud secure authentication.
*/

@description('Azure region for the Managed Identity.')
param location string

@description('Name of the User-Assigned Managed Identity.')
param identityName string

@description('Resource tags.')
param tags object

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

@description('Resource ID of the created Managed Identity.')
output identityId string = managedIdentity.id

@description('Principal ID (Object ID) of the Managed Identity.')
output principalId string = managedIdentity.properties.principalId

@description('Client ID (App ID) of the Managed Identity.')
output clientId string = managedIdentity.properties.clientId

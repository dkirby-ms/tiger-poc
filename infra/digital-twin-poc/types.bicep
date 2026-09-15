/*
  Type definitions for Factory Perception and Microsoft Fabric Edge Ingestion infrastructure.
*/

@description('Deployment environment name.')
@export()
type Environment = 'dev' | 'test' | 'prod'

@description('SKU configuration for Event Hubs namespace.')
@export()
type EventHubSku = {
  @description('Name of the Event Hubs SKU.')
  name: 'Basic' | 'Standard' | 'Premium'
  @description('Messaging capacity units.')
  capacity: int
}

@description('Tag dictionary for resource governance.')
@export()
type ResourceTags = {
  @description('Project or accelerator name.')
  project: string
  @description('Environment stage.')
  environment: string
  @description('Workload identifier.')
  workload: string
}

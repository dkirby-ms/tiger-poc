using './main.bicep'

param environment = 'dev'
param baseName = 'tiger-edge'
param skuName = 'Standard'
param tags = {
  project: 'factory-perception-poc'
  environment: 'dev'
  workload: 'edge-to-fabric-digital-twin'
}

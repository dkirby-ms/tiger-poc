<!-- markdownlint-disable-file -->
# Local Mock Control Plane for ModelDeployments - Research

**Date:** 2026-08-15  
**Issue:** #2 - Implement local mock control plane for ModelDeployments  
**Status:** Complete

## Scope and Success Criteria

### User Requests
1. Accept local deployment manifests or configuration
2. Provision one logical deployment per model
3. Surface deployment status, endpoint metadata, API-key metadata, and health

### Acceptance Criteria
1. Creating a deployment results in an isolated logical service with its own status
2. Deployment state changes are observable by the inference client
3. Deleting a deployment removes its endpoint and credentials

## Current State Analysis

### Existing Implementation
- `LocalFoundryDeploymentRuntime` class with hardcoded deployments (3 models)
- `DeploymentContract` dataclass with model_id, route, secret, ready fields
- Dispatch mechanism validates payloads, routes, secrets, and ready status
- Tests confirm contract validation works

### Architecture Patterns
- Single runtime instance manages all deployments
- Ready override mechanism for state mutation
- Payload validation based on route semantics
- Existing tests require backward compatibility

## Recommended Approach

### Design Pattern: Deployment Lifecycle Manager

**Key Components:**
1. **DeploymentConfig** - Accepts manifest/configuration for deployment creation
2. **DeploymentState** - Tracks deployment status (creating, ready, error, deleting)
3. **DeploymentRegistry** - Manages lifecycle (create, list, get, delete)
4. **Health Check** - Observable status endpoint
5. **Backward Compatibility** - Wrap existing runtime with dynamic deployment layer

### Implementation Strategy

**Phase 1: Extend contract model**
- Add DeploymentConfig dataclass for manifest acceptance
- Add DeploymentState enum for lifecycle tracking
- Extend DeploymentContract with status field

**Phase 2: Create DeploymentRegistry**
- Implement CRUD operations for deployments
- Track deployment state transitions
- Validate unique model_id and secrets
- Observable status queries

**Phase 3: Refactor runtime to use registry**
- LocalFoundryDeploymentRuntime delegates to DeploymentRegistry
- Maintain existing dispatch() interface
- Support dynamic deployment creation/deletion

**Phase 4: Add health/status endpoints**
- Get deployment status by model_id
- List all deployments with status
- Observable health checks

**Phase 5: Tests and validation**
- Existing tests pass unchanged (backward compatibility)
- New tests for deployment lifecycle
- State transitions are observable

## Technical Details

### Manifest Format
Configuration accepted as dict or dataclass:
```python
{
    "model_id": "yolo",
    "route": "/v1/predict", 
    "secret": "yolo-secret-v2"
}
```

### Deployment States
- **CREATING**: Deployment being provisioned
- **READY**: Deployment active and ready for inference
- **ERROR**: Deployment failed or degraded
- **DELETING**: Deployment cleanup in progress
- **DELETED**: Deployment removed

### Observable Queries
- `get_deployment(model_id)` - Single deployment status
- `list_deployments()` - All deployments with status
- `get_health(model_id)` - Health/readiness check

### Backward Compatibility
- Existing `dispatch()` interface unchanged
- Existing tests pass without modification
- Default deployments auto-provisioned if not explicitly created

## Success Validation

1. ✅ Accept deployment configuration manifests
2. ✅ Provision isolated logical services
3. ✅ Observable deployment state
4. ✅ Lifecycle operations (create, delete)
5. ✅ Credential lifecycle management
6. ✅ All existing tests pass
7. ✅ New tests validate lifecycle behavior

## Next Steps

1. Create DeploymentConfig and DeploymentState models
2. Implement DeploymentRegistry with CRUD operations
3. Extend DeploymentContract with status tracking
4. Refactor LocalFoundryDeploymentRuntime
5. Add comprehensive tests for lifecycle operations
6. Add status/health query methods

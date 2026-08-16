<!-- markdownlint-disable-file -->
# Local Mock Control Plane - Implementation Plan

**Date:** 2026-08-15  
**Difficulty:** Medium-hard  
**Research:** [deployment-control-plane-research.md](../../research/2026-08-15/deployment-control-plane-research.md)

## User Requests

1. **Create deployment lifecycle management** - Accept manifests and provision deployments dynamically
2. **Observable deployment state** - Track and expose deployment status, metadata, and health
3. **Full lifecycle support** - Create, list, get, and delete deployments with proper credential management

## Overview and Objectives

The local runtime currently has hardcoded deployments. This plan extends it to support dynamic deployment management while maintaining backward compatibility with existing tests.

**Derived Objectives:**
- Add deployment configuration acceptance via manifests
- Implement deployment registry with CRUD operations
- Track deployment state throughout lifecycle
- Provide observable status queries
- Ensure credential lifecycle management
- Maintain all existing test compatibility

## Context Summary

**Discovered Files:**
- [apps/local_model_runtime/foundry_contract.py](../../../../apps/local_model_runtime/foundry_contract.py) - Existing runtime implementation
- [apps/local_model_runtime/__init__.py](../../../../apps/local_model_runtime/__init__.py) - Module exports
- [tests/test_foundry_local_deployment_contracts.py](../../../../tests/test_foundry_local_deployment_contracts.py) - Existing test suite

**Key Patterns:**
- Dataclass-based contract model
- Ready status override for state mutation
- Payload validation based on route semantics
- Deterministic test harness approach

## Implementation Checklist

### Phase 1: Model Extensions (foundry_contract.py) <!-- parallelizable: false -->
- [ ] Add `DeploymentState` enum (CREATING, READY, ERROR, DELETING, DELETED)
- [ ] Add `DeploymentConfig` dataclass for manifest acceptance
- [ ] Extend `DeploymentContract` with status and timestamps
- [ ] Update `__init__` exports

**Success Criteria:**
- New models compile without errors
- Existing DeploymentContract behavior unchanged
- Can create instances from configs

### Phase 2: Implement DeploymentRegistry (new file deployment_registry.py) <!-- parallelizable: false -->
- [ ] Create `DeploymentRegistry` class with state management
- [ ] Implement `create_deployment(config)` method
- [ ] Implement `get_deployment(model_id)` method
- [ ] Implement `list_deployments()` method
- [ ] Implement `delete_deployment(model_id)` method
- [ ] Add validation for unique model_id and secrets
- [ ] Track state transitions with timestamps
- [ ] Update `__init__` exports

**Success Criteria:**
- Registry performs CRUD operations correctly
- Deployments have unique model_id and secrets
- State transitions are tracked
- Queries return current state

### Phase 3: Refactor LocalFoundryDeploymentRuntime <!-- parallelizable: false -->
- [ ] Add registry as internal component
- [ ] Auto-provision default deployments on init
- [ ] Refactor `dispatch()` to use registry
- [ ] Maintain exact existing interface
- [ ] Keep `set_ready()` method for test compatibility
- [ ] Add `get_status(model_id)` query method
- [ ] Add `get_health(model_id)` check method

**Success Criteria:**
- `dispatch()` interface unchanged
- Existing tests pass without modification
- Registry is used internally
- Default deployments auto-provisioned
- Query methods work correctly

### Phase 4: Add Tests (test_foundry_local_deployment_contracts.py) <!-- parallelizable: false -->
- [ ] Add lifecycle tests (create, get, list, delete)
- [ ] Test deployment isolation
- [ ] Test state transitions
- [ ] Test credential lifecycle
- [ ] Test observable status changes
- [ ] Verify existing tests still pass
- [ ] Test error conditions

**Success Criteria:**
- All existing tests pass unchanged
- New tests validate lifecycle operations
- Deployment state is observable
- Credentials are managed properly

## Planning Log

**Dependencies:**
- Python 3.8+
- dataclasses (stdlib)
- Existing foundry_contract module

**Implementation Paths Considered:**
1. ✅ **Selected**: Extend existing structure with registry layer
   - Rationale: Maintains backward compatibility, clear separation of concerns
   - Risk: Low - no changes to existing interfaces
   
2. Alternative: Rewrite entire runtime
   - Rationale: Cleaner code
   - Risk: High - breaks existing tests and clients
   - Status: Rejected

**File Changes:**
- **Modified**: `apps/local_model_runtime/foundry_contract.py`
- **New**: `apps/local_model_runtime/deployment_registry.py`
- **Modified**: `apps/local_model_runtime/__init__.py`
- **Modified**: `tests/test_foundry_local_deployment_contracts.py`

## Success Criteria

✅ All existing tests pass (backward compatibility)  
✅ Deployment creation from manifests  
✅ Deployment deletion removes credentials  
✅ Deployment state is observable  
✅ State transitions are trackable  
✅ Isolated logical services  
✅ Health check capability  

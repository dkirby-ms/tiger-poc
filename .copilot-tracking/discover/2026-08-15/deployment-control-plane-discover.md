<!-- markdownlint-disable-file -->
# Phase 5: Discover - Suggested Next Work

**Date:** 2026-08-15  
**Completed Work:** Local Mock Control Plane for ModelDeployments (Issue #2)  
**Status:** All acceptance criteria met, all tests passing (30/30 ✅)

## Summary of Completed Work

Successfully implemented a dynamic deployment lifecycle manager for the local Foundry runtime with:
- ✅ Configuration manifest acceptance (`DeploymentConfig`)
- ✅ Full CRUD operations (`create_deployment`, `list_deployments`, `delete_deployment`, `get_status`)
- ✅ Observable deployment state and metadata
- ✅ Isolated logical services with unique credentials
- ✅ Complete backward compatibility (3/3 existing tests pass unchanged)
- ✅ Comprehensive test coverage (27 new lifecycle tests)

## Discovered Patterns and Artifacts

**Model Manifest Infrastructure:**
- `models/bundle.json` defines model metadata (format, precision, path, SHA256, source, runtime)
- Bundle structure already supports format variations (ONNX, Transformers, ONNX-GenAI)
- Model identities are versioned and tracked with SHA256 digests

**Architecture References:**
- System design mentions "ModelDeployment lifecycle" as an architectural requirement
- Plans reference containerized runtime service and HTTP server
- Edge deployment patterns in Azure Local/Arc environment documented
- Foundry Local compatibility required for cloud migration path

**Existing Infrastructure:**
- Docker/Compose orchestration mentioned for local development
- Verification scripts in `scripts/` directory for validation
- Bundle manifest validation workflow documented

## High-Value Follow-Up Opportunities

### 1. 🔵 **Bundle Manifest Loader** (Medium Priority)
**Impact:** Simplifies deployment configuration and enables model manifest-driven setup  
**Scope:** Small, isolated feature  
**Effort:** 2-3 hours

Create a deployment loader that reads `bundle.json` and auto-provisions deployments:
```python
manifest = BundleManifest.load("models/bundle.json")
deployments = runtime.provision_from_bundle(manifest)
```

**Benefits:**
- Single source of truth for model definitions
- Aligns with production Foundry Local pattern
- Enables CI/CD pipeline to define deployments declaratively
- Supports model versioning and digest validation

**Next Actions:**
- Add `BundleManifest` parser in `apps/local_model_runtime/`
- Implement `provision_from_bundle()` method in runtime
- Add tests validating manifest-driven provisioning

---

### 2. 🔵 **HTTP API Server** (High Priority)
**Impact:** Enables remote clients and integration with edge orchestration  
**Scope:** Medium, adds new service  
**Effort:** 4-6 hours

Expose deployment lifecycle operations via REST API:
```
GET    /deployments                # List all deployments
POST   /deployments                # Create deployment
GET    /deployments/{model_id}     # Get deployment status
PATCH  /deployments/{model_id}     # Update deployment
DELETE /deployments/{model_id}     # Delete deployment
GET    /health                     # Overall system health
```

**Benefits:**
- Enables non-Python clients (Go, Rust, etc.)
- Prepares for Kubernetes operator integration
- Supports Docker/container health checks
- Foundation for edge management plane

**Technologies:**
- FastAPI (modern, type-safe, async)
- Pydantic models (schema validation)
- Existing pattern in system architecture

**Next Actions:**
- Create `apps/local_model_runtime/api/` with server
- Define OpenAPI schema for deployment operations
- Add integration tests for API endpoints
- Document API in README

---

### 3. 🟡 **Deployment Persistence** (Medium Priority)
**Impact:** Preserves deployment state across restarts  
**Scope:** Small, adds optional persistence layer  
**Effort:** 3-4 hours

Enable deployments to survive runtime restarts via local store:
```python
registry = DeploymentRegistry.load_or_create("deployments.json")
# ... deployments persist to disk on create/delete/update
```

**Benefits:**
- Development convenience (no re-provisioning after restart)
- Supports health recovery scenarios
- Foundation for backup/restore workflows

**Implementation Options:**
- JSON file persistence (simple, local dev)
- SQLite database (scalable, queryable)
- Both with pluggable adapter pattern

**Next Actions:**
- Add persistence abstraction to registry
- Implement JSON-based persistence first
- Add load/save tests
- Document persistence behavior

---

### 4. 🟡 **Health and Readiness Checks** (Medium Priority)
**Impact:** Enables container orchestration integration  
**Scope:** Small, isolated feature  
**Effort:** 2-3 hours

Add observable health endpoints for deployment status:
```python
health = runtime.get_deployment_health(model_id)  # DeploymentHealth object
# - status: HEALTHY, DEGRADED, UNHEALTHY
# - ready: bool (readiness probe)
# - reason: str
# - latency_ms: int
# - error_count: int
```

**Benefits:**
- Docker/Kubernetes health check support
- Observable deployment degradation
- Foundation for auto-recovery logic

**Next Actions:**
- Add health metric collection to registry
- Add `get_deployment_health()` method
- Document health probe behavior
- Add tests for health transitions

---

### 5. 🟢 **Deployment Templates** (Low Priority)
**Impact:** Reduces configuration errors and setup friction  
**Scope:** Small, convenience feature  
**Effort:** 1-2 hours

Pre-configured templates for common model types:
```python
template = DeploymentTemplate.predictive_model(
    model_id="my-yolo",
    source="models/my-yolo/model.onnx"
)
deployment = runtime.create_deployment_from_template(template)
```

**Benefits:**
- Reduces configuration mistakes
- Establishes deployment patterns
- Self-documenting for new team members

**Built-in Templates:**
- `predictive_model` - For detection/classification (YOLO pattern)
- `generative_model` - For LLM inference (Phi pattern)
- `transformers_model` - For HuggingFace models (Florence pattern)

**Next Actions:**
- Add template classes to contract module
- Add factory methods to registry
- Document template patterns

---

### 6. 🟢 **Metrics and Observability** (Low Priority)
**Impact:** Enables monitoring and debugging in production  
**Scope:** Medium, optional instrumenting  
**Effort:** 3-4 hours

Collect and expose deployment metrics:
```python
metrics = runtime.get_metrics(model_id)
# - creation_time, last_modified_time
# - dispatch_count, dispatch_success_rate
# - status_transitions, uptime_seconds
```

**Benefits:**
- Track deployment health over time
- Debug performance issues
- Foundation for alerting

**Implementation:**
- Counter-based metrics collection
- Optional Prometheus export
- Dashboard-friendly format

**Next Actions:**
- Add `MetricsCollector` to registry
- Wire metrics into dispatch pipeline
- Add metrics query methods
- Document metrics schema

---

### 7. 🟠 **Kubernetes CRD Integration** (Lower Priority)
**Impact:** Enables production Azure Local deployment  
**Scope:** Large, requires domain knowledge  
**Effort:** 6-8 hours

Define and support Kubernetes ModelDeployment CRD:
```yaml
apiVersion: modeldeployment.local/v1
kind: ModelDeployment
metadata:
  name: yolo-detector
spec:
  model: yolo
  route: /v1/predict
  replicas: 1
  resources:
    memory: 4Gi
    gpu: 1
status:
  ready: true
  conditions:
  - type: Ready
    status: "True"
```

**Benefits:**
- Path to Azure Local / Azure Arc production
- Leverages Kubernetes as orchestrator
- Aligns with system architecture vision

**Next Actions:**
- Research existing CRD patterns
- Define CRD schema
- Create operator/controller stub
- Document CRD usage

---

## Recommended Prioritization

### **Phase 1 (This Week)** - High Impact, Quick Wins
1. **Bundle Manifest Loader** - 2-3h
2. **Deployment Persistence** - 3-4h

*Rationale:* These enable local dev convenience and prepare for manifest-driven deployments

### **Phase 2 (Next Week)** - Foundation for Integration
3. **HTTP API Server** - 4-6h
4. **Health and Readiness Checks** - 2-3h

*Rationale:* API server unlocks remote access and orchestration integration

### **Phase 3 (Backlog)** - Polish and Production
5. **Deployment Templates** - 1-2h
6. **Metrics and Observability** - 3-4h
7. **Kubernetes CRD Integration** - 6-8h

*Rationale:* These enable monitoring, debugging, and cloud deployment

## Quick-Start Next Steps

**To continue work:**

```bash
# Option 1: Bundle Manifest Loader
# Create apps/local_model_runtime/bundle_loader.py
# Implement BundleManifest parser and provision_from_bundle()

# Option 2: HTTP API Server
# Create apps/local_model_runtime/api/
# Use FastAPI to expose deployment CRUD

# Option 3: Deployment Persistence
# Add optional persistence layer to DeploymentRegistry
# Implement load/save with JSON backend
```

## Related Issues and Context

- **Issue #2** (Completed): Implement local mock control plane for ModelDeployments
- **Architecture Pattern**: ModelDeployment lifecycle management referenced in system design
- **Production Path**: Azure Local / Azure Arc requires Kubernetes integration
- **Bundle System**: Model manifest infrastructure in place and ready for deployment loader

---

**Ready to start the next phase? Reply with:**
- `1️⃣ Bundle Manifest Loader`
- `2️⃣ HTTP API Server`  
- `3️⃣ Deployment Persistence`
- `4️⃣ Health and Readiness Checks`
- `5️⃣ Deployment Templates`
- `all` for all phases

Or describe different work you'd like to focus on.

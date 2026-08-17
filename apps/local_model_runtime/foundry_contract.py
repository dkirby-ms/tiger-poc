from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from .model_service import (
    DeploymentState,
    ModelServiceSpec,
    ModelServiceSupervisor,
    WORKLOAD_PROFILES,
    WorkloadType,
    load_default_specs,
    workload_for_route,
)
from .workload_adapters import adapter_for


@dataclass
class DeploymentConfig:
    """Configuration for creating a new deployment."""
    model_id: str
    route: str
    secret: str
    workload_type: Optional[WorkloadType] = None

    def validate(self) -> None:
        """Validate configuration."""
        if not self.model_id or not self.route or not self.secret:
            raise ValueError("model_id, route, and secret are required")
        if self.resolved_workload_type is None:
            raise ValueError(f"No workload profile serves route '{self.route}'")

    @property
    def resolved_workload_type(self) -> Optional[WorkloadType]:
        """Workload type, derived from the route when not set explicitly."""
        return self.workload_type or workload_for_route(self.route)

    @classmethod
    def from_spec(cls, spec: ModelServiceSpec) -> "DeploymentConfig":
        return cls(
            model_id=spec.model_id,
            route=spec.route,
            secret=spec.secret,
            workload_type=spec.workload_type,
        )


@dataclass(frozen=True)
class DeploymentContract:
    model_id: str
    route: str
    secret: str
    ready: bool = True
    status: DeploymentState = DeploymentState.RUNNING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    workload_type: WorkloadType = WorkloadType.PREDICTIVE


class FoundryControlPlane(Protocol):
    """Deployment discovery and lifecycle boundary used by pipeline stages."""

    def list_deployments(self) -> List[DeploymentContract]: ...

    def get(self, model_id: str) -> Optional[DeploymentContract]: ...

    def create_deployment(self, config: DeploymentConfig) -> DeploymentContract: ...

    def delete_deployment(self, model_id: str) -> bool: ...

    def wait_ready(self, model_id: str, timeout_s: float) -> bool: ...


class LocalControlPlane:
    """Deterministic Foundry Local contract harness for local validation."""

    def __init__(self, specs: Optional[List[ModelServiceSpec]] = None):
        # Import here to avoid circular dependency
        from .deployment_registry import DeploymentRegistry

        self._registry = DeploymentRegistry()
        self._supervisor = ModelServiceSupervisor(
            specs if specs is not None else load_default_specs()
        )
        self._supervisor.start_all()

        for service in self._supervisor.services():
            self._registry.create_deployment(DeploymentConfig.from_spec(service.spec))

        # For backward compatibility, expose deployment_contracts property
        self.deployment_contracts = self._registry.list_deployments()

    @property
    def supervisor(self) -> ModelServiceSupervisor:
        """Supervisor owning one isolated deployment per model."""
        return self._supervisor

    def _next_port(self) -> int:
        used = {service.spec.port for service in self._supervisor.services()}
        port = 8080
        while port in used:
            port += 1
        return port

    def health(self) -> Dict[str, Any]:
        """Aggregate per-service health without merging their lifecycles."""
        return self._supervisor.health()

    def set_ready(self, model_id: str, ready: bool) -> None:
        """Set deployment ready status."""
        self._registry.set_ready(model_id, ready)
        service = self._supervisor.get(model_id)
        if service is not None:
            service.start() if ready else service.stop()
        # Update the backward-compatible property
        self.deployment_contracts = self._registry.list_deployments()

    def _get_contract(self, model_id: str) -> Optional[DeploymentContract]:
        """Get contract by model_id."""
        return self._registry.get_deployment(model_id)

    def _route_valid(self, contract: DeploymentContract, route: str) -> bool:
        """Check if route is valid for contract."""
        return contract.route == route

    def _payload_valid(self, contract: DeploymentContract, payload: dict) -> bool:
        """Check if payload matches the contract's workload profile."""
        return adapter_for(contract.workload_type).validate(payload) is None

    def dispatch(self, model_id: str, route: str, secret: str, payload: dict):
        """Dispatch inference request to deployment."""
        contract = self._get_contract(model_id)
        if contract is None:
            return {"status": "unknown_model", "model_id": model_id, "route": route}

        if not self._registry.is_ready(model_id):
            return {
                "status": "not_ready",
                "model_id": contract.model_id,
                "route": contract.route,
                "receipt": "deployment-not-ready",
            }

        if not self._route_valid(contract, route):
            return {
                "status": "wrong_route",
                "model_id": contract.model_id,
                "expected_route": contract.route,
                "received_route": route,
            }

        if secret != contract.secret:
            return {
                "status": "unauthorized",
                "model_id": contract.model_id,
                "route": contract.route,
            }

        adapter = adapter_for(contract.workload_type)
        payload_error = adapter.validate(payload)
        if payload_error is not None:
            return {
                "status": "wrong_payload",
                "model_id": contract.model_id,
                "route": contract.route,
                "expected_payload": WORKLOAD_PROFILES[contract.workload_type].payload_kind,
                "message": payload_error.message,
                "param": payload_error.param,
            }

        return {
            "status": "ok",
            "model_id": contract.model_id,
            "route": contract.route,
            "payload_type": WORKLOAD_PROFILES[contract.workload_type].payload_kind,
            "response": adapter.build_response(contract.model_id, payload),
        }

    def get(self, model_id: str) -> Optional[DeploymentContract]:
        """Resolve one deployment by model identity."""
        return self._get_contract(model_id)

    def wait_ready(self, model_id: str, timeout_s: float) -> bool:
        """Return local readiness; local lifecycle transitions are synchronous."""
        if timeout_s < 0:
            raise ValueError("timeout_s cannot be negative")
        return self._registry.is_ready(model_id)

    def get_status(self, model_id: str) -> Optional[DeploymentState]:
        """Get deployment status."""
        return self._registry.get_status(model_id)

    def list_deployments(self) -> List[DeploymentContract]:
        """List all active deployments."""
        return self._registry.list_deployments()

    def create_deployment(self, config: DeploymentConfig) -> DeploymentContract:
        """Create a new deployment and its isolated single-model service."""
        contract = self._registry.create_deployment(config)
        if self._supervisor.get(contract.model_id) is None:
            self._supervisor.register(
                ModelServiceSpec(
                    model_id=contract.model_id,
                    workload_type=contract.workload_type,
                    bundle_model_id=contract.model_id,
                    secret=contract.secret,
                    port=self._next_port(),
                )
            )
        self._supervisor.start(contract.model_id)
        self.deployment_contracts = self._registry.list_deployments()
        return contract

    def delete_deployment(self, model_id: str) -> bool:
        """Delete a deployment and stop its service."""
        result = self._registry.delete_deployment(model_id)
        if result:
            self._supervisor.unregister(model_id)
        self.deployment_contracts = self._registry.list_deployments()
        return result


LocalFoundryDeploymentRuntime = LocalControlPlane

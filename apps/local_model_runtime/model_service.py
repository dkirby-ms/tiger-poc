"""Generic, configuration-driven local model services.

One service instance hosts exactly one model bundle. Differences between
models are expressed as workload profiles, bundle references, and resource
configuration rather than per-model service implementations.

Field names and states mirror the Foundry Local `ModelDeployment` CRD so the
local stack stays comparable to Azure Local.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional

CPU_QUANTITY = re.compile(r"^\d+(\.\d+)?m?$")
MEMORY_QUANTITY = re.compile(r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti|K|M|G|T)?$")


class WorkloadType(str, Enum):
    """Kind of inference contract a deployment exposes."""

    PREDICTIVE = "predictive"
    GENERATIVE = "generative"


class ComputeTarget(str, Enum):
    """Compute a deployment is scheduled against."""

    CPU = "cpu"
    GPU = "gpu"


class InferenceRuntime(str, Enum):
    """Inference runtime serving the model."""

    ONNX_GENAI = "onnx-genai"
    VLLM = "vllm"


class DeploymentState(str, Enum):
    """Deployment lifecycle states reported by the inference operator."""

    PENDING = "Pending"
    CREATING = "Creating"
    RUNNING = "Running"
    UPDATING = "Updating"
    ERROR = "Error"
    TERMINATING = "Terminating"


class EndpointExposure(str, Enum):
    """How the operator exposes a deployment through the Gateway."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    NONE = "none"


class FailureReason(str, Enum):
    """Fault categories the inference operator surfaces on a deployment."""

    MODEL_DOWNLOAD = "ModelDownloadFailed"
    GPU_UNAVAILABLE = "InsufficientGpuCapacity"
    RUNTIME_UNHEALTHY = "ModelRuntimeUnhealthy"
    BUNDLE_CONFLICT = "BundleConflict"


@dataclass(frozen=True)
class WorkloadProfile:
    """Route and payload contract shared by all deployments of one workload type."""

    route: str
    payload_kind: str
    required_fields: FrozenSet[str]
    rejected_fields: FrozenSet[str]

    def accepts(self, payload: Mapping[str, Any]) -> bool:
        keys = set(payload)
        return self.required_fields <= keys and not (self.rejected_fields & keys)


WORKLOAD_PROFILES: Dict[WorkloadType, WorkloadProfile] = {
    WorkloadType.PREDICTIVE: WorkloadProfile(
        route="/v1/predict",
        payload_kind="predictive",
        required_fields=frozenset({"image"}),
        rejected_fields=frozenset({"messages"}),
    ),
    WorkloadType.GENERATIVE: WorkloadProfile(
        route="/v1/chat/completions",
        payload_kind="chat-completion",
        required_fields=frozenset({"messages"}),
        rejected_fields=frozenset({"image"}),
    ),
}


def workload_for_route(route: str) -> Optional[WorkloadType]:
    """Resolve the workload type that owns a route."""
    for workload_type, profile in WORKLOAD_PROFILES.items():
        if profile.route == route:
            return workload_type
    return None


@dataclass(frozen=True)
class ResourceRequests:
    """Scheduling requests, using Kubernetes quantity strings."""

    cpu: str = "100m"
    memory: str = "256Mi"

    def validate(self) -> None:
        if not CPU_QUANTITY.match(self.cpu):
            raise ValueError(f"Invalid CPU quantity: {self.cpu}")
        if not MEMORY_QUANTITY.match(self.memory):
            raise ValueError(f"Invalid memory quantity: {self.memory}")

    def as_dict(self) -> Dict[str, Any]:
        return {"cpu": self.cpu, "memory": self.memory}


@dataclass(frozen=True)
class ResourceLimits:
    """Upper bounds, including the GPU count reserved for the deployment."""

    cpu: str = "1000m"
    memory: str = "1Gi"
    gpu: Optional[int] = None

    def validate(self) -> None:
        if not CPU_QUANTITY.match(self.cpu):
            raise ValueError(f"Invalid CPU quantity: {self.cpu}")
        if not MEMORY_QUANTITY.match(self.memory):
            raise ValueError(f"Invalid memory quantity: {self.memory}")
        if self.gpu is not None and not 0 <= self.gpu <= 8:
            raise ValueError("gpu must be between 0 and 8")

    def as_dict(self) -> Dict[str, Any]:
        limits: Dict[str, Any] = {"cpu": self.cpu, "memory": self.memory}
        if self.gpu is not None:
            limits["gpu"] = self.gpu
        return limits


@dataclass(frozen=True)
class ResourceConfig:
    """Per-deployment resource requests and limits."""

    requests: ResourceRequests = field(default_factory=ResourceRequests)
    limits: ResourceLimits = field(default_factory=ResourceLimits)

    def validate(self) -> None:
        self.requests.validate()
        self.limits.validate()

    def as_dict(self) -> Dict[str, Any]:
        return {"requests": self.requests.as_dict(), "limits": self.limits.as_dict()}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ResourceConfig":
        return cls(
            requests=ResourceRequests(**data.get("requests", {})),
            limits=ResourceLimits(**data.get("limits", {})),
        )


@dataclass(frozen=True)
class EndpointConfig:
    """Gateway routing for one deployment."""

    exposure: EndpointExposure = EndpointExposure.INTERNAL
    path: Optional[str] = None
    rewrite_path: str = "/"

    def validate(self) -> None:
        if self.path is not None and not self.path.startswith("/"):
            raise ValueError("endpoint path must start with '/'")
        if not self.rewrite_path.startswith("/"):
            raise ValueError("endpoint rewritePath must start with '/'")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "exposure": self.exposure.value,
            "path": self.path,
            "rewritePath": self.rewrite_path,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EndpointConfig":
        return cls(
            exposure=EndpointExposure(data.get("exposure", EndpointExposure.INTERNAL.value)),
            path=data.get("path"),
            rewrite_path=data.get("rewritePath", "/"),
        )


@dataclass(frozen=True)
class ModelServiceSpec:
    """Declarative definition of one model deployment."""

    model_id: str
    workload_type: WorkloadType
    bundle_model_id: str
    secret: str
    compute: ComputeTarget = ComputeTarget.CPU
    runtime: InferenceRuntime = InferenceRuntime.ONNX_GENAI
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    replicas: int = 1
    port: int = 8080
    endpoint: EndpointConfig = field(default_factory=EndpointConfig)

    @property
    def profile(self) -> WorkloadProfile:
        return WORKLOAD_PROFILES[self.workload_type]

    @property
    def route(self) -> str:
        return self.profile.route

    @property
    def path_prefix(self) -> str:
        """Gateway path prefix, defaulting to the deployment name."""
        return self.endpoint.path or f"/{self.model_id}"

    @property
    def gpu_count(self) -> int:
        return self.resources.limits.gpu or 0

    def validate(self) -> None:
        if not self.model_id or not self.bundle_model_id or not self.secret:
            raise ValueError("model_id, bundle_model_id, and secret are required")
        if self.workload_type not in WORKLOAD_PROFILES:
            raise ValueError(f"Unsupported workloadType: {self.workload_type}")
        if not 1 <= self.replicas <= 100:
            raise ValueError("replicas must be between 1 and 100")
        if not 1024 <= self.port <= 65535:
            raise ValueError("port must be between 1024 and 65535")
        if self.runtime is InferenceRuntime.VLLM and self.compute is not ComputeTarget.GPU:
            raise ValueError("runtime 'vllm' requires compute 'gpu'")
        if self.runtime is InferenceRuntime.VLLM and self.workload_type is WorkloadType.PREDICTIVE:
            raise ValueError("runtime 'vllm' does not serve predictive workloads")
        self.resources.validate()
        self.endpoint.validate()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ModelServiceSpec":
        spec = cls(
            model_id=data["model_id"],
            workload_type=WorkloadType(data["workloadType"]),
            bundle_model_id=data.get("bundle_model_id", data["model_id"]),
            secret=data["secret"],
            compute=ComputeTarget(data.get("compute", ComputeTarget.CPU.value)),
            runtime=InferenceRuntime(data.get("runtime", InferenceRuntime.ONNX_GENAI.value)),
            resources=ResourceConfig.from_mapping(data.get("resources", {})),
            replicas=int(data.get("replicas", 1)),
            port=int(data.get("port", 8080)),
            endpoint=EndpointConfig.from_mapping(data.get("endpoint", {})),
        )
        spec.validate()
        return spec


class ModelService:
    """A single-model deployment with an independent lifecycle."""

    def __init__(self, spec: ModelServiceSpec, cache_steps: int = 0):
        spec.validate()
        if cache_steps < 0:
            raise ValueError("cache_steps cannot be negative")
        self._spec = spec
        self._cache_steps = cache_steps
        self._remaining_steps = 0
        self._state = DeploymentState.PENDING
        self._loaded_bundle: Optional[str] = None
        self._ready_replicas = 0
        self._message: Optional[str] = None
        self._reason: Optional[FailureReason] = None
        self._restart_count = 0

    @property
    def spec(self) -> ModelServiceSpec:
        return self._spec

    @property
    def model_id(self) -> str:
        return self._spec.model_id

    @property
    def state(self) -> DeploymentState:
        return self._state

    @property
    def ready(self) -> bool:
        return (
            self._state is DeploymentState.RUNNING
            and self._ready_replicas == self._spec.replicas
        )

    @property
    def loaded_bundle(self) -> Optional[str]:
        return self._loaded_bundle

    @property
    def message(self) -> Optional[str]:
        return self._message

    @property
    def reason(self) -> Optional[FailureReason]:
        return self._reason

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def start(self) -> None:
        """Pull the single bundle reference and bring every replica up."""
        if self._state is DeploymentState.RUNNING:
            return
        self._state = DeploymentState.CREATING
        self._reason = None
        self._message = None
        self._remaining_steps = self._cache_steps
        if self._remaining_steps:
            self._message = f"Downloading bundle '{self._spec.bundle_model_id}' to the model cache"
            return
        self._become_running()

    def progress(self) -> DeploymentState:
        """Advance one simulated model cache step while Creating."""
        if self._state is not DeploymentState.CREATING:
            return self._state
        self._remaining_steps = max(self._remaining_steps - 1, 0)
        if self._remaining_steps == 0:
            self._become_running()
        return self._state

    def _become_running(self) -> None:
        self._load_bundle(self._spec.bundle_model_id)
        self._ready_replicas = self._spec.replicas
        self._state = DeploymentState.RUNNING
        self._message = None
        self._reason = None

    def stop(self) -> None:
        """Scale to zero and unload the bundle, leaving the deployment registered."""
        self._loaded_bundle = None
        self._ready_replicas = 0
        self._remaining_steps = 0
        self._state = DeploymentState.PENDING
        self._message = None
        self._reason = None

    def restart(self) -> None:
        """Restart this deployment only, clearing any recorded failure."""
        self.stop()
        self._restart_count += 1
        self.start()

    def update(self, spec: ModelServiceSpec) -> None:
        """Apply a new spec through an Updating transition."""
        spec.validate()
        if spec.model_id != self._spec.model_id:
            raise ValueError("update cannot change the deployment name")
        was_running = self._state is DeploymentState.RUNNING
        self._state = DeploymentState.UPDATING
        self._loaded_bundle = None
        self._ready_replicas = 0
        self._spec = spec
        if was_running:
            self._become_running()

    def terminate(self) -> None:
        """Enter the terminal state used while the deployment is removed."""
        self._loaded_bundle = None
        self._ready_replicas = 0
        self._state = DeploymentState.TERMINATING

    def fail(self, message: str, reason: FailureReason = FailureReason.RUNTIME_UNHEALTHY) -> None:
        """Record an actionable failure for this deployment only."""
        self._ready_replicas = 0
        self._remaining_steps = 0
        self._state = DeploymentState.ERROR
        self._message = message
        self._reason = reason

    def load_bundle(self, bundle_model_id: str) -> None:
        """Load a bundle explicitly, rejecting any second model in this process."""
        self._load_bundle(bundle_model_id)

    def _load_bundle(self, bundle_model_id: str) -> None:
        if self._loaded_bundle is not None and self._loaded_bundle != bundle_model_id:
            self.fail(
                f"Deployment '{self._spec.model_id}' already hosts bundle "
                f"'{self._loaded_bundle}' and cannot load '{bundle_model_id}'",
                FailureReason.BUNDLE_CONFLICT,
            )
            raise RuntimeError(self._message)
        if bundle_model_id != self._spec.bundle_model_id:
            self.fail(
                f"Deployment '{self._spec.model_id}' is bound to bundle "
                f"'{self._spec.bundle_model_id}', not '{bundle_model_id}'",
                FailureReason.BUNDLE_CONFLICT,
            )
            raise RuntimeError(self._message)
        self._loaded_bundle = bundle_model_id

    def health(self) -> Dict[str, Any]:
        """Report this deployment's own status, independent of other deployments."""
        return {
            "model_id": self._spec.model_id,
            "state": self._state.value,
            "ready": self.ready,
            "message": self._message,
            "reason": self._reason.value if self._reason else None,
            "restartCount": self._restart_count,
            "deploymentReady": self.ready,
            "serviceReady": self._state is not DeploymentState.TERMINATING,
            "endpointReady": (
                self._state is DeploymentState.RUNNING
                and self._spec.endpoint.exposure is not EndpointExposure.NONE
            ),
            "replicas": {
                "desired": self._spec.replicas,
                "ready": self._ready_replicas,
                "available": self._ready_replicas,
            },
            "workloadType": self._spec.workload_type.value,
            "compute": self._spec.compute.value,
            "runtime": self._spec.runtime.value,
            "route": self._spec.route,
            "path": self._spec.path_prefix,
            "exposure": self._spec.endpoint.exposure.value,
            "bundle_model_id": self._spec.bundle_model_id,
            "loaded_bundle": self._loaded_bundle,
            "resources": self._spec.resources.as_dict(),
        }


class ModelServiceSupervisor:
    """Owns one deployment per model and starts or stops them individually."""

    def __init__(
        self,
        specs: Iterable[ModelServiceSpec] = (),
        gpu_capacity: Optional[int] = None,
        cache_steps: int = 0,
    ):
        self._services: Dict[str, ModelService] = {}
        self._gpu_capacity = gpu_capacity
        self._cache_steps = cache_steps
        for spec in specs:
            self.register(spec)

    @classmethod
    def from_catalog(cls, catalog_path: Path | str, **kwargs: Any) -> "ModelServiceSupervisor":
        """Build a supervisor from a service catalog file."""
        payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        specs = [ModelServiceSpec.from_mapping(entry) for entry in payload.get("services", [])]
        return cls(specs, **kwargs)

    @property
    def gpu_capacity(self) -> Optional[int]:
        return self._gpu_capacity

    def allocated_gpus(self, exclude: Optional[str] = None) -> int:
        return sum(
            service.spec.gpu_count * service.spec.replicas
            for model_id, service in self._services.items()
            if model_id != exclude and service.state is DeploymentState.RUNNING
        )

    def register(self, spec: ModelServiceSpec) -> ModelService:
        spec.validate()
        if spec.model_id in self._services:
            raise ValueError(f"Deployment '{spec.model_id}' is already registered")
        for existing in self._services.values():
            if existing.spec.bundle_model_id == spec.bundle_model_id:
                raise ValueError(
                    f"Bundle '{spec.bundle_model_id}' is already hosted by deployment "
                    f"'{existing.model_id}'"
                )
            if existing.spec.port == spec.port:
                raise ValueError(
                    f"Port {spec.port} is already bound by deployment '{existing.model_id}'"
                )
        service = ModelService(spec, cache_steps=self._cache_steps)
        self._services[spec.model_id] = service
        return service

    def unregister(self, model_id: str) -> bool:
        service = self._services.pop(model_id, None)
        if service is None:
            return False
        service.terminate()
        return True

    def get(self, model_id: str) -> Optional[ModelService]:
        return self._services.get(model_id)

    def services(self) -> List[ModelService]:
        return list(self._services.values())

    def start(self, model_id: str) -> None:
        service = self._require(model_id)
        if not self._can_schedule(service):
            requested = service.spec.gpu_count * service.spec.replicas
            service.fail(
                f"Cannot schedule '{model_id}': {requested} GPU(s) requested, "
                f"{self._gpu_capacity - self.allocated_gpus(exclude=model_id)} available. "
                f"Stop another deployment or lower resources.limits.gpu.",
                FailureReason.GPU_UNAVAILABLE,
            )
            return
        service.start()

    def stop(self, model_id: str) -> None:
        self._require(model_id).stop()

    def restart(self, model_id: str) -> None:
        self._require(model_id).restart()

    def progress(self, model_id: str) -> DeploymentState:
        return self._require(model_id).progress()

    def start_all(self) -> None:
        for model_id in list(self._services):
            self.start(model_id)

    def stop_all(self) -> None:
        for service in self._services.values():
            service.stop()

    def health(self) -> Dict[str, Any]:
        services = [service.health() for service in self._services.values()]
        health: Dict[str, Any] = {
            "healthy": all(entry["ready"] for entry in services) if services else False,
            "services": services,
        }
        if self._gpu_capacity is not None:
            health["gpu"] = {
                "capacity": self._gpu_capacity,
                "allocated": self.allocated_gpus(),
            }
        return health

    def _can_schedule(self, service: ModelService) -> bool:
        if self._gpu_capacity is None:
            return True
        requested = service.spec.gpu_count * service.spec.replicas
        return self.allocated_gpus(exclude=service.model_id) + requested <= self._gpu_capacity

    def _require(self, model_id: str) -> ModelService:
        service = self._services.get(model_id)
        if service is None:
            raise KeyError(f"Unknown model deployment: {model_id}")
        return service


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "models" / "services.json"


def load_default_specs(catalog_path: Path | str = DEFAULT_CATALOG_PATH) -> List[ModelServiceSpec]:
    """Load deployment specs from the catalog, falling back to built-in defaults."""
    path = Path(catalog_path)
    if not path.is_file():
        return list(BUILTIN_SPECS)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ModelServiceSpec.from_mapping(entry) for entry in payload.get("services", [])]


def load_spec(model_id: str, catalog_path: Path | str = DEFAULT_CATALOG_PATH) -> ModelServiceSpec:
    """Load the single spec a service instance is responsible for."""
    for spec in load_default_specs(catalog_path):
        if spec.model_id == model_id:
            return spec
    raise KeyError(f"No service catalog entry for model '{model_id}'")


BUILTIN_SPECS: List[ModelServiceSpec] = [
    ModelServiceSpec(
        model_id="yolo",
        workload_type=WorkloadType.PREDICTIVE,
        bundle_model_id="yolo",
        secret="yolo-secret",
        compute=ComputeTarget.GPU,
        resources=ResourceConfig(
            requests=ResourceRequests(cpu="500m", memory="1Gi"),
            limits=ResourceLimits(cpu="2000m", memory="4Gi", gpu=1),
        ),
        port=8001,
    ),
    ModelServiceSpec(
        model_id="florence-2",
        workload_type=WorkloadType.PREDICTIVE,
        bundle_model_id="florence-2",
        secret="florence-2-secret",
        compute=ComputeTarget.GPU,
        resources=ResourceConfig(
            requests=ResourceRequests(cpu="500m", memory="2Gi"),
            limits=ResourceLimits(cpu="2000m", memory="6Gi", gpu=1),
        ),
        port=8002,
    ),
    ModelServiceSpec(
        model_id="phi-4-multimodal",
        workload_type=WorkloadType.GENERATIVE,
        bundle_model_id="phi-4-multimodal",
        secret="phi-4-multimodal-secret",
        compute=ComputeTarget.GPU,
        resources=ResourceConfig(
            requests=ResourceRequests(cpu="1000m", memory="4Gi"),
            limits=ResourceLimits(cpu="4000m", memory="10Gi", gpu=1),
        ),
        port=8003,
    ),
]

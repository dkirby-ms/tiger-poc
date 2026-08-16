import json

import pytest

from apps.local_model_runtime import (
    ComputeTarget,
    DeploymentState,
    InferenceRuntime,
    LocalFoundryDeploymentRuntime,
    ModelService,
    ModelServiceSpec,
    ModelServiceSupervisor,
    ResourceConfig,
    ResourceLimits,
    ResourceRequests,
    WorkloadType,
    load_default_specs,
)


def spec(model_id="yolo", workload_type=WorkloadType.PREDICTIVE, **overrides):
    return ModelServiceSpec(
        model_id=model_id,
        workload_type=workload_type,
        bundle_model_id=overrides.pop("bundle_model_id", model_id),
        secret=overrides.pop("secret", f"{model_id}-secret"),
        port=overrides.pop("port", 8080),
        **overrides,
    )


class TestModelServiceSpec:
    def test_route_and_path_derive_from_workload_and_name(self):
        assert spec("yolo").route == "/v1/predict"
        assert spec("florence-2").route == "/v1/predict"
        assert spec("phi-4-multimodal", WorkloadType.GENERATIVE).route == "/v1/chat/completions"
        assert spec("yolo").path_prefix == "/yolo"

    def test_vllm_requires_gpu_compute(self):
        with pytest.raises(ValueError, match="requires compute 'gpu'"):
            spec(
                "phi-4-multimodal",
                WorkloadType.GENERATIVE,
                runtime=InferenceRuntime.VLLM,
                compute=ComputeTarget.CPU,
            ).validate()

    def test_vllm_does_not_serve_predictive_workloads(self):
        with pytest.raises(ValueError, match="predictive"):
            spec(
                "yolo",
                runtime=InferenceRuntime.VLLM,
                compute=ComputeTarget.GPU,
            ).validate()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"replicas": 0},
            {"replicas": 101},
            {"port": 80},
            {"port": 70000},
        ],
    )
    def test_out_of_range_fields_are_rejected(self, overrides):
        with pytest.raises(ValueError):
            spec("yolo", **overrides).validate()

    @pytest.mark.parametrize(
        "resources",
        [
            ResourceConfig(requests=ResourceRequests(cpu="half")),
            ResourceConfig(requests=ResourceRequests(memory="2 gigs")),
            ResourceConfig(limits=ResourceLimits(gpu=9)),
        ],
    )
    def test_invalid_resource_quantities_are_rejected(self, resources):
        with pytest.raises(ValueError):
            spec("yolo", resources=resources).validate()

    def test_kubernetes_quantities_are_accepted(self):
        config = ResourceConfig(
            requests=ResourceRequests(cpu="500m", memory="1Gi"),
            limits=ResourceLimits(cpu="2", memory="4Gi", gpu=1),
        )

        config.validate()

        assert config.as_dict() == {
            "requests": {"cpu": "500m", "memory": "1Gi"},
            "limits": {"cpu": "2", "memory": "4Gi", "gpu": 1},
        }


class TestModelServiceLifecycle:
    def test_states_follow_the_model_deployment_lifecycle(self):
        service = ModelService(spec())

        assert service.state is DeploymentState.PENDING
        assert service.health()["ready"] is False

        service.start()
        health = service.health()
        assert service.state is DeploymentState.RUNNING
        assert health["deploymentReady"] is True
        assert health["endpointReady"] is True
        assert health["replicas"] == {"desired": 1, "ready": 1, "available": 1}
        assert health["loaded_bundle"] == "yolo"

        service.stop()
        assert service.state is DeploymentState.PENDING
        assert service.health()["replicas"]["ready"] == 0

        service.terminate()
        assert service.state is DeploymentState.TERMINATING
        assert service.health()["serviceReady"] is False

    def test_failure_reports_an_actionable_message(self):
        service = ModelService(spec())
        service.start()

        with pytest.raises(RuntimeError, match="already hosts bundle"):
            service.load_bundle("florence-2")

        health = service.health()
        assert service.state is DeploymentState.ERROR
        assert "florence-2" in health["message"]
        assert health["ready"] is False

    def test_health_reports_scheduling_configuration(self):
        service = ModelService(
            spec(
                "phi-4-multimodal",
                WorkloadType.GENERATIVE,
                compute=ComputeTarget.GPU,
                resources=ResourceConfig(limits=ResourceLimits(gpu=2)),
            )
        )

        health = service.health()

        assert health["workloadType"] == "generative"
        assert health["compute"] == "gpu"
        assert health["runtime"] == "onnx-genai"
        assert health["resources"]["limits"]["gpu"] == 2

    def test_replicas_must_all_be_ready(self):
        service = ModelService(spec("yolo", replicas=3))
        service.start()

        assert service.health()["replicas"] == {"desired": 3, "ready": 3, "available": 3}
        assert service.ready is True


class TestModelServiceSupervisor:
    def test_deployments_start_and_stop_independently(self):
        supervisor = ModelServiceSupervisor(
            [
                spec("yolo", port=8001),
                spec("phi-4-multimodal", WorkloadType.GENERATIVE, port=8003),
            ]
        )
        supervisor.start_all()

        supervisor.stop("yolo")

        assert supervisor.get("yolo").ready is False
        assert supervisor.get("phi-4-multimodal").ready is True
        assert supervisor.health()["healthy"] is False

    def test_duplicate_bundle_across_deployments_is_rejected(self):
        supervisor = ModelServiceSupervisor([spec("yolo", port=8001)])

        with pytest.raises(ValueError, match="already hosted"):
            supervisor.register(
                spec("yolo-copy", bundle_model_id="yolo", secret="copy-secret", port=8002)
            )

    def test_duplicate_port_is_rejected(self):
        supervisor = ModelServiceSupervisor([spec("yolo", port=8001)])

        with pytest.raises(ValueError, match="already bound"):
            supervisor.register(spec("florence-2", port=8001))

    def test_duplicate_model_id_is_rejected(self):
        supervisor = ModelServiceSupervisor([spec("yolo")])

        with pytest.raises(ValueError, match="already registered"):
            supervisor.register(spec("yolo", secret="other-secret"))

    def test_unknown_deployment_lifecycle_calls_raise(self):
        supervisor = ModelServiceSupervisor()

        with pytest.raises(KeyError):
            supervisor.start("unknown")

    def test_catalog_drives_deployment_definitions(self, tmp_path):
        catalog = tmp_path / "services.json"
        catalog.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "model_id": "custom",
                            "workloadType": "generative",
                            "secret": "custom-secret",
                            "compute": "gpu",
                            "runtime": "vllm",
                            "replicas": 2,
                            "port": 9001,
                            "resources": {"limits": {"cpu": "4", "memory": "8Gi", "gpu": 2}},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        supervisor = ModelServiceSupervisor.from_catalog(catalog)
        service = supervisor.get("custom")

        assert service.spec.route == "/v1/chat/completions"
        assert service.spec.runtime is InferenceRuntime.VLLM
        assert service.spec.replicas == 2
        assert service.spec.resources.limits.gpu == 2


class TestDefaultCatalog:
    def test_repository_catalog_defines_one_deployment_per_model(self):
        specs = load_default_specs()

        assert {item.model_id for item in specs} == {"yolo", "florence-2", "phi-4-multimodal"}
        assert len({item.bundle_model_id for item in specs}) == 3
        assert len({item.secret for item in specs}) == 3
        assert len({item.port for item in specs}) == 3

    def test_runtime_backs_each_deployment_with_its_own_service(self):
        runtime = LocalFoundryDeploymentRuntime()

        health = runtime.health()
        assert health["healthy"] is True
        assert len(health["services"]) == 3

        runtime.set_ready("yolo", False)
        services = {entry["model_id"]: entry for entry in runtime.health()["services"]}
        assert services["yolo"]["ready"] is False
        assert services["yolo"]["state"] == "Pending"
        assert services["florence-2"]["ready"] is True

    def test_runtime_accepts_injected_specs(self):
        runtime = LocalFoundryDeploymentRuntime([spec("only-model")])

        assert {d.model_id for d in runtime.list_deployments()} == {"only-model"}
        assert runtime.dispatch(
            "only-model",
            "/v1/predict",
            "only-model-secret",
            {"image": "data"},
        )["status"] == "ok"

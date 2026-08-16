import pytest

from apps.local_model_runtime import (
    ComputeTarget,
    DeploymentState,
    FailureReason,
    ModelService,
    ModelServiceSpec,
    ModelServiceSupervisor,
    ResourceConfig,
    ResourceLimits,
    WorkloadType,
)


def spec(model_id="yolo", workload_type=WorkloadType.PREDICTIVE, gpus=None, **overrides):
    resources = overrides.pop(
        "resources", ResourceConfig(limits=ResourceLimits(gpu=gpus)) if gpus else ResourceConfig()
    )
    return ModelServiceSpec(
        model_id=model_id,
        workload_type=workload_type,
        bundle_model_id=overrides.pop("bundle_model_id", model_id),
        secret=overrides.pop("secret", f"{model_id}-secret"),
        compute=overrides.pop("compute", ComputeTarget.GPU if gpus else ComputeTarget.CPU),
        resources=resources,
        port=overrides.pop("port", 8080),
        **overrides,
    )


class TestModelCacheDelay:
    def test_deployment_stays_creating_until_the_cache_is_populated(self):
        service = ModelService(spec(), cache_steps=2)

        service.start()
        assert service.state is DeploymentState.CREATING
        assert service.ready is False
        assert "model cache" in service.message

        assert service.progress() is DeploymentState.CREATING
        assert service.progress() is DeploymentState.RUNNING
        assert service.ready is True
        assert service.message is None

    def test_progress_is_a_no_op_outside_creating(self):
        service = ModelService(spec())
        service.start()

        assert service.progress() is DeploymentState.RUNNING

    def test_no_delay_starts_immediately(self):
        service = ModelService(spec())

        service.start()

        assert service.state is DeploymentState.RUNNING

    def test_negative_cache_steps_are_rejected(self):
        with pytest.raises(ValueError):
            ModelService(spec(), cache_steps=-1)


class TestGpuScheduling:
    def test_deployment_that_exceeds_gpu_capacity_reports_an_error(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", gpus=1, port=8001), spec("phi-4-multimodal", WorkloadType.GENERATIVE, gpus=2, port=8003)],
            gpu_capacity=2,
        )

        supervisor.start("yolo")
        supervisor.start("phi-4-multimodal")

        yolo = supervisor.get("yolo")
        phi = supervisor.get("phi-4-multimodal")
        assert yolo.state is DeploymentState.RUNNING
        assert phi.state is DeploymentState.ERROR
        assert phi.reason is FailureReason.GPU_UNAVAILABLE
        assert "GPU" in phi.message

    def test_capacity_frees_when_another_deployment_stops(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", gpus=2, port=8001), spec("florence-2", gpus=2, port=8002)],
            gpu_capacity=2,
        )

        supervisor.start_all()
        assert supervisor.get("florence-2").state is DeploymentState.ERROR

        supervisor.stop("yolo")
        supervisor.start("florence-2")

        assert supervisor.get("florence-2").state is DeploymentState.RUNNING
        assert supervisor.health()["gpu"] == {"capacity": 2, "allocated": 2}

    def test_replicas_multiply_the_gpu_request(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", gpus=1, replicas=3, port=8001)], gpu_capacity=2
        )

        supervisor.start("yolo")

        assert supervisor.get("yolo").reason is FailureReason.GPU_UNAVAILABLE

    def test_unlimited_capacity_schedules_everything(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", gpus=8, port=8001), spec("florence-2", gpus=8, port=8002)]
        )

        supervisor.start_all()

        assert all(service.ready for service in supervisor.services())
        assert "gpu" not in supervisor.health()


class TestFailureAndRestart:
    def test_runtime_failure_reports_reason_and_message(self):
        service = ModelService(spec())
        service.start()

        service.fail("ONNX Runtime session crashed", FailureReason.RUNTIME_UNHEALTHY)

        health = service.health()
        assert health["state"] == "Error"
        assert health["reason"] == "ModelRuntimeUnhealthy"
        assert health["message"] == "ONNX Runtime session crashed"
        assert health["ready"] is False

    def test_restart_clears_the_failure_and_counts(self):
        service = ModelService(spec())
        service.start()
        service.fail("ONNX Runtime session crashed")

        service.restart()

        health = service.health()
        assert health["state"] == "Running"
        assert health["reason"] is None
        assert health["restartCount"] == 1

    def test_failure_in_one_deployment_leaves_others_healthy(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", port=8001), spec("florence-2", port=8002)]
        )
        supervisor.start_all()

        supervisor.get("yolo").fail("GPU fell off the bus")

        assert supervisor.get("florence-2").ready is True
        states = {entry["model_id"]: entry["state"] for entry in supervisor.health()["services"]}
        assert states == {"yolo": "Error", "florence-2": "Running"}

    def test_restart_through_the_supervisor_targets_one_deployment(self):
        supervisor = ModelServiceSupervisor(
            [spec("yolo", port=8001), spec("florence-2", port=8002)]
        )
        supervisor.start_all()

        supervisor.restart("yolo")

        assert supervisor.get("yolo").restart_count == 1
        assert supervisor.get("florence-2").restart_count == 0


class TestUpdate:
    def test_update_applies_a_new_spec_and_returns_to_running(self):
        service = ModelService(spec("yolo", replicas=1))
        service.start()

        service.update(spec("yolo", replicas=3))

        assert service.state is DeploymentState.RUNNING
        assert service.health()["replicas"]["desired"] == 3
        assert service.ready is True

    def test_update_leaves_a_stopped_deployment_pending(self):
        service = ModelService(spec("yolo"))

        service.update(spec("yolo", replicas=2))

        assert service.state is DeploymentState.UPDATING
        assert service.ready is False

    def test_update_cannot_rename_the_deployment(self):
        service = ModelService(spec("yolo"))

        with pytest.raises(ValueError, match="cannot change the deployment name"):
            service.update(spec("florence-2"))

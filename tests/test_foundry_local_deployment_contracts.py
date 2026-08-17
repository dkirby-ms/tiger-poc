import pytest

from apps.local_model_runtime.foundry_contract import LocalFoundryDeploymentRuntime, DeploymentConfig, DeploymentState
from apps.local_model_runtime.deployment_registry import DeploymentRegistry


def predictive_payload(data="data", **values):
    return {
        "items": [{"content_type": "image/jpeg", "encoder": "base64", "data": data}],
        **values,
    }


@pytest.fixture
def runtime():
    return LocalFoundryDeploymentRuntime()


@pytest.fixture
def registry():
    return DeploymentRegistry()


# ============================================================================
# EXISTING TESTS - Backward Compatibility
# ============================================================================


def test_three_deployments_are_present_with_unique_routes_and_secrets(runtime):
    contracts = runtime.deployment_contracts

    assert len(contracts) == 3
    assert {contract.model_id for contract in contracts} == {
        "yolo",
        "florence-2",
        "phi-4-multimodal",
    }
    assert {contract.route for contract in contracts} == {
        "/v1/predict",
        "/v1/chat/completions",
    }
    assert len({contract.secret for contract in contracts}) == 3
    assert {contract.route for contract in contracts if contract.model_id in {"yolo", "florence-2"}} == {"/v1/predict"}
    assert {contract.route for contract in contracts if contract.model_id == "phi-4-multimodal"} == {"/v1/chat/completions"}


def test_predictive_and_generative_routes_use_the_expected_payload_semantics(runtime):
    assert runtime.dispatch(
        "yolo",
        "/v1/predict",
        "yolo-secret",
        predictive_payload("base64-image-data", confidence_threshold=0.5),
    )["status"] == "ok"

    wrong_predictive_payload = runtime.dispatch(
        "yolo",
        "/v1/predict",
        "yolo-secret",
        {"messages": [{"role": "user", "content": "Describe the image."}]},
    )
    assert wrong_predictive_payload["status"] == "wrong_payload"

    assert runtime.dispatch(
        "phi-4-multimodal",
        "/v1/chat/completions",
        "phi-4-multimodal-secret",
        {"messages": [{"role": "user", "content": "Describe the image."}]},
    )["status"] == "ok"

    wrong_generative_payload = runtime.dispatch(
        "phi-4-multimodal",
        "/v1/chat/completions",
        "phi-4-multimodal-secret",
        {"image": "base64-image-data", "confidence_threshold": 0.5},
    )
    assert wrong_generative_payload["status"] == "wrong_payload"


def test_wrong_auth_and_non_ready_deployments_are_rejected_without_fallback(runtime):
    unauthorized = runtime.dispatch(
        "florence-2",
        "/v1/predict",
        "yolo-secret",
        {"image": "base64-image-data", "confidence_threshold": 0.5},
    )
    assert unauthorized["status"] == "unauthorized"

    wrong_route = runtime.dispatch(
        "yolo",
        "/v1/chat/completions",
        "yolo-secret",
        {"messages": [{"role": "user", "content": "Describe the image."}]},
    )
    assert wrong_route["status"] == "wrong_route"

    runtime.set_ready("yolo", False)
    non_ready = runtime.dispatch(
        "yolo",
        "/v1/predict",
        "yolo-secret",
        {"image": "base64-image-data", "confidence_threshold": 0.5},
    )
    assert non_ready["status"] == "not_ready"


# ============================================================================
# NEW TESTS - Deployment Lifecycle Management
# ============================================================================


class TestDeploymentRegistry:
    """Tests for DeploymentRegistry lifecycle operations."""

    def test_create_deployment_from_config(self, registry):
        """Test creating a deployment from configuration."""
        config = DeploymentConfig(
            model_id="test-model",
            route="/v1/predict",
            secret="test-secret"
        )
        
        contract = registry.create_deployment(config)
        
        assert contract.model_id == "test-model"
        assert contract.route == "/v1/predict"
        assert contract.secret == "test-secret"
        assert contract.status == DeploymentState.RUNNING
        assert contract.ready is True
        assert contract.created_at is not None
        assert contract.updated_at is not None

    def test_create_deployment_with_invalid_config(self, registry):
        """Test creating deployment with invalid config raises error."""
        config = DeploymentConfig(
            model_id="",  # Invalid: empty model_id
            route="/v1/predict",
            secret="test-secret"
        )
        
        with pytest.raises(ValueError):
            registry.create_deployment(config)

    def test_create_deployment_duplicate_model_id_raises_error(self, registry):
        """Test that duplicate model_id raises error."""
        config1 = DeploymentConfig(model_id="dup", route="/v1/predict", secret="secret1")
        config2 = DeploymentConfig(model_id="dup", route="/v1/predict", secret="secret2")
        
        registry.create_deployment(config1)
        
        with pytest.raises(ValueError, match="already exists"):
            registry.create_deployment(config2)

    def test_create_deployment_duplicate_secret_raises_error(self, registry):
        """Test that duplicate secret raises error."""
        config1 = DeploymentConfig(model_id="model1", route="/v1/predict", secret="dup-secret")
        config2 = DeploymentConfig(model_id="model2", route="/v1/predict", secret="dup-secret")
        
        registry.create_deployment(config1)
        
        with pytest.raises(ValueError, match="Secret already in use"):
            registry.create_deployment(config2)

    def test_get_deployment_returns_contract(self, registry):
        """Test getting deployment by model_id."""
        config = DeploymentConfig(model_id="test", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        contract = registry.get_deployment("test")
        
        assert contract is not None
        assert contract.model_id == "test"

    def test_get_deployment_returns_none_for_unknown(self, registry):
        """Test getting unknown deployment returns None."""
        contract = registry.get_deployment("unknown")
        assert contract is None

    def test_list_deployments_returns_all_active(self, registry):
        """Test listing all active deployments."""
        config1 = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret1")
        config2 = DeploymentConfig(model_id="model2", route="/v1/chat/completions", secret="secret2")
        
        registry.create_deployment(config1)
        registry.create_deployment(config2)
        
        deployments = registry.list_deployments()
        
        assert len(deployments) == 2
        assert {d.model_id for d in deployments} == {"model1", "model2"}

    def test_list_deployments_excludes_deleted(self, registry):
        """Test that deleted deployments are not listed."""
        config1 = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret1")
        config2 = DeploymentConfig(model_id="model2", route="/v1/predict", secret="secret2")
        
        registry.create_deployment(config1)
        registry.create_deployment(config2)
        registry.delete_deployment("model1")
        
        deployments = registry.list_deployments()
        
        assert len(deployments) == 1
        assert deployments[0].model_id == "model2"

    def test_delete_deployment_marks_as_deleted(self, registry):
        """Test deleting deployment."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        result = registry.delete_deployment("model1")
        
        assert result is True
        assert registry.get_deployment("model1") is None
        
        # Verify it's marked deleted internally
        deployments = registry.list_deployments()
        assert "model1" not in {d.model_id for d in deployments}

    def test_delete_deployment_nonexistent_returns_false(self, registry):
        """Test deleting nonexistent deployment returns False."""
        result = registry.delete_deployment("unknown")
        assert result is False

    def test_delete_deployment_twice_returns_false(self, registry):
        """Test deleting same deployment twice returns False."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        assert registry.delete_deployment("model1") is True
        assert registry.delete_deployment("model1") is False

    def test_set_ready_changes_status(self, registry):
        """Test setting deployment ready status."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        registry.set_ready("model1", False)
        
        contract = registry.get_deployment("model1")
        assert contract.ready is False

    def test_set_ready_unknown_deployment_raises_error(self, registry):
        """Test setting ready on unknown deployment raises error."""
        with pytest.raises(KeyError):
            registry.set_ready("unknown", False)

    def test_set_ready_deleted_deployment_raises_error(self, registry):
        """Test setting ready on deleted deployment raises error."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        registry.delete_deployment("model1")
        
        with pytest.raises(KeyError, match="Cannot modify deleted"):
            registry.set_ready("model1", False)

    def test_get_status_returns_deployment_state(self, registry):
        """Test getting deployment status."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        status = registry.get_status("model1")
        
        assert status == DeploymentState.RUNNING

    def test_get_status_unknown_returns_none(self, registry):
        """Test getting status for unknown deployment returns None."""
        status = registry.get_status("unknown")
        assert status is None

    def test_is_ready_true_when_ready(self, registry):
        """Test is_ready returns True for ready deployment."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        
        assert registry.is_ready("model1") is True

    def test_is_ready_false_when_not_ready(self, registry):
        """Test is_ready returns False when not ready."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        registry.set_ready("model1", False)
        
        assert registry.is_ready("model1") is False

    def test_is_ready_false_when_deleted(self, registry):
        """Test is_ready returns False for deleted deployment."""
        config = DeploymentConfig(model_id="model1", route="/v1/predict", secret="secret")
        registry.create_deployment(config)
        registry.delete_deployment("model1")
        
        assert registry.is_ready("model1") is False


class TestDeploymentLifecycleIntegration:
    """Integration tests for deployment lifecycle with runtime."""

    def test_runtime_creates_deployment_from_config(self, runtime):
        """Test runtime can create new deployment."""
        config = DeploymentConfig(
            model_id="custom-model",
            route="/v1/predict",
            secret="custom-secret"
        )
        
        contract = runtime.create_deployment(config)
        
        assert contract.model_id == "custom-model"
        assert contract in runtime.list_deployments()

    def test_runtime_deletes_deployment(self, runtime):
        """Test runtime can delete deployment."""
        config = DeploymentConfig(model_id="to-delete", route="/v1/predict", secret="secret")
        runtime.create_deployment(config)
        
        result = runtime.delete_deployment("to-delete")
        
        assert result is True
        assert "to-delete" not in {d.model_id for d in runtime.list_deployments()}

    def test_dispatch_works_after_deployment_creation(self, runtime):
        """Test dispatch works with dynamically created deployment."""
        config = DeploymentConfig(model_id="new-model", route="/v1/predict", secret="new-secret")
        runtime.create_deployment(config)
        
        result = runtime.dispatch(
            "new-model",
            "/v1/predict",
            "new-secret",
            predictive_payload()
        )
        
        assert result["status"] == "ok"

    def test_dispatch_fails_after_deletion(self, runtime):
        """Test dispatch fails after deployment is deleted."""
        config = DeploymentConfig(model_id="to-remove", route="/v1/predict", secret="secret")
        runtime.create_deployment(config)
        runtime.delete_deployment("to-remove")
        
        result = runtime.dispatch(
            "to-remove",
            "/v1/predict",
            "secret",
            {"image": "data"}
        )
        
        assert result["status"] == "unknown_model"

    def test_deployment_state_changes_are_observable(self, runtime):
        """Test that deployment state changes are observable."""
        config = DeploymentConfig(model_id="observable", route="/v1/predict", secret="secret")
        contract = runtime.create_deployment(config)
        
        # Initial state is READY
        assert contract.status == DeploymentState.RUNNING
        
        # Change ready status
        runtime.set_ready("observable", False)
        
        # Observable via get_status
        status = runtime.get_status("observable")
        assert status == DeploymentState.RUNNING  # Status remains, but ready flag changed
        
        # Dispatch fails because not ready
        result = runtime.dispatch(
            "observable",
            "/v1/predict",
            "secret",
            {"image": "data"}
        )
        assert result["status"] == "not_ready"

    def test_isolated_deployments_have_unique_credentials(self, runtime):
        """Test that deployments are isolated with unique credentials."""
        config1 = DeploymentConfig(model_id="isolated1", route="/v1/predict", secret="secret1")
        config2 = DeploymentConfig(model_id="isolated2", route="/v1/predict", secret="secret2")
        
        runtime.create_deployment(config1)
        runtime.create_deployment(config2)
        
        # Dispatch with wrong secret fails
        result = runtime.dispatch(
            "isolated1",
            "/v1/predict",
            "secret2",  # Wrong secret
            {"image": "data"}
        )
        assert result["status"] == "unauthorized"

    def test_default_deployments_exist_and_work(self, runtime):
        """Test that default deployments are auto-provisioned."""
        assert len(runtime.list_deployments()) == 3
        
        default_ids = {d.model_id for d in runtime.list_deployments()}
        assert default_ids == {"yolo", "florence-2", "phi-4-multimodal"}

    def test_control_plane_resolves_and_waits_for_local_deployment(self, runtime):
        """Test the control-plane protocol methods used by pipeline stages."""
        assert runtime.get("yolo").model_id == "yolo"
        assert runtime.wait_ready("yolo", timeout_s=0) is True

        runtime.set_ready("yolo", False)

        assert runtime.wait_ready("yolo", timeout_s=0) is False

    def test_credentials_removed_after_deletion(self, runtime):
        """Test that credentials are not reusable after deletion."""
        config1 = DeploymentConfig(model_id="model1", route="/v1/predict", secret="unique-secret")
        runtime.create_deployment(config1)
        runtime.delete_deployment("model1")
        
        # Secret can now be reused
        config2 = DeploymentConfig(model_id="model2", route="/v1/predict", secret="unique-secret")
        contract = runtime.create_deployment(config2)
        
        assert contract.model_id == "model2"


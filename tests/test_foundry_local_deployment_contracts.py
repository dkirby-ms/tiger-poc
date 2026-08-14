import pytest

from apps.local_model_runtime.foundry_contract import LocalFoundryDeploymentRuntime


@pytest.fixture
def runtime():
    return LocalFoundryDeploymentRuntime()


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
        {"image": "base64-image-data", "confidence_threshold": 0.5},
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

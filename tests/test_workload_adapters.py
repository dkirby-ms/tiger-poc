import pytest

from apps.local_model_runtime import LocalFoundryDeploymentRuntime, WorkloadType
from apps.local_model_runtime.workload_adapters import adapter_for


def predictive_payload(*data):
    return {
        "items": [
            {"content_type": "image/jpeg", "encoder": "base64", "data": value}
            for value in data
        ]
    }


@pytest.fixture
def runtime():
    return LocalFoundryDeploymentRuntime()


class TestPredictiveAdapter:
    adapter = adapter_for(WorkloadType.PREDICTIVE)

    def test_accepts_a_minimal_predictive_payload(self):
        assert self.adapter.validate(predictive_payload("data")) is None

    @pytest.mark.parametrize(
        "payload,param",
        [
            ({}, "items"),
            ({"items": []}, "items"),
            ({"items": ["data"]}, "items[0]"),
            ({"items": [{"content_type": "image/png", "encoder": "base64", "data": "x"}]}, "items[0].content_type"),
            ({"items": [{"content_type": "image/jpeg", "encoder": "raw", "data": "x"}]}, "items[0].encoder"),
            ({"items": [{"content_type": "image/jpeg", "encoder": "base64", "data": ""}]}, "items[0].data"),
            ({**predictive_payload("data"), "messages": []}, "messages"),
            ({**predictive_payload("data"), "confidence_threshold": "high"}, "confidence_threshold"),
            ({**predictive_payload("data"), "confidence_threshold": 1.5}, "confidence_threshold"),
        ],
    )
    def test_rejects_invalid_payloads_with_the_offending_param(self, payload, param):
        error = self.adapter.validate(payload)

        assert error is not None
        assert error.param == param
        assert error.type == "invalid_request_error"
        assert error.message

    def test_response_shape(self):
        response = self.adapter.build_response("yolo", predictive_payload("first", "second"))

        assert response["object"] == "prediction"
        assert response["model"] == "yolo"
        assert response["predictions"] == [[], []]
        assert response["usage"]["images"] == 2
        assert response["id"].startswith("pred-")


class TestGenerativeAdapter:
    adapter = adapter_for(WorkloadType.GENERATIVE)

    def test_accepts_a_minimal_chat_payload(self):
        assert self.adapter.validate({"messages": [{"role": "user", "content": "hi"}]}) is None

    @pytest.mark.parametrize(
        "payload,param",
        [
            ({}, "messages"),
            ({"messages": []}, "messages"),
            ({"messages": "hi"}, "messages"),
            ({"messages": ["hi"]}, "messages[0]"),
            ({"messages": [{"role": "user"}]}, "messages[0].content"),
            ({"messages": [{"content": "hi"}]}, "messages[0].role"),
            ({"messages": [{"role": "user", "content": "hi"}], "items": []}, "items"),
        ],
    )
    def test_rejects_invalid_payloads_with_the_offending_param(self, payload, param):
        error = self.adapter.validate(payload)

        assert error is not None
        assert error.param == param

    def test_response_is_openai_chat_completion_compatible(self):
        response = self.adapter.build_response(
            "phi-4-multimodal", {"messages": [{"role": "user", "content": "Describe the image."}]}
        )

        assert response["object"] == "chat.completion"
        assert response["id"].startswith("chatcmpl-")
        assert response["model"] == "phi-4-multimodal"
        assert isinstance(response["created"], int)

        choice = response["choices"][0]
        assert choice["index"] == 0
        assert choice["message"]["role"] == "assistant"
        assert choice["message"]["content"]
        assert choice["finish_reason"] == "stop"

        usage = response["usage"]
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


class TestAdapterSelectionIsWorkloadBased:
    def test_all_predictive_services_share_one_adapter(self, runtime):
        yolo = runtime.dispatch("yolo", "/v1/predict", "yolo-secret", predictive_payload("data"))
        florence = runtime.dispatch(
            "florence-2", "/v1/predict", "florence-2-secret", predictive_payload("data")
        )

        assert yolo["response"]["object"] == florence["response"]["object"] == "prediction"
        assert yolo["response"]["model"] == "yolo"
        assert florence["response"]["model"] == "florence-2"

    def test_dispatch_reports_contract_errors_with_detail(self, runtime):
        result = runtime.dispatch(
            "phi-4-multimodal",
            "/v1/chat/completions",
            "phi-4-multimodal-secret",
            {"messages": []},
        )

        assert result["status"] == "wrong_payload"
        assert result["param"] == "messages"
        assert "non-empty" in result["message"]

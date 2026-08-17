import json
import threading
import urllib.error
import urllib.request

import pytest

from apps.local_model_runtime import (
    ModelServiceHTTPServer,
    ModelServiceSpec,
    ResourceConfig,
    WorkloadType,
    load_default_specs,
)
from apps.local_model_runtime.__main__ import main, parse_args


def spec(model_id="yolo", workload_type=WorkloadType.PREDICTIVE, secret="yolo-secret"):
    return ModelServiceSpec(
        model_id=model_id,
        workload_type=workload_type,
        bundle_model_id=model_id,
        secret=secret,
        resources=ResourceConfig(),
    )


def request(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def predictive_payload(data="data", **values):
    return {
        "items": [{"content_type": "image/jpeg", "encoder": "base64", "data": data}],
        **values,
    }


@pytest.fixture
def served():
    def _serve(service_spec):
        server = ModelServiceHTTPServer(service_spec, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, f"http://127.0.0.1:{server.port}"

    servers = []

    def factory(service_spec=None):
        server, base = _serve(service_spec or spec())
        servers.append(server)
        return server, base

    yield factory

    for server in servers:
        server.shutdown()
        server.close()


class TestModelServiceHTTP:
    def test_health_reports_the_single_hosted_model(self, served):
        _, base = served()

        status, body = request(f"{base}/healthz")

        assert status == 200
        assert body["model_id"] == "yolo"
        assert body["ready"] is True
        assert body["state"] == "Running"
        assert body["deploymentReady"] is True
        assert body["endpointReady"] is True
        assert body["path"] == "/yolo"
        assert body["loaded_bundle"] == "yolo"

    def test_models_lists_exactly_one_model(self, served):
        _, base = served()

        status, body = request(f"{base}/v1/models")

        assert status == 200
        assert [entry["id"] for entry in body["data"]] == ["yolo"]
        assert body["data"][0]["available"] is True
        assert body["data"][0]["workloadType"] == "predictive"
        assert body["data"][0]["runtime"] == "onnx-genai"

    def test_predictive_inference_requires_the_service_credential(self, served):
        _, base = served()
        payload = predictive_payload("base64-image-data")

        unauthorized, body = request(f"{base}/v1/predict", "POST", payload, {"Authorization": "Bearer nope"})
        assert unauthorized == 401
        assert body["error"]["type"] == "authentication_error"

        status, body = request(
            f"{base}/v1/predict", "POST", payload, {"X-API-Key": "yolo-secret"}
        )
        assert status == 200
        assert body["object"] == "prediction"
        assert body["model"] == "yolo"
        assert "secret" not in json.dumps(body)

    def test_legacy_api_key_header_is_rejected(self, served):
        _, base = served()

        status, _ = request(
            f"{base}/v1/predict",
            "POST",
            predictive_payload(),
            {"api-key": "yolo-secret"},
        )

        assert status == 401

    def test_generative_service_serves_only_its_own_route(self, served):
        _, base = served(spec("phi-4-multimodal", WorkloadType.GENERATIVE, "phi-secret"))
        headers = {"Authorization": "Bearer phi-secret"}

        status, body = request(
            f"{base}/v1/chat/completions",
            "POST",
            {"messages": [{"role": "user", "content": "Describe the image."}]},
            headers,
        )
        assert status == 200
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert body["choices"][0]["finish_reason"] == "stop"
        assert body["usage"]["total_tokens"] > 0

        wrong_route, error_body = request(f"{base}/v1/predict", "POST", predictive_payload(), headers)
        assert wrong_route == 404
        assert error_body["error"]["type"] == "not_found_error"

    def test_payload_mismatch_is_rejected(self, served):
        _, base = served()

        status, body = request(
            f"{base}/v1/predict",
            "POST",
            {"messages": [{"role": "user", "content": "hi"}]},
            {"X-API-Key": "yolo-secret"},
        )

        assert status == 400
        assert body["status"] == "wrong_payload"
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["param"] == "items"
        assert "items" in body["error"]["message"]

    def test_invalid_field_value_reports_the_offending_param(self, served):
        _, base = served()

        status, body = request(
            f"{base}/v1/predict",
            "POST",
            predictive_payload(confidence_threshold=5),
            {"X-API-Key": "yolo-secret"},
        )

        assert status == 400
        assert body["error"]["param"] == "confidence_threshold"

    def test_malformed_json_is_rejected(self, served):
        _, base = served()
        req = urllib.request.Request(
            f"{base}/v1/predict",
            data=b"not-json",
            method="POST",
            headers={"X-API-Key": "yolo-secret"},
        )

        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req, timeout=5)

        assert error.value.code == 400

    def test_stopped_service_reports_unavailable(self, served):
        server, base = served()
        server.endpoint.set_ready(False)

        health_status, health_body = request(f"{base}/healthz")
        infer_status, infer_body = request(
            f"{base}/v1/predict", "POST", predictive_payload(), {"X-API-Key": "yolo-secret"}
        )

        assert health_status == 503
        assert health_body["state"] == "Pending"
        assert health_body["replicas"]["ready"] == 0
        assert infer_status == 503
        assert infer_body["error"]["state"] == "Pending"

    def test_services_run_on_separate_ports(self, served):
        _, yolo_base = served()
        _, phi_base = served(spec("phi-4-multimodal", WorkloadType.GENERATIVE, "phi-secret"))

        assert yolo_base != phi_base
        assert request(f"{yolo_base}/v1/models")[1]["data"][0]["id"] == "yolo"
        assert request(f"{phi_base}/v1/models")[1]["data"][0]["id"] == "phi-4-multimodal"

    def test_unknown_path_returns_not_found(self, served):
        _, base = served()

        status, _ = request(f"{base}/nope")

        assert status == 404


class TestEntryPoint:
    def test_catalog_assigns_a_distinct_port_to_every_service(self):
        specs = load_default_specs()
        ports = [item.port for item in specs]

        assert all(port > 0 for port in ports)
        assert len(set(ports)) == len(ports)

    def test_args_default_to_environment(self, monkeypatch):
        monkeypatch.setenv("MODEL_ID", "florence-2")
        monkeypatch.setenv("MODEL_SERVICE_PORT", "9100")

        args = parse_args([])

        assert args.model_id == "florence-2"
        assert args.port == 9100

    def test_missing_model_id_exits_with_usage_error(self, monkeypatch, capsys):
        monkeypatch.delenv("MODEL_ID", raising=False)

        assert main([]) == 2
        assert "--model-id" in capsys.readouterr().err

    def test_unknown_model_id_exits_with_usage_error(self, capsys):
        assert main(["--model-id", "not-in-catalog"]) == 2
        assert "not-in-catalog" in capsys.readouterr().err

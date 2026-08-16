import json
import threading
import urllib.error
import urllib.request

import pytest

from apps.local_model_runtime import (
    EndpointConfig,
    EndpointExposure,
    Gateway,
    GatewayHTTPServer,
    ModelServiceHTTPServer,
    ModelServiceSpec,
    WorkloadType,
)


def spec(model_id="yolo", workload_type=WorkloadType.PREDICTIVE, port=8080, **overrides):
    return ModelServiceSpec(
        model_id=model_id,
        workload_type=workload_type,
        bundle_model_id=model_id,
        secret=f"{model_id}-secret",
        port=port,
        **overrides,
    )


def request(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


@pytest.fixture
def stack():
    """Start backends on ephemeral ports plus a gateway in front of them."""
    servers = []

    def factory(specs):
        bound = []
        for service_spec in specs:
            backend = ModelServiceHTTPServer(service_spec, host="127.0.0.1", port=0)
            threading.Thread(target=backend.serve_forever, daemon=True).start()
            servers.append(backend)
            bound.append(service_spec.__class__(**{**service_spec.__dict__, "port": backend.port}))

        gateway_server = GatewayHTTPServer(
            Gateway(bound, upstream_template="http://127.0.0.1:{port}"),
            host="127.0.0.1",
            port=0,
        )
        threading.Thread(target=gateway_server.serve_forever, daemon=True).start()
        servers.append(gateway_server)
        return gateway_server, f"http://127.0.0.1:{gateway_server.port}"

    yield factory

    for server in servers:
        server.shutdown()
        server.close()


class TestGatewayRouting:
    def test_path_prefix_routes_to_the_matching_deployment(self, stack):
        _, base = stack([spec("yolo"), spec("phi-4-multimodal", WorkloadType.GENERATIVE, 8081)])

        status, body = request(f"{base}/yolo/v1/models")

        assert status == 200
        assert body["data"][0]["id"] == "yolo"

    def test_each_prefix_reaches_only_its_own_deployment(self, stack):
        _, base = stack([spec("yolo"), spec("phi-4-multimodal", WorkloadType.GENERATIVE, 8081)])

        yolo = request(f"{base}/yolo/v1/models")[1]["data"][0]["id"]
        phi = request(f"{base}/phi-4-multimodal/v1/models")[1]["data"][0]["id"]

        assert yolo == "yolo"
        assert phi == "phi-4-multimodal"

    def test_credentials_are_forwarded_and_isolated(self, stack):
        _, base = stack([spec("yolo"), spec("florence-2", port=8081)])
        payload = {"image": "data"}

        ok, _ = request(
            f"{base}/yolo/v1/predict", "POST", payload, {"Authorization": "Bearer yolo-secret"}
        )
        crossed, _ = request(
            f"{base}/florence-2/v1/predict", "POST", payload, {"Authorization": "Bearer yolo-secret"}
        )

        assert ok == 200
        assert crossed == 401

    def test_unknown_prefix_returns_not_found(self, stack):
        _, base = stack([spec("yolo")])

        status, body = request(f"{base}/not-a-deployment/v1/models")

        assert status == 404
        assert body["error"]["code"] == "unknown_route"

    def test_routes_endpoint_describes_the_httproutes(self, stack):
        _, base = stack([spec("yolo")])

        status, body = request(f"{base}/routes")

        assert status == 200
        assert body["data"][0]["path"] == "/yolo"
        assert body["data"][0]["rewritePath"] == "/"

    def test_exposure_none_is_not_routed(self):
        gateway = Gateway(
            [
                spec("yolo", endpoint=EndpointConfig(exposure=EndpointExposure.NONE)),
                spec("florence-2", port=8081),
            ]
        )

        assert [route.spec.model_id for route in gateway.routes] == ["florence-2"]
        assert gateway.resolve("/yolo/v1/predict") is None

    def test_custom_path_and_rewrite_are_honored(self):
        gateway = Gateway(
            [spec("yolo", endpoint=EndpointConfig(path="/detect", rewrite_path="/"), port=9000)],
            upstream_template="http://127.0.0.1:{port}",
        )

        route = gateway.resolve("/detect/v1/predict")

        assert route is not None
        assert route.target("/detect/v1/predict") == "http://127.0.0.1:9000/v1/predict"

    def test_unreachable_upstream_reports_bad_gateway(self):
        gateway = Gateway(
            [spec("yolo", port=9)], upstream_template="http://127.0.0.1:{port}"
        )

        status, body = gateway.forward("GET", "/yolo/v1/models", {}, None)

        assert status == 502
        assert body["error"]["code"] == "upstream_unreachable"

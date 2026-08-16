"""Generic HTTP surface for a single-model service.

The same server implementation serves every model; the bound service spec
determines the route, credential, and payload contract.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from .foundry_contract import LocalFoundryDeploymentRuntime
from .model_service import ModelService, ModelServiceSpec

STATUS_CODES: Dict[str, HTTPStatus] = {
    "ok": HTTPStatus.OK,
    "unknown_model": HTTPStatus.NOT_FOUND,
    "not_ready": HTTPStatus.SERVICE_UNAVAILABLE,
    "wrong_route": HTTPStatus.NOT_FOUND,
    "unauthorized": HTTPStatus.UNAUTHORIZED,
    "wrong_payload": HTTPStatus.BAD_REQUEST,
}

ERROR_TYPES: Dict[str, str] = {
    "unknown_model": "not_found_error",
    "wrong_route": "not_found_error",
    "unauthorized": "authentication_error",
    "wrong_payload": "invalid_request_error",
    "not_ready": "service_unavailable_error",
}

DEFAULT_MESSAGES: Dict[str, str] = {
    "unknown_model": "This service does not host the requested model",
    "wrong_route": "This service does not serve the requested route",
    "unauthorized": "The supplied credential is not valid for this service",
    "wrong_payload": "The request payload does not match the service contract",
    "not_ready": "The service is not ready to accept requests",
}

MAX_REQUEST_BYTES = 32 * 1024 * 1024


class ModelServiceEndpoint:
    """Transport-independent request handling for one model service."""

    def __init__(self, spec: ModelServiceSpec):
        spec.validate()
        self._spec = spec
        self._runtime = LocalFoundryDeploymentRuntime([spec])

    @property
    def spec(self) -> ModelServiceSpec:
        return self._spec

    @property
    def service(self) -> ModelService:
        return self._runtime.supervisor.get(self._spec.model_id)

    def health(self) -> Tuple[HTTPStatus, Dict[str, Any]]:
        health = self.service.health()
        code = HTTPStatus.OK if health["ready"] else HTTPStatus.SERVICE_UNAVAILABLE
        return code, health

    def models(self) -> Tuple[HTTPStatus, Dict[str, Any]]:
        service = self.service
        return HTTPStatus.OK, {
            "object": "list",
            "data": [
                {
                    "id": self._spec.model_id,
                    "object": "model",
                    "available": service.ready,
                    "state": service.state.value,
                    "workloadType": self._spec.workload_type.value,
                    "runtime": self._spec.runtime.value,
                    "compute": self._spec.compute.value,
                    "route": self._spec.route,
                    "bundle_model_id": self._spec.bundle_model_id,
                }
            ],
        }

    def infer(
        self, route: str, secret: Optional[str], payload: Dict[str, Any]
    ) -> Tuple[HTTPStatus, Dict[str, Any]]:
        result = self._runtime.dispatch(
            model_id=self._spec.model_id,
            route=route,
            secret=secret or "",
            payload=payload,
        )
        status = result["status"]
        if status == "ok":
            return HTTPStatus.OK, result["response"]

        code = STATUS_CODES.get(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        service = self.service
        error = {
            "type": ERROR_TYPES.get(status, "api_error"),
            "code": status,
            "message": result.get("message") or DEFAULT_MESSAGES.get(status, status),
            "param": result.get("param"),
            "model": result.get("model_id", self._spec.model_id),
        }
        if status == "not_ready":
            error["state"] = service.state.value
            error["reason"] = service.reason.value if service.reason else None
            if service.message:
                error["message"] = service.message
        return code, {"status": status, "error": error}

    def set_ready(self, ready: bool) -> None:
        self._runtime.set_ready(self._spec.model_id, ready)


def extract_secret(headers) -> Optional[str]:
    """Read the service credential from either supported auth header."""
    authorization = headers.get("Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return headers.get("api-key")


def _make_handler(endpoint: ModelServiceEndpoint):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "TigerModelService/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _respond(self, code: HTTPStatus, body: Dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._respond(*endpoint.health())
                return
            if self.path == "/v1/models":
                self._respond(*endpoint.models())
                return
            self._respond(HTTPStatus.NOT_FOUND, {"status": "not_found", "path": self.path})

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._respond(HTTPStatus.BAD_REQUEST, {"status": "invalid_length"})
                return
            if length > MAX_REQUEST_BYTES:
                self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "payload_too_large"})
                return

            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._respond(HTTPStatus.BAD_REQUEST, {"status": "invalid_json"})
                return
            if not isinstance(payload, dict):
                self._respond(HTTPStatus.BAD_REQUEST, {"status": "invalid_json"})
                return

            self._respond(*endpoint.infer(self.path, extract_secret(self.headers), payload))

    return Handler


class ModelServiceHTTPServer:
    """Serves one model service over HTTP."""

    def __init__(self, spec: ModelServiceSpec, host: str = "0.0.0.0", port: Optional[int] = None):
        self.endpoint = ModelServiceEndpoint(spec)
        self._server = ThreadingHTTPServer((host, spec.port if port is None else port), _make_handler(self.endpoint))
        self._server.daemon_threads = True

    @property
    def address(self) -> Tuple[str, int]:
        return self._server.server_address[0], self._server.server_address[1]

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()

    def close(self) -> None:
        self._server.server_close()

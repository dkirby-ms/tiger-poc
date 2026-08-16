"""Gateway that routes `/<deployment-name>/...` to per-deployment services.

Mirrors the Foundry Local Gateway API HTTPRoute: a path prefix per deployment,
rewritten before the request reaches the backend. Deployments with
`endpoint.exposure: none` are reachable only by their direct service URL.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .model_service import EndpointExposure, ModelServiceSpec

DEFAULT_UPSTREAM_TEMPLATE = "http://127.0.0.1:{port}"
FORWARDED_HEADERS = ("Authorization", "api-key", "Content-Type", "Accept")
MAX_REQUEST_BYTES = 32 * 1024 * 1024


class GatewayRoute:
    """One HTTPRoute: a path prefix bound to a single deployment."""

    def __init__(self, spec: ModelServiceSpec, upstream_template: str):
        self.spec = spec
        self.prefix = spec.path_prefix.rstrip("/")
        self.rewrite_path = spec.endpoint.rewrite_path
        self.upstream = upstream_template.format(model_id=spec.model_id, port=spec.port).rstrip("/")

    def matches(self, path: str) -> bool:
        return path == self.prefix or path.startswith(f"{self.prefix}/")

    def target(self, path: str) -> str:
        remainder = path[len(self.prefix) :] or "/"
        rewritten = self.rewrite_path.rstrip("/") + remainder
        return f"{self.upstream}{rewritten}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.spec.model_id,
            "path": self.prefix,
            "rewritePath": self.rewrite_path,
            "exposure": self.spec.endpoint.exposure.value,
            "upstream": self.upstream,
        }


class Gateway:
    """Resolves request paths to deployment upstreams and proxies them."""

    def __init__(
        self,
        specs: Sequence[ModelServiceSpec],
        upstream_template: str = DEFAULT_UPSTREAM_TEMPLATE,
        timeout: float = 30.0,
    ):
        self._routes: List[GatewayRoute] = [
            GatewayRoute(spec, upstream_template)
            for spec in specs
            if spec.endpoint.exposure is not EndpointExposure.NONE
        ]
        self._timeout = timeout

    @property
    def routes(self) -> List[GatewayRoute]:
        return list(self._routes)

    def resolve(self, path: str) -> Optional[GatewayRoute]:
        for route in self._routes:
            if route.matches(path):
                return route
        return None

    def describe(self) -> Dict[str, Any]:
        return {"object": "list", "data": [route.as_dict() for route in self._routes]}

    def forward(
        self, method: str, path: str, headers: Dict[str, str], body: Optional[bytes]
    ) -> Tuple[int, Dict[str, Any]]:
        route = self.resolve(path)
        if route is None:
            return HTTPStatus.NOT_FOUND, {
                "status": "unknown_route",
                "error": {
                    "type": "not_found_error",
                    "code": "unknown_route",
                    "message": f"No deployment is routed at '{path}'",
                    "param": None,
                },
            }

        request = urllib.request.Request(route.target(path), data=body, method=method)
        for header in FORWARDED_HEADERS:
            value = headers.get(header)
            if value:
                request.add_header(header, value)

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status, _decode(response.read())
        except urllib.error.HTTPError as error:
            return error.code, _decode(error.read())
        except urllib.error.URLError as error:
            return HTTPStatus.BAD_GATEWAY, {
                "status": "upstream_unreachable",
                "error": {
                    "type": "upstream_error",
                    "code": "upstream_unreachable",
                    "message": f"Deployment '{route.spec.model_id}' is unreachable: {error.reason}",
                    "param": None,
                },
            }


def _decode(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"body": raw.decode("utf-8", errors="replace")}


def _make_handler(gateway: Gateway):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "TigerModelGateway/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _respond(self, code: int, body: Dict[str, Any]) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _headers(self) -> Dict[str, str]:
            return {header: self.headers.get(header, "") for header in FORWARDED_HEADERS}

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._respond(HTTPStatus.OK, {"status": "ok", "routes": len(gateway.routes)})
                return
            if self.path == "/routes":
                self._respond(HTTPStatus.OK, gateway.describe())
                return
            self._respond(*gateway.forward("GET", self.path, self._headers(), None))

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._respond(HTTPStatus.BAD_REQUEST, {"status": "invalid_length"})
                return
            if length > MAX_REQUEST_BYTES:
                self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "payload_too_large"})
                return
            body = self.rfile.read(length) if length else b""
            self._respond(*gateway.forward("POST", self.path, self._headers(), body))

    return Handler


class GatewayHTTPServer:
    """Serves the gateway over HTTP."""

    def __init__(self, gateway: Gateway, host: str = "0.0.0.0", port: int = 8080):
        self.gateway = gateway
        self._server = ThreadingHTTPServer((host, port), _make_handler(gateway))
        self._server.daemon_threads = True

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()

    def close(self) -> None:
        self._server.server_close()

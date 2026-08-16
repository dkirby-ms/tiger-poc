"""Entry point that runs exactly one model service, or the gateway in front of them."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from dataclasses import replace
from typing import Optional, Sequence

from .gateway import DEFAULT_UPSTREAM_TEMPLATE, Gateway, GatewayHTTPServer
from .http_service import ModelServiceHTTPServer
from .model_service import DEFAULT_CATALOG_PATH, load_default_specs, load_spec


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="local_model_runtime", description=__doc__)
    parser.add_argument(
        "--gateway",
        action="store_true",
        default=os.environ.get("MODEL_GATEWAY", "").lower() in {"1", "true", "yes"},
        help="Run the gateway instead of a single model service",
    )
    parser.add_argument(
        "--model-id",
        default=os.environ.get("MODEL_ID"),
        help="Catalog entry this service instance hosts",
    )
    parser.add_argument(
        "--catalog",
        default=os.environ.get("MODEL_SERVICE_CATALOG", str(DEFAULT_CATALOG_PATH)),
        help="Path to the service catalog",
    )
    parser.add_argument("--host", default=os.environ.get("MODEL_SERVICE_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MODEL_SERVICE_PORT", "0")) or None,
        help="Override the catalog port",
    )
    parser.add_argument(
        "--upstream-template",
        default=os.environ.get("MODEL_UPSTREAM_TEMPLATE", DEFAULT_UPSTREAM_TEMPLATE),
        help="Gateway upstream URL template using {model_id} and {port}",
    )
    return parser.parse_args(argv)


def _serve(server, banner: str) -> int:
    # serve_forever blocks this thread, so shutdown has to run on another one.
    def request_shutdown(*_: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    for received in (signal.SIGTERM, signal.SIGINT):
        signal.signal(received, request_shutdown)

    print(banner, flush=True)
    try:
        server.serve_forever()
    finally:
        server.close()
    return 0


def _run_gateway(args: argparse.Namespace) -> int:
    specs = load_default_specs(args.catalog)
    if not specs:
        print(f"No deployments found in catalog {args.catalog}", file=sys.stderr)
        return 2

    server = GatewayHTTPServer(
        Gateway(specs, upstream_template=args.upstream_template),
        host=args.host,
        port=args.port or int(os.environ.get("MODEL_GATEWAY_PORT", "8080")),
    )
    for route in server.gateway.routes:
        print(f"{route.prefix}/* -> {route.upstream}{route.rewrite_path}", flush=True)
    return _serve(server, f"gateway listening on {args.host}:{server.port}")


def _run_model_service(args: argparse.Namespace) -> int:
    if not args.model_id:
        print("--model-id or MODEL_ID is required", file=sys.stderr)
        return 2

    try:
        spec = load_spec(args.model_id, args.catalog)
    except KeyError as error:
        print(str(error), file=sys.stderr)
        return 2

    secret = os.environ.get("MODEL_SERVICE_SECRET")
    if secret:
        spec = replace(spec, secret=secret)

    server = ModelServiceHTTPServer(spec, host=args.host, port=args.port)
    return _serve(
        server,
        f"{spec.model_id} ({spec.workload_type.value}) serving {spec.route} on "
        f"{args.host}:{server.port}",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    return _run_gateway(args) if args.gateway else _run_model_service(args)


if __name__ == "__main__":
    raise SystemExit(main())

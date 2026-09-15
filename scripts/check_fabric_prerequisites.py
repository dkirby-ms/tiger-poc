#!/usr/bin/env python3
"""Validate non-secret prerequisites before live Fabric configuration.

Usage:
    uv run python scripts/check_fabric_prerequisites.py
    uv run python scripts/check_fabric_prerequisites.py --probe-tls
"""

from __future__ import annotations

import argparse
import os
import socket
import ssl
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

EXIT_SUCCESS = 0
EXIT_CONFIGURATION = 2
EXIT_BLOCKED = 3
EXIT_CONNECTIVITY = 4

REQUIRED_TEXT_SETTINGS = (
    "FABRIC_WORKSPACE_ID",
    "FABRIC_REGION",
    "FABRIC_CAPACITY_OR_TRIAL",
    "FABRIC_AUTH_MODE",
    "FABRIC_EVENTSTREAM_HOSTNAME",
    "FABRIC_PRIVATE_NETWORK_POLICY",
)
REQUIRED_TRUE_SETTINGS = (
    "FABRIC_CONTRIBUTOR_ACCESS",
    "FABRIC_DIGITAL_TWIN_BUILDER_ENABLED",
    "FABRIC_SPARK_AUTOSCALE_BILLING_COMPATIBLE",
    "FABRIC_TLS_VERIFY",
    "FABRIC_PREVIEW_APPROVED",
)


class CheckStatus(StrEnum):
    """Represent a prerequisite check outcome without exposing its value."""

    PASS = "PASS"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    MISSING = "MISSING"


@dataclass(frozen=True)
class CheckResult:
    """Describe one non-secret prerequisite check."""

    setting: str
    status: CheckStatus
    guidance: str


def evaluate_environment(environ: Mapping[str, str]) -> tuple[CheckResult, ...]:
    """Evaluate required non-secret Fabric settings without returning their values."""
    results: list[CheckResult] = []
    for setting in REQUIRED_TEXT_SETTINGS:
        if not environ.get(setting, "").strip():
            results.append(CheckResult(setting, CheckStatus.MISSING, "set the required value"))
        else:
            results.append(CheckResult(setting, CheckStatus.PASS, "configured"))

    for setting in REQUIRED_TRUE_SETTINGS:
        raw_value = environ.get(setting, "").strip().lower()
        if not raw_value:
            results.append(CheckResult(setting, CheckStatus.MISSING, "record true or false"))
        elif raw_value not in {"true", "false"}:
            results.append(CheckResult(setting, CheckStatus.INVALID, "use true or false"))
        elif raw_value == "false":
            results.append(CheckResult(setting, CheckStatus.BLOCKED, "live Fabric work is blocked"))
        else:
            results.append(CheckResult(setting, CheckStatus.PASS, "confirmed"))

    auth_mode = environ.get("FABRIC_AUTH_MODE", "").strip().lower()
    if auth_mode and auth_mode not in {"entra", "sas"}:
        results.append(
            CheckResult("FABRIC_AUTH_MODE_FORMAT", CheckStatus.INVALID, "use entra or sas")
        )

    network_policy = environ.get("FABRIC_PRIVATE_NETWORK_POLICY", "").strip().lower()
    if network_policy and network_policy not in {"private", "approved-public"}:
        results.append(
            CheckResult(
                "FABRIC_PRIVATE_NETWORK_POLICY_FORMAT",
                CheckStatus.INVALID,
                "use private or approved-public",
            )
        )

    hostname = environ.get("FABRIC_EVENTSTREAM_HOSTNAME", "").strip()
    if hostname and not _is_hostname_only(hostname):
        results.append(
            CheckResult(
                "FABRIC_EVENTSTREAM_HOSTNAME_FORMAT",
                CheckStatus.INVALID,
                "provide a hostname without scheme, path, query, user information, or port",
            )
        )
    return tuple(results)


def create_parser() -> argparse.ArgumentParser:
    """Create the prerequisite-check command-line parser."""
    parser = argparse.ArgumentParser(
        description="Check non-secret Fabric prerequisites before live configuration."
    )
    parser.add_argument(
        "--probe-tls",
        action="store_true",
        help="Open a certificate-verifying TLS connection to the configured hostname.",
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="TLS probe timeout in seconds.")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run prerequisite checks and return an actionable process exit code."""
    args = create_parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    results = evaluate_environment(environment)
    for result in results:
        print(f"{result.status}: {result.setting} ({result.guidance})")

    if any(result.status in {CheckStatus.MISSING, CheckStatus.INVALID} for result in results):
        print("RESULT: configuration incomplete; live Fabric work must not start")
        return EXIT_CONFIGURATION
    if any(result.status is CheckStatus.BLOCKED for result in results):
        print("RESULT: prerequisite denied; live Fabric work must not start")
        return EXIT_BLOCKED
    if args.probe_tls:
        try:
            _probe_tls(environment["FABRIC_EVENTSTREAM_HOSTNAME"], args.timeout)
        except (OSError, ssl.SSLError) as error:
            print(f"BLOCKED: TLS_PROBE ({type(error).__name__})")
            return EXIT_CONNECTIVITY
        print("PASS: TLS_PROBE (certificate verified)")
    print("RESULT: non-secret prerequisites passed")
    return EXIT_SUCCESS


def _is_hostname_only(value: str) -> bool:
    parsed = urlsplit(f"//{value}")
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.hostname
        and parsed.hostname == value
        and parsed.username is None
        and parsed.password is None
        and port is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _probe_tls(hostname: str, timeout: float) -> None:
    context = ssl.create_default_context()
    with socket.create_connection((hostname, 443), timeout=timeout) as connection:
        with context.wrap_socket(connection, server_hostname=hostname):
            return


def main() -> int:
    """Run the command with top-level interrupt and pipe handling."""
    try:
        return run()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        sys.stderr.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())

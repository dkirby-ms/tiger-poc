# /// script
# requires-python = ">=3.11"
# dependencies = ["azure-identity>=1.25,<2", "azure-storage-file-datalake>=12.22,<13", "httpx>=0.28,<1"]
# ///
"""Deploy the Tiger Fabric POC with a signed-in Azure CLI user.

Usage: uv run infra/fabric/deploy.py --help
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import re
import ssl
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity import AzureCliCredential
from azure.storage.filedatalake import DataLakeServiceClient

if __package__:
    from .artifacts import (
        INGESTION_TIME_POLICY,
        database_schema,
        load_config,
        reference_ingest,
        reference_tables,
        substitute,
        twin_definition,
    )
else:
    from artifacts import (
        INGESTION_TIME_POLICY,
        database_schema,
        load_config,
        reference_ingest,
        reference_tables,
        substitute,
        twin_definition,
    )

API = "https://api.fabric.microsoft.com/v1/"
ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = Path(__file__).parent / "definitions"
LOGGER = logging.getLogger(__name__)
ITEMS = {
    "eventhouse": ("Eventhouse", "eventhouses", "events"),
    "database": ("KQLDatabase", "kqlDatabases", "events_db"),
    "source": ("Lakehouse", "lakehouses", "reference"),
    "backing": ("Lakehouse", "lakehouses", "twin_data"),
    "eventstream": ("Eventstream", "eventstreams", "ingest"),
    "twin": ("DigitalTwinBuilder", "digitalTwinBuilders", "twin"),
    **{
        f"flow_{group}": (
            "DigitalTwinBuilderFlow",
            "digitalTwinBuilderFlows",
            f"{group}_flow",
        )
        for group in ("reference", "relationships", "timeseries")
    },
}


class DeploymentError(RuntimeError):
    """A deployment failed without deleting any resources."""


def encode_definition(parts: dict[str, Any]) -> dict:
    """Encode JSON objects or text as Fabric public definition parts."""
    return {
        "parts": [
            {
                "path": path,
                "payload": base64.b64encode(
                    (value if isinstance(value, str) else json.dumps(value)).encode()
                ).decode(),
                "payloadType": "InlineBase64",
            }
            for path, value in sorted(parts.items())
        ]
    }


class FabricClient:
    """Bounded Fabric REST requests with refreshed user credentials."""

    def __init__(
        self,
        http: httpx.Client,
        token: Callable[[str], str],
        *,
        timeout: float = 1800,
        pause: Callable[[float], None] = time.sleep,
        diagnostics_dir: Path | None = None,
    ) -> None:
        self.http = http
        self.token = token
        self.timeout = timeout
        self.pause = pause
        self.diagnostics_dir = diagnostics_dir

    def save_failure(self, response: httpx.Response, context: str) -> str:
        """Optionally retain the service error privately, never request credentials."""
        if self.diagnostics_dir is None:
            return " Use --diagnostics-dir to retain the service error locally."
        try:
            body = response.json()
        except ValueError:
            body = response.text
        try:
            self.diagnostics_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="fabric-failure-",
                suffix=".json",
                dir=self.diagnostics_dir,
                delete=False,
            ) as diagnostic:
                json.dump(
                    {
                        "context": context,
                        "statusCode": response.status_code,
                        "requestId": response.headers.get("request-id"),
                        "response": body,
                    },
                    diagnostic,
                    indent=2,
                )
                diagnostic.write("\n")
            return f" Private service diagnostic: {diagnostic.name}. Review before sharing."
        except OSError:
            return " Could not save the private service diagnostic; check directory access."

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Call Fabric, retrying throttling but never ambiguous server errors."""
        url = urljoin(API, path)
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.fabric.microsoft.com"
            or not parsed.path.startswith("/v1/")
        ):
            raise DeploymentError("Refusing an untrusted Fabric API URL.")
        deadline = time.monotonic() + self.timeout
        for attempt in range(8):
            response = self.http.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {self.token('https://api.fabric.microsoft.com/.default')}"
                },
                **kwargs,
            )
            if response.status_code != 429:
                break
            if attempt == 7:
                raise DeploymentError(
                    "Fabric throttling persisted after eight attempts."
                )
            self.delay(response, deadline)
        if not 200 <= response.status_code < 300:
            raise DeploymentError(
                f"Fabric {method} {parsed.path} returned HTTP {response.status_code}; "
                f"request ID: {response.headers.get('request-id', 'unavailable')}. "
                "Inspect the item and permissions before retrying."
                + self.save_failure(response, f"{method} {parsed.path}")
            )
        return response

    def delay(self, response: httpx.Response, deadline: float) -> None:
        """Honor Retry-After without exceeding the operation timeout."""
        try:
            seconds = max(1, int(response.headers.get("retry-after", "5")))
        except ValueError as error:
            raise DeploymentError(
                "Fabric returned an invalid Retry-After header."
            ) from error
        if time.monotonic() + seconds >= deadline:
            raise DeploymentError(
                "Operation timed out; it may still be running in Fabric."
            )
        self.pause(seconds)

    def finish(self, response: httpx.Response, *, result: bool = False) -> dict:
        """Wait for an LRO; fetch a result only for operations that produce one."""
        if response.status_code != 202:
            return response.json() if response.content else {}
        operation_url = response.headers.get("location")
        operation_id = response.headers.get("x-ms-operation-id")
        if operation_id:
            try:
                operation_url = f"operations/{UUID(operation_id)}"
            except ValueError as error:
                raise DeploymentError(
                    "Fabric returned an invalid operation ID."
                ) from error
        if not operation_url:
            raise DeploymentError("Async response did not include an operation URL.")
        deadline = time.monotonic() + self.timeout
        while True:
            self.delay(response, deadline)
            response = self.request("GET", operation_url)
            body = response.json()
            status = body.get("status")
            if status == "Succeeded":
                if result:
                    result_url = operation_url.rstrip("/") + "/result"
                    if not operation_id:
                        result_url = response.headers.get("location", result_url)
                    return self.request(
                        "GET",
                        result_url,
                    ).json()
                return body
            if status in {"Failed", "Cancelled", "Canceled"}:
                error = body.get("error")
                code = error.get("errorCode") if isinstance(error, dict) else None
                detail = (
                    f" Error code: {code}."
                    if isinstance(code, str)
                    and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", code)
                    else ""
                )
                raise DeploymentError(
                    f"Fabric operation {operation_url} ended with {status}.{detail}"
                    + self.save_failure(response, operation_url)
                )
            if status not in {"NotStarted", "Running"}:
                raise DeploymentError(f"Unexpected operation status: {status!r}.")

    def items(self, workspace: str) -> list[dict]:
        """List every item, following continuation links."""
        path = f"workspaces/{workspace}/items"
        items = []
        visited = set()
        while path:
            if path in visited:
                raise DeploymentError("Fabric returned a cyclic pagination link.")
            visited.add(path)
            body = self.request("GET", path).json()
            items.extend(body.get("value", []))
            path = body.get("continuationUri")
        return items


def fingerprint(config: dict) -> str:
    """Hash material deployment inputs, excluding runtime-only flow settings."""
    digest = hashlib.sha256()
    settings = {
        key: value
        for key, value in config.items()
        if key not in {"flowJobType", "artifactRoot"}
    }
    digest.update(json.dumps(settings, sort_keys=True).encode())
    for path in sorted(DEFINITIONS.iterdir()):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update(json.dumps(reference_tables(config), sort_keys=True).encode())
    digest.update(database_schema(config).encode())
    parts, groups = twin_definition(config, "<workspace>", "<source>", "<backing>")
    digest.update(json.dumps([parts, groups], sort_keys=True).encode())
    return digest.hexdigest()


class Deployment:
    """Create or resume owned resources; never adopt or delete existing items."""

    def __init__(
        self, client: FabricClient, config: dict, workspace: str, state_path: Path
    ) -> None:
        self.client = client
        self.config = config
        self.workspace = str(UUID(workspace))
        self.state_path = state_path
        expected = {
            "version": 1,
            "workspaceId": self.workspace,
            "fingerprint": fingerprint(config),
        }
        self.state = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else {**expected, "items": {}, "completed": []}
        )
        if any(self.state.get(key) != value for key, value in expected.items()):
            raise DeploymentError(
                "State does not match the workspace or artifacts. Use a fresh deployment after manual cleanup; do not reuse this state."
            )

    def save(self) -> None:
        """Atomically persist item IDs and completion checkpoints, without secrets."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def preflight(self) -> None:
        """Check workspace capacity and every owned/name-colliding item before writes."""
        workspace = self.client.request("GET", f"workspaces/{self.workspace}").json()
        if not workspace.get("capacityId"):
            raise DeploymentError("The workspace must be assigned to Fabric capacity.")
        inventory = self.client.items(self.workspace)
        by_id = {item["id"]: item for item in inventory}
        for key, (kind, _, suffix) in ITEMS.items():
            name = f"{self.config['prefix']}_{suffix}"
            owned = self.state["items"].get(key)
            if owned:
                actual = by_id.get(owned)
                if (
                    not actual
                    or actual["type"] != kind
                    or actual["displayName"] != name
                ):
                    raise DeploymentError(
                        f"Owned item {name} is missing or changed; refusing partial recreation."
                    )
            for item in inventory:
                if (
                    item["type"] == kind
                    and item["displayName"].casefold() == name.casefold()
                    and item["id"] != owned
                ):
                    raise DeploymentError(
                        f"Name collision: {name}. Remove the old item manually or use another prefix."
                    )

    def create(self, key: str, parts: dict | None = None) -> str:
        """Create one item, or return an ID already recorded by this deployment."""
        if key in self.state["items"]:
            return self.state["items"][key]
        kind, endpoint, suffix = ITEMS[key]
        name = f"{self.config['prefix']}_{suffix}"
        LOGGER.info("Creating %s (%s)", name, kind)
        payload = {
            "displayName": name,
            "description": "Tiger POC code-managed deployment",
        }
        if parts is not None:
            payload["definition"] = encode_definition(parts)
        try:
            response = self.client.request(
                "POST", f"workspaces/{self.workspace}/{endpoint}", json=payload
            )
            item = self.client.finish(response, result=True)
        except DeploymentError as error:
            raise DeploymentError(f"Create {name} ({kind}) failed. {error}") from error
        if not item.get("id"):
            raise DeploymentError(
                f"Create {name} completed without an item ID; inspect the workspace before retrying."
            )
        self.state["items"][key] = str(UUID(item["id"]))
        self.save()
        return self.state["items"][key]

    def once(self, name: str, action: Callable[[], None]) -> None:
        """Checkpoint only successful, repeatable provisioning actions."""
        if name not in self.state["completed"]:
            LOGGER.info("Configuring %s", name)
            action()
            self.state["completed"].append(name)
            self.save()

    def kql(self, command: str, *, query: bool = False) -> dict:
        """Run KQL against the trusted endpoint returned by Fabric."""
        database = self.client.request(
            "GET",
            f"workspaces/{self.workspace}/kqlDatabases/{self.state['items']['database']}",
        ).json()
        endpoint = database["properties"]["queryServiceUri"].rstrip("/")
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.netloc.endswith(".kusto.fabric.microsoft.com")
            or parsed.path
        ):
            raise DeploymentError("Fabric returned an unexpected KQL query endpoint.")
        try:
            response = self.client.http.post(
                endpoint + ("/v1/rest/query" if query else "/v1/rest/mgmt"),
                headers={
                    "Authorization": f"Bearer {self.client.token(endpoint + '/.default')}"
                },
                json={"db": self.state["items"]["database"], "csl": command},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise DeploymentError(
                f"Could not establish a secure connection to KQL endpoint {parsed.hostname}:443. "
                "Check DNS, network/VPN, proxy, and TLS connectivity from this environment. "
                "Keep the checkpoint and retry after connectivity is restored; do not disable TLS verification."
            ) from error
        if not response.is_success:
            raise DeploymentError(
                f"KQL command returned HTTP {response.status_code}; inspect database permissions and schema."
            )
        body = response.json()
        if body.get("error") or body.get("Exceptions") or body.get("OneApiErrors"):
            raise DeploymentError("KQL reported a command error; deployment stopped.")
        return body

    def seed(self, upload: Callable[[str, str, str], None]) -> None:
        """Upload and load reference CSV tables, using overwrite for safe retries."""
        lakehouse = self.state["items"]["source"]
        for table, content in reference_tables(self.config).items():

            def load(table: str = table, content: str = content) -> None:
                self.kql(reference_ingest(self.config, table, content))
                upload(lakehouse, f"Files/{table}.csv", content)
                response = self.client.request(
                    "POST",
                    f"workspaces/{self.workspace}/lakehouses/{lakehouse}/tables/{table}/load",
                    json={
                        "relativePath": f"Files/{table}.csv",
                        "pathType": "File",
                        "mode": "Overwrite",
                        "recursive": False,
                        "formatOptions": {
                            "format": "Csv",
                            "header": True,
                            "delimiter": ",",
                        },
                    },
                )
                self.client.finish(response)

            self.once(f"reference_{table}", load)

    def apply(self, upload: Callable[[str, str, str], None]) -> None:
        """Deploy all definitions and reference data, but do not start recurring jobs."""
        self.preflight()
        eventhouse = self.create("eventhouse")
        database = self.create(
            "database",
            {
                "DatabaseProperties.json": {
                    "databaseType": "ReadWrite",
                    "parentEventhouseItemId": eventhouse,
                },
                "DatabaseSchema.kql": database_schema(self.config),
            },
        )
        self.once("ingestion_time", lambda: self.kql(INGESTION_TIME_POLICY))
        self.once(
            "mirroring",
            lambda: self.kql(
                ".alter-merge table ConfirmedPresenceEvents policy mirroring dataformat=parquet "
                f"with (IsEnabled=true, Backfill=true, TargetLatencyInMinutes={self.config['targetLatencyMinutes']})"
            ),
        )
        self.once(
            "mirroring_qr",
            lambda: self.kql(
                ".alter-merge table BoxIdentificationEvents policy mirroring dataformat=parquet "
                f"with (IsEnabled=true, Backfill=true, TargetLatencyInMinutes={self.config['targetLatencyMinutes']})"
            ),
        )
        source = self.create("source")
        backing = self.create("backing")
        self.seed(upload)
        self.once(
            "shortcut",
            lambda: self.client.request(
                "POST",
                f"workspaces/{self.workspace}/items/{source}/shortcuts?shortcutConflictPolicy=CreateOrOverwrite",
                json={
                    "path": "Tables",
                    "name": "ConfirmedPresenceEvents",
                    "target": {
                        "oneLake": {
                            "workspaceId": self.workspace,
                            "itemId": database,
                            "path": "Tables/ConfirmedPresenceEvents",
                        }
                    },
                },
            ),
        )
        self.once(
            "shortcut_qr",
            lambda: self.client.request(
                "POST",
                f"workspaces/{self.workspace}/items/{source}/shortcuts?shortcutConflictPolicy=CreateOrOverwrite",
                json={
                    "path": "Tables",
                    "name": "BoxIdentificationEvents",
                    "target": {
                        "oneLake": {
                            "workspaceId": self.workspace,
                            "itemId": database,
                            "path": "Tables/BoxIdentificationEvents",
                        }
                    },
                },
            ),
        )
        topology = substitute(
            json.loads((DEFINITIONS / "eventstream.json").read_text()),
            {
                "workspaceId": self.workspace,
                "databaseId": database,
                "databaseName": f"{self.config['prefix']}_{ITEMS['database'][2]}",
            },
        )
        self.create("eventstream", {"eventstream.json": topology})
        parts, groups = twin_definition(self.config, self.workspace, source, backing)
        twin = self.create("twin", parts)
        for group, operations in groups.items():
            self.create(
                f"flow_{group}",
                {
                    "definition.json": {
                        "DigitalTwinBuilderId": twin,
                        "OperationIds": operations,
                        "IsOnDemand": False,
                    }
                },
            )
        LOGGER.info(
            "Definitions and reference tables deployed. Twin mapping jobs have NOT run. State: %s",
            self.state_path,
        )

    def run_flow(self, group: str, job_type: str) -> None:
        """Start a confirmed flow job type, or resume polling a recorded active job."""
        jobs = self.state.setdefault("jobs", {})
        previous = jobs.get(group, {})
        if previous.get("status") in {"NotStarted", "InProgress"}:
            location = previous["location"]
            response = httpx.Response(202, headers={"Retry-After": "1"})
        else:
            item = self.state["items"][f"flow_{group}"]
            response = self.client.request(
                "POST",
                f"workspaces/{self.workspace}/items/{item}/jobs/{job_type}/instances",
            )
            location = response.headers.get("location")
            if response.status_code != 202 or not location:
                raise DeploymentError(
                    "Job submission did not return an asynchronous job location."
                )
            jobs[group] = {
                "location": location,
                "status": "NotStarted",
                "jobType": job_type,
            }
            self.save()
        deadline = time.monotonic() + self.client.timeout
        while True:
            self.client.delay(response, deadline)
            response = self.client.request("GET", location)
            status = response.json().get("status")
            jobs[group]["status"] = status
            self.save()
            if status == "Completed":
                LOGGER.info("Flow %s completed", group)
                return
            if status not in {"NotStarted", "InProgress"}:
                raise DeploymentError(
                    f"Flow {group} ended with {status}; inspect job {location}."
                )

    def run(self, phase: str, job_type: str) -> None:
        """Run static initialization before mapping presence time series."""
        self.preflight()
        if any(key not in self.state["items"] for key in ITEMS):
            raise DeploymentError("Finish apply before running flows.")
        if self.state.get("schedules"):
            raise DeploymentError(
                "Schedules are recorded; do not overlap manual and scheduled flow runs."
            )
        if phase in {"reference", "all"}:
            self.run_flow("reference", job_type)
            self.run_flow("relationships", job_type)
            self.state["referenceInitialized"] = True
            self.save()
        if phase in {"events", "all"}:
            if not self.state.get("referenceInitialized"):
                raise DeploymentError("Run the reference phase before mapping events.")
            for group in ("timeseries",):
                self.run_flow(group, job_type)

    def schedule(self, job_type: str, until: str, interval: int) -> None:
        """Create explicitly requested, bounded recurring event-flow schedules."""
        end = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if end.tzinfo is None or end <= now or not 15 <= interval <= 720:
            raise ValueError(
                "Use a future timezone-aware --until and --interval between 15 and 720 minutes"
            )
        if not all(
            self.state.get("jobs", {}).get(group, {}).get("status") == "Completed"
            for group in ("reference", "relationships", "timeseries")
        ):
            raise DeploymentError(
                "Complete reference and event flow runs before enabling schedules."
            )
        self.preflight()
        schedules = self.state.setdefault("schedules", {})
        for group in ("timeseries",):
            if group in schedules:
                continue
            item = self.state["items"][f"flow_{group}"]
            body = {
                "enabled": True,
                "configuration": {
                    "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
                    "endDateTime": end.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ),
                    "localTimeZoneId": "UTC",
                    "type": "Cron",
                    "interval": interval,
                },
            }
            response = self.client.request(
                "POST",
                f"workspaces/{self.workspace}/items/{item}/jobs/{job_type}/schedules",
                json=body,
            ).json()
            schedules[group] = {"id": response["id"], "jobType": job_type, **body}
            self.save()


def create_http_client(*, tls12: bool = False) -> httpx.Client:
    """Create a verified HTTP client with optional TLS 1.2 compatibility."""
    verification: ssl.SSLContext | bool = True
    if tls12:
        verification = ssl.create_default_context()
        verification.minimum_version = ssl.TLSVersion.TLSv1_2
        verification.maximum_version = ssl.TLSVersion.TLSv1_2
    return httpx.Client(verify=verification, timeout=60, follow_redirects=False)


def create_parser() -> argparse.ArgumentParser:
    """Build the deployment CLI without authenticating."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["plan", "apply", "status", "run", "schedule"]
    )
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).with_name("config.json")
    )
    parser.add_argument(
        "--workspace", help="Existing Fabric workspace GUID (required except for plan)"
    )
    parser.add_argument(
        "--tenant", help="Tenant GUID used by your Azure CLI user login"
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Local checkpoint (default: data/fabric/<workspace>.json)",
    )
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Maximum seconds per async operation"
    )
    parser.add_argument(
        "--tls12",
        action="store_true",
        help="Use verified TLS 1.2 for Fabric/KQL HTTP calls (network compatibility)",
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        help="Save Fabric failure responses in private files; may contain sensitive service details",
    )
    parser.add_argument(
        "--job-type",
        help="Confirmed DigitalTwinBuilderFlow job type (no assumed preview default)",
    )
    parser.add_argument(
        "--phase", choices=["reference", "events", "all"], default="reference"
    )
    parser.add_argument(
        "--until", help="Required schedule expiration, e.g. 2026-10-01T00:00:00Z"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Minutes between scheduled event mapping runs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run offline planning or an explicitly requested cloud operation."""
    args = create_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        config = load_config(args.config)
        tables = reference_tables(config)
        job_type = args.job_type or config.get("flowJobType")
        if args.command in {"run", "schedule"} and (
            not job_type or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", job_type)
        ):
            raise ValueError(
                "A confirmed --job-type is required; DigitalTwinBuilderFlow's preview execution contract is not documented"
            )
        if args.command == "schedule" and not args.until:
            raise ValueError("--until is required to bound the schedule lifetime")
        if args.command == "plan":
            twin_definition(
                config, "<workspace>", "<source-lakehouse>", "<twin-lakehouse>"
            )
            print(
                json.dumps(
                    {
                        "mode": "offline; no cloud calls",
                        "fingerprint": fingerprint(config),
                        "items": [
                            {
                                "key": key,
                                "type": spec[0],
                                "name": f"{config['prefix']}_{spec[2]}",
                            }
                            for key, spec in ITEMS.items()
                        ],
                        "referenceTables": list(tables),
                        "flowExecution": "requires a confirmed flow job type; apply does not start jobs",
                    },
                    indent=2,
                )
            )
            return 0
        if not args.workspace or args.timeout < 1:
            raise ValueError("--workspace and a positive --timeout are required")
        workspace = str(UUID(args.workspace))
        state = args.state or ROOT / "data/fabric" / f"{workspace}.json"
        if args.command != "apply" and not state.exists():
            raise ValueError("No deployment state exists for this workspace")
        account = json.loads(
            subprocess.run(
                ["az", "account", "show", "--output", "json"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        if account.get("user", {}).get("type") != "user":
            raise ValueError(
                "Sign in with an interactive user using az login; app-only credentials are not supported"
            )
        tenant = str(UUID(args.tenant or account["tenantId"]))
        with (
            AzureCliCredential(tenant_id=tenant) as credential,
            create_http_client(tls12=args.tls12) as http,
        ):
            client = FabricClient(
                http,
                lambda scope: credential.get_token(scope).token,
                timeout=args.timeout,
                diagnostics_dir=args.diagnostics_dir,
            )
            deployment = Deployment(client, config, workspace, state)
            if args.command == "run":
                deployment.run(args.phase, job_type)
                return 0
            if args.command == "schedule":
                deployment.schedule(job_type, args.until, args.interval)
                return 0
            if args.command == "status":
                deployment.preflight()
                print(json.dumps(deployment.state, indent=2))
                if "database" in deployment.state["items"]:
                    print(
                        json.dumps(
                            deployment.kql(
                                "ProcessEventsRaw | summarize EventCount=count(), LastCapturedAt=max(capturedAt)",
                                query=True,
                            ),
                            indent=2,
                        )
                    )
                return 0
            with DataLakeServiceClient(
                "https://onelake.dfs.fabric.microsoft.com", credential=credential
            ) as storage:
                filesystem = storage.get_file_system_client(workspace)

                def upload(lakehouse: str, path: str, content: str) -> None:
                    filesystem.get_file_client(f"{lakehouse}/{path}").upload_data(
                        content.encode(), overwrite=True
                    )

                deployment.apply(upload)
        return 0
    except (ValueError, KeyError, OSError) as error:
        LOGGER.error("Configuration error: %s", error)
        return 2
    except KeyboardInterrupt:
        LOGGER.error(
            "Interrupted. In-flight Fabric operations may continue; keep the checkpoint."
        )
        return 130
    except (
        DeploymentError,
        httpx.HTTPError,
        AzureError,
        subprocess.SubprocessError,
    ) as error:
        LOGGER.error(
            "Deployment stopped (%s). Completed items were retained. Check login, permissions, and Fabric operation status.",
            type(error).__name__,
        )
        if isinstance(error, DeploymentError):
            LOGGER.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())

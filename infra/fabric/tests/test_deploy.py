"""Offline checks for the Fabric deployment artifacts and orchestration."""

import csv
import io
import json
import re
import ssl
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest

from infra.fabric.artifacts import (
    database_schema,
    load_config,
    reference_ingest,
    reference_tables,
    twin_definition,
)
from infra.fabric.deploy import (
    Deployment,
    DeploymentError,
    FabricClient,
    create_http_client,
    create_parser,
    encode_definition,
    main,
)

ROOT = Path(__file__).resolve().parents[3]
DEFINITIONS = ROOT / "infra/fabric/definitions"


def test_given_canonical_kql_when_compiled_then_schema_and_presence_policy_are_preserved() -> (
    None
):
    config = load_config(ROOT / "infra/fabric/config.json")

    schema = database_schema(config)

    assert "value: dynamic" in schema
    assert 'gettype(value) == "bool"' in schema
    assert '"IsTransactional":true' in schema
    assert ".create-or-alter materialized-view CurrentPositionOccupancy" in schema
    assert ".ingest inline" not in schema
    assert ".show tables" not in schema


def test_given_schema_when_submitted_then_only_fabric_supported_commands_are_used() -> (
    None
):
    config = load_config(ROOT / "infra/fabric/config.json")

    schema = database_schema(config)
    command_lines = re.findall(r"^\..*$", schema, re.MULTILINE)

    assert len(command_lines) == 14
    assert ".create-or-alter materialized-view LastCaseIdentification" in schema
    assert 'gettype(value) == "string" and unit == "identifier"' in schema
    assert all(
        re.match(
            r"\.(create-merge table |create-or-alter function |"
            r"create-or-alter materialized-view |"
            r"alter table \w+ policy update|create table \w+ ingestion json mapping )",
            command,
        )
        for command in command_lines
    )
    assert "policy ingestiontime" not in schema


def test_given_reference_seed_when_compiled_then_data_is_replaced_not_appended() -> (
    None
):
    config = load_config(ROOT / "infra/fabric/config.json")

    command = reference_ingest(config, "Plants", reference_tables(config)["Plants"])

    assert command.startswith(".set-or-replace Plants <|")
    assert '"Seattle, WA"' in command
    assert "datetime(2026-09-15T00:00:00+00:00)" in command


def test_given_multiline_kql_when_compiled_then_blank_lines_preserve_commands(
    tmp_path,
) -> None:
    config = load_config(ROOT / "infra/fabric/config.json")
    source = Path(config["artifactRoot"]) / "kql"
    destination = tmp_path / "kql"
    destination.mkdir()
    for filename in ("01_create_tables.kql", "02_update_policy.kql"):
        content = (
            (source / filename)
            .read_text()
            .replace("    | where gettype(value)", "\n    | where gettype(value)")
        )
        (destination / filename).write_text(content)
    config["artifactRoot"] = str(tmp_path)

    schema = database_schema(config)

    assert '\n\n    | where gettype(value) == "bool"' in schema
    assert '"Properties": {"Path": "$.eventId"}' in schema
    assert "| summarize arg_max(capturedAt, *) by subjectId" in schema


def test_given_canonical_instances_when_reference_tables_rendered_then_metadata_matches() -> (
    None
):
    config = load_config(ROOT / "infra/fabric/config.json")
    instances = json.loads(
        (Path(config["artifactRoot"]) / "digital_twin/twin_instances.json").read_text()
    )

    tables = reference_tables(config)

    for table, collection in (
        ("Plants", "plants"),
        ("Cells", "cells"),
        ("MonitoredPositions", "monitoredPositions"),
        ("Cases", "cases"),
    ):
        rows = list(csv.DictReader(io.StringIO(tables[table])))
        columns = set(rows[0]) - {"createdTimestamp"}
        assert sorted(
            [{key: row[key] for key in sorted(columns)} for row in rows], key=str
        ) == sorted(
            [
                {key: instance[key] for key in sorted(columns)}
                for instance in instances[collection]
            ],
            key=str,
        )


def make_client(responses: list[httpx.Response]) -> FabricClient:
    """Create a transport that consumes deterministic responses without waiting."""
    return FabricClient(
        httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0))),
        lambda scope: "test-token",
        pause=lambda seconds: None,
    )


def test_given_json_definition_when_encoded_then_parts_round_trip() -> None:
    import base64

    parts = encode_definition({"definition.json": {"LakehouseId": "test"}})["parts"]

    assert json.loads(base64.b64decode(parts[0]["payload"])) == {"LakehouseId": "test"}


def test_given_async_create_when_completed_then_result_is_fetched() -> None:
    client = make_client(
        [
            httpx.Response(200, json={"status": "Running"}),
            httpx.Response(200, json={"status": "Succeeded"}),
            httpx.Response(200, json={"id": "created-item"}),
        ]
    )

    result = client.finish(
        httpx.Response(
            202,
            headers={"Location": "https://api.fabric.microsoft.com/v1/operations/one"},
        ),
        result=True,
    )

    assert result == {"id": "created-item"}


@pytest.mark.parametrize(
    "location",
    [
        "http://api.fabric.microsoft.com/v1/operations/redirected",
        "https://regional.example.net/v1/operations/redirected",
        "https://wabi-us-central-b-primary-redirect.analysis.windows.net/v1/operations/redirected",
    ],
)
def test_given_operation_id_when_location_untrusted_then_public_api_is_used(
    location: str,
) -> None:
    operation = "00000000-0000-4000-8000-000000000010"
    requests = []
    responses = [
        httpx.Response(
            200, headers={"Location": location}, json={"status": "Succeeded"}
        ),
        httpx.Response(200, json={"id": "created-item"}),
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return responses.pop(0)

    client = FabricClient(
        httpx.Client(transport=httpx.MockTransport(respond)),
        lambda scope: "test-token",
        pause=lambda seconds: None,
    )

    result = client.finish(
        httpx.Response(
            202, headers={"Location": location, "x-ms-operation-id": operation}
        ),
        result=True,
    )

    assert result == {"id": "created-item"}
    assert requests == [
        f"https://api.fabric.microsoft.com/v1/operations/{operation}",
        f"https://api.fabric.microsoft.com/v1/operations/{operation}/result",
    ]


@pytest.mark.parametrize(
    "operation_id", ["not-a-guid", "../workspaces", "https://example.com"]
)
def test_given_invalid_operation_id_when_polled_then_no_request_is_sent(
    operation_id: str,
) -> None:
    client = make_client([])

    with pytest.raises(DeploymentError, match="invalid operation ID"):
        client.finish(httpx.Response(202, headers={"x-ms-operation-id": operation_id}))


def test_given_untrusted_location_without_id_when_polled_then_request_is_rejected() -> (
    None
):
    client = make_client([])

    with pytest.raises(DeploymentError, match="untrusted"):
        client.finish(
            httpx.Response(202, headers={"Location": "https://example.com/operation"})
        )


def test_given_failed_operation_when_polled_then_deployment_stops() -> None:
    client = make_client([httpx.Response(200, json={"status": "Failed"})])

    with pytest.raises(DeploymentError, match="Failed"):
        client.finish(
            httpx.Response(
                202,
                headers={"x-ms-operation-id": "00000000-0000-4000-8000-000000000010"},
            )
        )


def test_given_service_error_when_operation_fails_then_code_is_reported_without_message() -> (
    None
):
    client = make_client(
        [
            httpx.Response(
                200,
                json={
                    "status": "Failed",
                    "error": {
                        "errorCode": "ScriptContainsUnsupportedCommand",
                        "message": "private payload",
                    },
                },
            )
        ]
    )

    with pytest.raises(
        DeploymentError, match="ScriptContainsUnsupportedCommand"
    ) as failure:
        client.finish(
            httpx.Response(
                202,
                headers={"x-ms-operation-id": "00000000-0000-4000-8000-000000000010"},
            )
        )

    assert "private payload" not in str(failure.value)


def test_given_failed_twin_import_when_created_then_item_context_is_reported(
    tmp_path: Path,
) -> None:
    client = make_client(
        [
            httpx.Response(
                202,
                headers={"x-ms-operation-id": "00000000-0000-4000-8000-000000000010"},
            ),
            httpx.Response(
                200,
                json={
                    "status": "Failed",
                    "error": {"errorCode": "ALMOperationImportFailed"},
                },
            ),
        ]
    )
    deployment = Deployment(
        client,
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )

    with pytest.raises(
        DeploymentError, match=r"Create tiger_twin \(DigitalTwinBuilder\) failed"
    ):
        deployment.create("twin", {"definition.json": {"LakehouseId": "backing"}})

    assert deployment.state["items"] == {}
    assert not deployment.state_path.exists()


@pytest.mark.parametrize("status_code", [200, 400])
def test_given_diagnostics_when_service_fails_then_details_are_private(
    tmp_path: Path, status_code: int, caplog
) -> None:
    body = {
        "status": "Failed",
        "error": {
            "errorCode": "ALMOperationImportFailed",
            "message": "private import details",
            "moreDetails": [{"errorCode": "InnerError", "message": "private detail"}],
        },
    }
    diagnostics = tmp_path / "diagnostics"
    client = FabricClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status_code, json=body)
            )
        ),
        lambda scope: "credential-not-for-diagnostics",
        pause=lambda seconds: None,
        diagnostics_dir=diagnostics,
    )

    with pytest.raises(DeploymentError) as failure:
        if status_code == 400:
            client.request("POST", "workspaces/test/digitalTwinBuilders", json={})
        else:
            client.finish(
                httpx.Response(
                    202,
                    headers={
                        "x-ms-operation-id": "00000000-0000-4000-8000-000000000010"
                    },
                )
            )

    files = list(diagnostics.glob("*.json"))
    assert len(files) == 1
    assert files[0].stat().st_mode & 0o777 == 0o600
    content = files[0].read_text()
    assert json.loads(content)["response"] == body
    assert "credential-not-for-diagnostics" not in content
    assert "private import details" not in str(failure.value) + caplog.text
    assert str(files[0]) in str(failure.value)


def test_given_unwritable_diagnostics_when_import_fails_then_original_error_survives(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("existing file")
    client = FabricClient(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "status": "Failed",
                        "error": {"errorCode": "ALMOperationImportFailed"},
                    },
                )
            )
        ),
        lambda scope: "token",
        pause=lambda seconds: None,
        diagnostics_dir=blocked,
    )

    with pytest.raises(DeploymentError, match="ALMOperationImportFailed") as failure:
        client.finish(
            httpx.Response(
                202,
                headers={"x-ms-operation-id": "00000000-0000-4000-8000-000000000010"},
            )
        )

    assert "Could not save" in str(failure.value)
    assert blocked.read_text() == "existing file"


@pytest.mark.parametrize(
    "url",
    ["https://example.com/token", "http://api.fabric.microsoft.com/v1/operations/one"],
)
def test_given_untrusted_url_when_requested_then_token_is_not_sent(url: str) -> None:
    client = make_client([])

    with pytest.raises(DeploymentError, match="untrusted"):
        client.request("GET", url)


def test_given_paginated_items_when_listed_then_all_pages_are_returned() -> None:
    client = make_client(
        [
            httpx.Response(
                200,
                json={
                    "value": [{"id": "one"}],
                    "continuationUri": "https://api.fabric.microsoft.com/v1/workspaces/test/items?page=2",
                },
            ),
            httpx.Response(200, json={"value": [{"id": "two"}]}),
        ]
    )

    assert client.items("test") == [{"id": "one"}, {"id": "two"}]


def test_given_throttling_when_retried_then_request_can_complete() -> None:
    client = make_client(
        [
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={}),
        ]
    )

    assert client.request("GET", "workspaces").status_code == 200


def test_given_merged_reference_when_rendered_then_stable_ids_are_preserved() -> None:
    config = load_config(ROOT / "infra/fabric/config.json")

    tables = reference_tables(config)

    assert "cell-a-object-position-01" in tables["MonitoredPositions"]
    assert "cell-b-pallet-position-01" in tables["MonitoredPositions"]
    assert "demo-plant-01" in tables["Plants"]
    assert "cell-a,demo-plant-01" in tables["Cells"]


def test_given_model_when_rendered_then_links_and_flow_groups_are_consistent() -> None:
    config = load_config(ROOT / "infra/fabric/config.json")

    parts, groups = twin_definition(config, "workspace", "source", "backing")
    mappings = [
        part for path, part in parts.items() if path.startswith("MappingOperations/")
    ]
    timeseries = next(
        part
        for part in mappings
        if part["MappingOperationProperties"]["MappingType"] == "TimeSeries"
    )

    assert parts["definition.json"]["LakehouseId"] == "backing"
    assert len(groups["reference"]) == 4
    assert len(groups["timeseries"]) == 2
    assert len(groups["relationships"]) == 3
    assert parts["EntityTypes/10003.json"]["Name"] == "MonitoredPosition"
    case_mapping = next(
        part for part in mappings if part["DisplayName"] == "Case_timeseries"
    )
    assert (
        case_mapping["SourceTableProperties"]["SourceTableName"]
        == "BoxIdentificationEvents"
    )
    assert case_mapping["MappingOperationProperties"][
        "TimeseriesEntityLinkProperties"
    ] == {"EntityProperty": "caseId", "TimeseriesProperty": "subjectId"}
    assert [item["Value"] for item in case_mapping["Filters"]["FilterOperations"]] == [
        "BoxIdentified"
    ]
    assert all(part["SourceTableProperties"]["ItemId"] == "source" for part in mappings)
    assert timeseries["MappingOperationProperties"][
        "TimeseriesEntityLinkProperties"
    ] == {"EntityProperty": "positionId", "TimeseriesProperty": "subjectId"}
    assert (
        timeseries["SourceTableProperties"]["SourceTableName"]
        == "ConfirmedPresenceEvents"
    )
    assert {
        "SourceColumn": "capturedAt",
        "EntityTypePropertyName": "Timestamp",
    } in timeseries["MappingOperationProperties"]["MappedProperties"]
    assert parts == twin_definition(config, "workspace", "source", "backing")[0]


def test_given_timeseries_mapping_when_rendered_then_all_targets_are_declared() -> None:
    config = load_config(ROOT / "infra/fabric/config.json")
    parts, _ = twin_definition(config, "workspace", "source", "backing")
    mapping = next(
        part
        for path, part in parts.items()
        if path.startswith("MappingOperations/")
        and part["MappingOperationProperties"]["MappingType"] == "TimeSeries"
    )
    entity = parts[f"EntityTypes/{mapping['EntityTypeId']}.json"]
    properties = {
        prop["Name"]: prop["ValueType"] for prop in entity["TimeseriesProperties"]
    }
    targets = mapping["MappingOperationProperties"]["MappedProperties"]

    assert properties["Timestamp"] == "DateTime"
    assert all(target["EntityTypePropertyName"] in properties for target in targets)
    assert (
        targets.count(
            {"SourceColumn": "capturedAt", "EntityTypePropertyName": "Timestamp"}
        )
        == 1
    )


def test_given_plan_when_run_then_no_authentication_is_needed(capsys) -> None:
    result = main(["plan"])

    assert result == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "offline; no cloud calls"


def test_given_name_collision_when_preflight_runs_then_no_resource_is_created(
    tmp_path,
) -> None:
    client = make_client(
        [
            httpx.Response(200, json={"capacityId": "capacity"}),
            httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "foreign",
                            "type": "Eventhouse",
                            "displayName": "tiger_events",
                        }
                    ]
                },
            ),
        ]
    )
    deployment = Deployment(
        client,
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )

    with pytest.raises(DeploymentError, match="Name collision"):
        deployment.preflight()


def test_given_saved_workspace_when_different_workspace_selected_then_resume_rejected(
    tmp_path,
) -> None:
    config = load_config(ROOT / "infra/fabric/config.json")
    state = tmp_path / "state.json"
    Deployment(
        make_client([]), config, "00000000-0000-4000-8000-000000000001", state
    ).save()

    with pytest.raises(DeploymentError, match="State does not match"):
        Deployment(
            make_client([]), config, "00000000-0000-4000-8000-000000000002", state
        )


def test_given_empty_workspace_when_applied_twice_then_second_run_creates_nothing(
    tmp_path,
) -> None:
    requests = []
    items = []
    uploads = []
    workspace = "00000000-0000-4000-8000-000000000001"
    kinds = {
        "eventhouses": "Eventhouse",
        "kqlDatabases": "KQLDatabase",
        "lakehouses": "Lakehouse",
        "eventstreams": "Eventstream",
        "digitalTwinBuilders": "DigitalTwinBuilder",
        "digitalTwinBuilderFlows": "DigitalTwinBuilderFlow",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.endswith(f"workspaces/{workspace}"):
            return httpx.Response(200, json={"capacityId": "capacity"})
        if request.method == "GET" and path.endswith("/items"):
            return httpx.Response(200, json={"value": items})
        if request.method == "GET" and "/kqlDatabases/" in path:
            return httpx.Response(
                200,
                json={
                    "displayName": "tiger_events_db",
                    "properties": {
                        "queryServiceUri": "https://test.kusto.fabric.microsoft.com"
                    },
                },
            )
        if request.method == "POST" and path.endswith("/v1/rest/mgmt"):
            return httpx.Response(200, json={"Tables": []})
        if request.method == "POST" and path.endswith("/load"):
            return httpx.Response(
                202,
                headers={
                    "Location": "https://api.fabric.microsoft.com/v1/operations/load"
                },
            )
        if path == "/v1/operations/load":
            return httpx.Response(200, json={"status": "Succeeded"})
        if request.method == "POST" and path.endswith("/shortcuts"):
            return httpx.Response(201, json={})
        if request.method == "POST" and path.split("/")[-1] in kinds:
            payload = json.loads(request.content)
            item = {
                "id": str(uuid5(NAMESPACE_URL, payload["displayName"])),
                "type": kinds[path.split("/")[-1]],
                "displayName": payload["displayName"],
            }
            items.append(item)
            return httpx.Response(201, json=item)
        pytest.fail(f"Unexpected request: {request.method} {path}")

    client = FabricClient(
        httpx.Client(transport=httpx.MockTransport(respond)),
        lambda scope: "test",
        pause=lambda seconds: None,
    )
    config = load_config(ROOT / "infra/fabric/config.json")
    state = tmp_path / "state.json"
    deployment = Deployment(client, config, workspace, state)

    deployment.apply(lambda lakehouse, path, content: uploads.append((path, content)))
    first_requests = requests.copy()
    requests.clear()
    Deployment(client, config, workspace, state).apply(
        lambda *args: pytest.fail("Unexpected upload on resume")
    )

    assert len(items) == 10
    assert len(uploads) == 4
    assert "mirroring_qr" in deployment.state["completed"]
    assert "shortcut_qr" in deployment.state["completed"]
    shortcuts = [
        json.loads(request.content)
        for request in first_requests
        if request.url.path.endswith("/shortcuts")
    ]
    assert {shortcut["name"] for shortcut in shortcuts} == {
        "ConfirmedPresenceEvents",
        "BoxIdentificationEvents",
    }
    assert all(request.method == "GET" for request in requests)
    assert not any("/jobs/" in request.url.path for request in first_requests)
    policy_requests = [
        request
        for request in first_requests
        if request.url.path == "/v1/rest/mgmt"
        and json.loads(request.content)["csl"]
        == ".alter table ProcessEventsRaw policy ingestiontime true"
    ]
    assert len(policy_requests) == 1
    assert "ingestion_time" in deployment.state["completed"]
    eventstream_request = next(
        request
        for request in first_requests
        if request.url.path.endswith("/eventstreams")
    )
    assert first_requests.index(policy_requests[0]) < first_requests.index(
        eventstream_request
    )
    eventstream = next(
        json.loads(request.content)
        for request in first_requests
        if request.url.path.endswith("/eventstreams")
    )
    import base64

    flows = [
        json.loads(
            base64.b64decode(
                json.loads(request.content)["definition"]["parts"][0]["payload"]
            )
        )
        for request in first_requests
        if request.url.path.endswith("/digitalTwinBuilderFlows")
    ]
    assert len(flows) == 4
    assert [flow for flow in flows if flow["IsOnDemand"]] == [
        {
            "DigitalTwinBuilderId": deployment.state["items"]["twin"],
            "OperationIds": [],
            "IsOnDemand": True,
        }
    ]

    topology = json.loads(
        base64.b64decode(eventstream["definition"]["parts"][0]["payload"])
    )
    assert (
        topology["destinations"][0]["properties"]["itemId"]
        == deployment.state["items"]["database"]
    )
    assert topology["destinations"][0]["properties"]["tableName"] == "ProcessEventsRaw"


@pytest.mark.parametrize("query", [False, True])
def test_given_database_display_name_when_kql_sent_then_item_id_is_used(
    tmp_path, query
) -> None:
    database_id = "00000000-0000-4000-8000-000000000002"
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "displayName": "tiger_events_db",
                    "properties": {
                        "queryServiceUri": "https://test.kusto.fabric.microsoft.com"
                    },
                },
            )
        return httpx.Response(200, json={"Tables": []})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        deployment = Deployment(
            FabricClient(http, lambda scope: "test-token"),
            load_config(ROOT / "infra/fabric/config.json"),
            "00000000-0000-4000-8000-000000000001",
            tmp_path / "state.json",
        )
        deployment.state["items"]["database"] = database_id

        deployment.kql("print value=1" if query else ".show tables", query=query)

    assert requests[0].url.path.endswith(f"/kqlDatabases/{database_id}")
    assert requests[1].url.path == ("/v1/rest/query" if query else "/v1/rest/mgmt")
    assert json.loads(requests[1].content)["db"] == database_id


@pytest.mark.parametrize("tls12", [False, True])
def test_given_tls_option_when_client_created_then_certificate_checks_remain_enabled(
    monkeypatch, tls12
) -> None:
    options = {}
    sentinel = object()

    def capture_client(**kwargs):
        options.update(kwargs)
        return sentinel

    monkeypatch.setattr(httpx, "Client", capture_client)
    args = create_parser().parse_args(["status", *(["--tls12"] if tls12 else [])])

    assert create_http_client(tls12=args.tls12) is sentinel
    assert options["follow_redirects"] is False
    if tls12:
        context = options["verify"]
        assert isinstance(context, ssl.SSLContext)
        assert (
            context.minimum_version == context.maximum_version == ssl.TLSVersion.TLSv1_2
        )
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
    else:
        assert options["verify"] is True


@pytest.mark.parametrize("connection_error", [httpx.ConnectError, httpx.ConnectTimeout])
def test_given_kql_connection_failure_when_configuring_then_checkpoint_is_not_completed(
    tmp_path,
    connection_error,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "displayName": "tiger_events_db",
                    "properties": {
                        "queryServiceUri": "https://test.kusto.fabric.microsoft.com"
                    },
                },
            )
        raise connection_error("private transport details", request=request)

    client = FabricClient(
        httpx.Client(transport=httpx.MockTransport(respond)), lambda scope: "test-token"
    )
    deployment = Deployment(
        client,
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["database"] = "database"

    with pytest.raises(
        DeploymentError, match="test.kusto.fabric.microsoft.com:443"
    ) as failure:
        deployment.once(
            "ingestion_time",
            lambda: deployment.kql(
                ".alter table ProcessEventsRaw policy ingestiontime true"
            ),
        )

    assert deployment.state["completed"] == []
    assert "private transport details" not in str(failure.value)


def test_given_invalid_job_type_when_run_requested_then_fails_before_authentication() -> (
    None
):
    assert main(["run", "--job-type", "../invalid"]) == 2


def test_given_default_cli_when_parsed_then_all_mapping_stages_are_selected() -> None:
    args = create_parser().parse_args(["apply"])
    assert args.definitions_only is False
    assert args.phase == "all"
    assert main(["run", "--definitions-only"]) == 2


@pytest.mark.parametrize("definitions_only", [False, True])
def test_given_apply_cli_when_invoked_then_only_provisioning_runs(
    tmp_path, monkeypatch, definitions_only
) -> None:
    from contextlib import nullcontext
    from types import SimpleNamespace

    from infra.fabric import deploy

    calls = []
    filesystem = object()

    class FakeDeployment:
        def __init__(self, *args):
            pass

        def apply(self, upload):
            calls.append("apply")

        def export_dashboard(self):
            calls.append("dashboard")

        def configure_twin_projections(self):
            calls.append("twin_projections")

        def initialize(self, job_type, wait_for_sources):
            calls.append(job_type)
            wait_for_sources("timeseries")

        def wait_for_sources(self, actual_filesystem, group):
            assert actual_filesystem is filesystem
            calls.append(group)

    monkeypatch.setattr(deploy, "Deployment", FakeDeployment)
    monkeypatch.setattr(
        deploy.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=json.dumps(
                {
                    "user": {"type": "user"},
                    "tenantId": "00000000-0000-4000-8000-000000000002",
                }
            )
        ),
    )
    monkeypatch.setattr(
        deploy, "AzureCliCredential", lambda **kwargs: nullcontext(object())
    )
    monkeypatch.setattr(
        deploy, "create_http_client", lambda **kwargs: nullcontext(object())
    )
    monkeypatch.setattr(
        deploy,
        "DataLakeServiceClient",
        lambda *args, **kwargs: nullcontext(
            SimpleNamespace(get_file_system_client=lambda workspace: filesystem)
        ),
    )
    arguments = [
        "apply",
        "--workspace",
        "00000000-0000-4000-8000-000000000001",
        "--state",
        str(tmp_path / "state.json"),
    ]
    if definitions_only:
        arguments.append("--definitions-only")

    assert main(arguments) == 0
    assert calls == ["apply", "twin_projections", "dashboard"]


@pytest.mark.parametrize("suffix", ["001", "002"])
def test_given_deployment_when_dashboard_exported_then_bindings_are_configured(
    tmp_path, suffix
) -> None:
    config = load_config(ROOT / "infra/fabric/config.json")
    template = (
        Path(config["artifactRoot"]) / "dashboards/fabric_realtime_dashboard.json"
    )
    original = template.read_bytes()
    workspace = "00000000-0000-4000-8000-000000000" + suffix
    database_id = "00000000-0000-4000-8000-000000001" + suffix
    metadata = {
        "displayName": "example_db",
        "properties": {
            "queryServiceUri": "https://example.kusto.fabric.microsoft.com/"
        },
    }
    deployment = Deployment(
        make_client([httpx.Response(200, json=metadata)]),
        config,
        workspace,
        tmp_path / "custom.json",
    )
    deployment.state["items"]["database"] = database_id

    output = deployment.export_dashboard()

    rendered = json.loads(output.read_text())
    source = rendered["dataSources"][0]
    assert output == tmp_path / "custom.dashboard.json"
    assert source["workspace"] == workspace
    assert source["database"] == source["databaseArtifactId"] == database_id
    assert source["clusterUri"] == "https://example.kusto.fabric.microsoft.com"
    assert source["name"] == "example_db"
    assert source["kind"] == "kusto-trident"
    assert all(
        query["dataSource"]["dataSourceId"] == source["id"]
        for query in rendered["queries"]
    )
    assert template.read_bytes() == original
    expected = json.loads(original)
    expected["dataSources"] = rendered["dataSources"]
    assert rendered == expected


@pytest.mark.parametrize("broken_binding", [False, True])
def test_given_invalid_dashboard_inputs_when_exported_then_no_file_is_written(
    tmp_path, broken_binding
) -> None:
    config = load_config(ROOT / "infra/fabric/config.json")
    deployment = Deployment(
        make_client(
            [
                httpx.Response(
                    200,
                    json={
                        "displayName": "example_db",
                        "properties": {
                            "queryServiceUri": (
                                "https://example.kusto.fabric.microsoft.com"
                                if broken_binding
                                else "https://example.invalid"
                            )
                        },
                    },
                )
            ]
        ),
        config,
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["database"] = "database"
    if broken_binding:
        template = json.loads(
            (
                Path(config["artifactRoot"])
                / "dashboards/fabric_realtime_dashboard.json"
            ).read_text()
        )
        template["queries"][0]["dataSource"]["dataSourceId"] = "unbound"
        (tmp_path / "dashboards").mkdir()
        (tmp_path / "dashboards/fabric_realtime_dashboard.json").write_text(
            json.dumps(template)
        )
        config["artifactRoot"] = str(tmp_path)

    with pytest.raises(DeploymentError, match="template data source|unexpected KQL"):
        deployment.export_dashboard()

    assert not (tmp_path / "state.dashboard.json").exists()


def test_given_twin_sources_when_configured_twice_then_only_backing_tables_are_linked(
    tmp_path, monkeypatch
) -> None:
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(201, json={})

    deployment = Deployment(
        FabricClient(
            httpx.Client(transport=httpx.MockTransport(respond)), lambda scope: "test"
        ),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"] = {"database": "events", "backing": "twin-output"}
    registrations = []
    monkeypatch.setattr(deployment, "kql", registrations.append)

    deployment.configure_twin_sources()
    deployment.configure_twin_sources()

    assert len(requests) == 9
    assert all(
        body["target"]["oneLake"]["itemId"] == "twin-output" for body in requests
    )
    assert all(body["name"].startswith("Twin_") for body in requests)
    assert len(deployment.state["completed"]) == 18
    assert len(registrations) == 9
    assert all(";impersonate" in command for command in registrations)


def test_given_partial_initialization_when_resumed_then_completed_stages_are_skipped(
    tmp_path, monkeypatch
) -> None:
    from infra.fabric.deploy import ITEMS

    deployment = Deployment(
        make_client([]),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"] = {key: key for key in ITEMS}
    monkeypatch.setattr(deployment, "preflight", lambda: None)
    calls = []

    def run_flow(group, job_type):
        calls.append((group, job_type))
        if group == "relationships" and len(calls) == 2:
            raise DeploymentError("temporary failure")
        deployment.state.setdefault("jobs", {})[group] = {"status": "Completed"}
        deployment.save()

    monkeypatch.setattr(deployment, "run_flow", run_flow)
    readiness_checks = []
    with pytest.raises(DeploymentError, match="temporary failure"):
        deployment.initialize("ExecuteOperations", readiness_checks.append)
    assert "referenceInitialized" not in deployment.state
    deployment.initialize("ExecuteOperations", readiness_checks.append)
    assert [group for group, _ in calls] == [
        "reference",
        "relationships",
        "relationships",
        "timeseries",
    ]
    assert all(job_type == "ExecuteOperations" for _, job_type in calls)
    assert deployment.state["referenceInitialized"] is True
    deployment.initialize("ExecuteOperations", readiness_checks.append)
    assert len(calls) == 4
    assert readiness_checks == [
        "reference",
        "relationships",
        "relationships",
        "timeseries",
    ]


def test_given_delayed_delta_logs_when_waiting_then_both_history_tables_are_checked(
    tmp_path,
) -> None:
    from types import SimpleNamespace

    from azure.core.exceptions import ResourceNotFoundError

    calls = []

    def get_paths(*, path, recursive):
        calls.append(path)
        assert recursive is False
        if len(calls) == 1:
            raise ResourceNotFoundError("not ready")
        return [
            SimpleNamespace(
                name=path + "/00000000000000000000.json", is_directory=False
            )
        ]

    deployment = Deployment(
        make_client([]),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["source"] = "source"
    deployment.wait_for_sources(SimpleNamespace(get_paths=get_paths), "timeseries")
    assert calls == [
        "source/Tables/BoxIdentificationEvents/_delta_log",
        "source/Tables/ConfirmedPresenceEvents/_delta_log",
        "source/Tables/BoxIdentificationEvents/_delta_log",
    ]


def test_given_missing_delta_logs_when_timeout_then_no_mapping_job_is_submitted(
    tmp_path,
) -> None:
    from types import SimpleNamespace

    client = make_client([])
    client.timeout = 1
    deployment = Deployment(
        client,
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["source"] = "source"
    with pytest.raises(DeploymentError, match="No mapping was submitted"):
        deployment.wait_for_sources(
            SimpleNamespace(get_paths=lambda **kwargs: []), "timeseries"
        )
    assert "jobs" not in deployment.state


def test_given_ambiguous_submission_when_resumed_then_no_duplicate_job_is_sent(
    tmp_path,
) -> None:
    deployment = Deployment(
        make_client([]),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["jobs"] = {
        "reference": {"status": "Submitting", "jobType": "ExecuteOperations"}
    }
    with pytest.raises(DeploymentError, match="unknown outcome"):
        deployment.run_flow("reference", "ExecuteOperations")


def test_given_ready_sources_when_initialized_then_rest_jobs_complete_in_order(
    tmp_path, monkeypatch
) -> None:
    from infra.fabric.deploy import ITEMS

    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202, headers={"Location": str(request.url) + "/one"})
        return httpx.Response(200, json={"status": "Completed"})

    deployment = Deployment(
        FabricClient(
            httpx.Client(transport=httpx.MockTransport(respond)),
            lambda scope: "test",
            pause=lambda seconds: None,
        ),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"] = {key: key for key in ITEMS}
    monkeypatch.setattr(deployment, "preflight", lambda: None)

    deployment.initialize("ExecuteOperations", lambda group: None)
    deployment.initialize(
        "ExecuteOperations", lambda group: pytest.fail("Unexpected readiness check")
    )

    assert [method for method, _ in requests] == ["POST", "GET"] * 3
    assert [
        path.split("/items/")[1] for method, path in requests if method == "POST"
    ] == [
        f"flow_{group}/jobs/ExecuteOperations/instances"
        for group in ("reference", "relationships", "timeseries")
    ]
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["referenceInitialized"] is True
    assert all(job["status"] == "Completed" for job in saved["jobs"].values())


def test_given_active_mapping_when_resumed_then_existing_job_is_polled(
    tmp_path,
) -> None:
    requests = []

    def respond(request):
        requests.append(request.method)
        return httpx.Response(200, json={"status": "Completed"})

    deployment = Deployment(
        FabricClient(
            httpx.Client(transport=httpx.MockTransport(respond)),
            lambda scope: "test",
            pause=lambda seconds: None,
        ),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["jobs"] = {
        "reference": {
            "status": "InProgress",
            "jobType": "ExecuteOperations",
            "location": "https://api.fabric.microsoft.com/v1/workspaces/test/items/flow/jobs/instances/one",
        }
    }

    deployment.run_flow("reference", "ExecuteOperations")

    assert requests == ["GET"]
    assert deployment.state["jobs"]["reference"]["status"] == "Completed"


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 405, 422, 500, 503])
def test_given_submission_error_when_recorded_then_only_rejections_are_retryable(
    tmp_path, status_code
) -> None:
    deployment = Deployment(
        make_client([httpx.Response(status_code, json={"errorCode": "TestFailure"})]),
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["flow_reference"] = "flow"

    with pytest.raises(DeploymentError, match=f"HTTP {status_code}"):
        deployment.run_flow("reference", "ExecuteOperations")

    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["jobs"]["reference"]["status"] == (
        "Rejected" if status_code < 500 else "Submitting"
    )


def test_given_job_type_rejection_when_reported_then_code_and_body_request_id_are_visible() -> (
    None
):
    request_id = "e33641dc-04ed-40aa-8678-39cf2da8f57b"
    client = make_client(
        [
            httpx.Response(
                400,
                json={
                    "errorCode": "InvalidJobType",
                    "requestId": request_id,
                    "message": "private service details",
                },
            )
        ]
    )

    with pytest.raises(DeploymentError, match="InvalidJobType") as failure:
        client.request(
            "POST", "workspaces/test/items/flow/jobs/ExecuteOperations/instances"
        )

    assert request_id in str(failure.value)
    assert "private service details" not in str(failure.value)
    assert "Confirm a supported execution job type" in str(failure.value)


def test_given_deduped_job_when_polled_then_not_reported_as_completed(tmp_path) -> None:
    client = make_client(
        [
            httpx.Response(
                202,
                headers={
                    "Location": "https://api.fabric.microsoft.com/v1/workspaces/test/items/flow/jobs/instances/one"
                },
            ),
            httpx.Response(200, json={"status": "Deduped"}),
        ]
    )
    deployment = Deployment(
        client,
        load_config(ROOT / "infra/fabric/config.json"),
        "00000000-0000-4000-8000-000000000001",
        tmp_path / "state.json",
    )
    deployment.state["items"]["flow_reference"] = "flow"

    with pytest.raises(DeploymentError, match="Deduped"):
        deployment.run_flow("reference", "ConfirmedJobType")

    assert deployment.state["jobs"]["reference"]["status"] == "Deduped"

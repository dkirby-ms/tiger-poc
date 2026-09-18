"""Local artifact contract checks; these do not replace execution in a KQL database."""

import csv
import json
import re
from pathlib import Path

import yaml
from tiger_perception.sinks import SCHEMA

DETECT = Path(__file__).resolve().parents[1]
FABRIC = DETECT.parent / "fabric"


def test_given_raw_mapping_when_parsed_then_detect_fields_are_preserved() -> None:
    """Require canonical wire fields and optional observation evidence."""
    script = (FABRIC / "kql/01_create_tables.kql").read_text()
    mapping = json.loads("".join(re.findall(r"^'(.*)'$", script, re.MULTILINE)))

    assert {entry["column"] for entry in mapping} == set(SCHEMA["required"]) | {
        "observation", "plantId", "plantName"
    }
    assert all(entry["Properties"]["Path"] == f"$.{entry['column']}" for entry in mapping)
    assert all("path" not in entry for entry in mapping)
    assert ".alter table ProcessEventsRaw policy ingestiontime true" in script


def test_given_plant_seed_when_parsed_then_twin_metadata_matches() -> None:
    """Keep CSV seed metadata aligned with the manually configured twin."""
    script = (FABRIC / "kql/01_create_tables.kql").read_text()
    instances = json.loads((FABRIC / "digital_twin/twin_instances.json").read_text())
    seed = script.split(".ingest inline into table Plants <|", 1)[1]
    seed = seed.strip().split("\n\n", 1)[0]

    rows = list(csv.reader(seed.splitlines()))

    assert all(len(row) == 4 for row in rows)
    assert {tuple(row[:3]) for row in rows} == {
        (plant["plantId"], plant["plantName"], plant["location"])
        for plant in instances["plants"]
    }


def test_given_occupancy_queries_when_no_positions_then_rate_is_unknown() -> None:
    """Require explicit typed null guards in the shipped KQL rate expressions."""
    dashboard = json.loads((FABRIC / "dashboards/fabric_realtime_dashboard.json").read_text())
    samples = (FABRIC / "kql/03_sample_queries.kql").read_text()

    rate_query = next(
        query["text"] for query in dashboard["queries"]
        if "project Rate" in query["text"]
    )
    sample_query = samples.split("// Query 2:", 1)[1].split("// Query 3:", 1)[0]
    guarded_rate = (
        "iff(TotalPositions == 0, real(null), "
        "round(100.0 * OccupiedCount / TotalPositions, 1))"
    )

    for query in (rate_query, sample_query):
        assert "TotalPositions = count()" in query
        assert "OccupiedCount = countif(isOccupied == true)" in query
        assert guarded_rate in query
    assert f"| project Rate = {guarded_rate}" in rate_query
    assert f"| extend OccupancyRate = {guarded_rate}" in sample_query


def test_given_detect_manifests_when_joined_then_reference_identities_match() -> None:
    """All shipped detect workload subjects resolve to the correct source and plant."""
    instances = json.loads((FABRIC / "digital_twin/twin_instances.json").read_text())
    positions = {item["positionId"]: item for item in instances["monitoredPositions"]}
    cells = {item["cellId"]: item for item in instances["cells"]}
    plants = {item["plantId"]: item for item in instances["plants"]}
    script = (FABRIC / "kql/01_create_tables.kql").read_text()

    for path in [DETECT.parent.parent / "manifest.yaml", *(DETECT / "manifests").glob("*.yaml")]:
        manifest = yaml.safe_load(path.read_text())
        source = manifest["spec"]["source"]
        position = positions[source["subjectId"]]
        cell = cells[position["cellId"]]
        plant = plants[cell["plantId"]]
        assert position["monitoredSourceId"] == source["id"]
        assert plant["plantId"] == manifest["metadata"]["plantId"]
        assert plant["plantName"] == manifest["metadata"]["plantName"]
        assert source["subjectId"] in cell["relationships"]["monitorsPosition"]
        assert ",".join(position[key] for key in (
            "positionId", "cellId", "positionName", "monitoredSourceId"
        )) in script
        assert all(value is None for value in position["initialState"].values())


def test_given_update_policy_when_parsed_then_transform_precedes_aggregation() -> None:
    """Keep bool filtering out of the materialized-view aggregation definition."""
    script = (FABRIC / "kql/02_update_policy.kql").read_text()
    policy = json.loads(re.search(r"@'(\[.*\])'", script).group(1))
    view = script.split(".create async materialized-view", 1)[1]

    assert policy[0]["Source"] == "ProcessEventsRaw"
    assert policy[0]["Query"] == "ExtractConfirmedPresence()"
    assert policy[0]["IsTransactional"] is True
    assert 'observationType in ("PalletPresent", "ObjectPresent")' in script
    assert 'gettype(value) == "bool" and unit == "boolean"' in script
    assert "arg_max(capturedAt, *) by subjectId" in view
    assert "async materialized-view" in script
    assert "| where" not in view and "| project" not in view


def test_given_eventhub_contract_when_read_then_rbac_skus_require_standard_or_premium() -> None:
    """Managed-identity producers should not advertise a Basic Event Hubs SKU."""
    main = (Path(__file__).resolve().parents[3] / "infra" / "digital-twin-poc" / "main.bicep").read_text()
    types = (Path(__file__).resolve().parents[3] / "infra" / "digital-twin-poc" / "types.bicep").read_text()

    assert "param skuName 'Standard' | 'Premium' = 'Standard'" in main
    assert "name: 'Standard' | 'Premium'" in types
    assert "'Basic'" not in main and "'Basic'" not in types


def test_given_twin_binding_when_read_then_only_confirmed_latest_state_is_used() -> None:
    """Generic ProcessEvents must not overwrite position occupancy."""
    ontology = json.loads((FABRIC / "digital_twin/ontology_definition.json").read_text())
    binding = ontology["telemetryBindings"][0]

    assert binding["sourceStream"] == "CurrentPositionOccupancy"
    assert binding["mappingRule"]["entityPrimaryKey"] == "positionId"
    assert binding["mappingRule"]["propertyUpdates"]["isOccupied"] == "isOccupied"


def test_given_qr_assets_when_read_then_case_identity_is_separate_from_occupancy() -> None:
    script = (FABRIC / "kql/02_update_policy.kql").read_text()
    extraction = script.split("function ExtractBoxIdentifications()", 1)[1].split("\n}", 1)[0]
    assert 'observationType == "BoxIdentified"' in extraction
    assert 'gettype(value) == "string" and unit == "identifier"' in extraction
    assert 'subjectId matches regex @"^CASE-[0-9]{3}$"' in extraction
    assert "tostring(value) == subjectId" in extraction
    assert 'gettype(observation.positionId) == "string"' in extraction
    assert "isnotempty(plantId) and isnotempty(positionId)" in extraction
    assert "isOccupied" not in extraction
    latest = script.split("LastCaseIdentification on table BoxIdentificationEvents", 1)[1]
    assert "arg_max(capturedAt, *) by plantId, subjectId" in latest
    assert "| where" not in latest
    ontology = json.loads((FABRIC / "digital_twin/ontology_definition.json").read_text())
    binding = next(item for item in ontology["telemetryBindings"] if item["targetEntityType"] == "Case")
    assert binding["historyStream"] == "BoxIdentificationEvents"
    assert binding["sourceStream"] == "LastCaseIdentification"
    assert "isOccupied" not in binding["mappingRule"]["propertyUpdates"]
    workload = yaml.safe_load((DETECT / "manifests/cell-c-qr.yaml").read_text())
    instances = json.loads((FABRIC / "digital_twin/twin_instances.json").read_text())
    position = next(item for item in instances["monitoredPositions"] if item["positionId"] == workload["spec"]["source"]["subjectId"])
    assert position["monitoredSourceId"] == workload["spec"]["source"]["id"]
    assert {item["caseId"] for item in instances["cases"]} == {"CASE-001", "CASE-002", "CASE-003"}


def test_given_qr_dashboard_when_read_then_counts_history_not_inventory() -> None:
    dashboard = json.loads((FABRIC / "dashboards/fabric_realtime_dashboard.json").read_text())
    page = next(page for page in dashboard["pages"] if page["name"] == "QR Case Identifications")
    tiles = [tile for tile in dashboard["tiles"] if tile["pageId"] == page["id"]]
    assert len(tiles) == 3
    queries = {query["id"]: query for query in dashboard["queries"]}
    latest = next(queries[tile["queryRef"]["queryId"]] for tile in tiles if tile["title"].startswith("Last Case"))
    assert latest["usedVariables"] == []
    assert "LastCaseIdentification" in latest["text"]
    history = next(queries[tile["queryRef"]["queryId"]] for tile in tiles if tile["title"] == "Case Identification History")
    assert "arg_max(publishedAt, *) by eventId" in history["text"]
    assert history["usedVariables"] == ["_startTime", "_endTime"]


def test_given_dashboard_when_read_then_queries_use_current_contract() -> None:
    """Prevent legacy table names and invented ingestion timestamps from returning."""
    dashboard = json.loads((FABRIC / "dashboards/fabric_realtime_dashboard.json").read_text())
    queries = "\n".join(query["text"] for query in dashboard["queries"])
    queries += (FABRIC / "dashboards/powerbi_directquery_kql.m").read_text()
    queries += (FABRIC / "kql/03_sample_queries.kql").read_text()

    assert "CurrentPalletOccupancy" not in queries
    assert "palletPositionId" not in queries
    assert "ingestionTime" not in queries
    assert "ingestion_time()" in queries
    status_tile = next(tile for tile in dashboard["tiles"] if tile["title"] == "Last Confirmed Position State")
    status_query = next(query for query in dashboard["queries"] if query["id"] == status_tile["queryRef"]["queryId"])
    assert "join kind=inner Plants on plantId" in status_query["text"]


def test_given_dashboard_template_when_shared_then_connection_is_unconfigured() -> None:
    dashboard = json.loads((FABRIC / "dashboards/fabric_realtime_dashboard.json").read_text())

    assert "id" not in dashboard and "eTag" not in dashboard
    assert dashboard["schema_version"] == 82
    assert dashboard["autoRefresh"] == {"enabled": False}
    assert len(dashboard["dataSources"]) == 1
    source = dashboard["dataSources"][0]
    assert source == {
        "id": "50be4fa0-851c-4631-9896-000000000003",
        "name": "Configure Tiger KQL Database", "kind": "manual-kusto",
        "clusterUri": "https://example.invalid", "database": "REPLACE_WITH_KQL_DATABASE",
    }
    queries = {query["id"]: query for query in dashboard["queries"]}
    assert len(queries) == len(dashboard["queries"]) == len(dashboard["tiles"]) == 13
    assert len({tile["id"] for tile in dashboard["tiles"]}) == 13
    for tile in dashboard["tiles"]:
        assert tile["pageId"] in {page["id"] for page in dashboard["pages"]}
        query = queries[tile["queryRef"]["queryId"]]
        assert query["dataSource"] == {"kind": "inline", "dataSourceId": source["id"]}
        assert query["usedVariables"] == [
            name for name in ("_startTime", "_endTime") if name in query["text"]
        ]
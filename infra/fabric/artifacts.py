"""Render Fabric definitions and reference tables without credentials or I/O to Fabric."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

DEFINITIONS = Path(__file__).parent / "definitions"
INGESTION_TIME_POLICY = ".alter table ProcessEventsRaw policy ingestiontime true"


def database_schema(config: dict) -> str:
    """Compile the two known KQL artifacts for a new, empty database.

    The shipped scripts start commands at column zero. Reference ingestion and
    inspection blocks remain separate from the schema definition. This is not
    a general-purpose KQL parser.
    """
    commands = []
    for filename in ("01_create_tables.kql", "02_update_policy.kql"):
        content = (Path(config["artifactRoot"]) / "kql" / filename).read_text()
        content = "\n".join(
            line for line in content.splitlines() if not line.lstrip().startswith("//")
        )
        for block in re.split(r"(?m)(?=^\.[A-Za-z])", content):
            command = block.strip()
            if command.startswith((".create ", ".create-or-alter ", ".alter ")):
                command = re.sub(
                    r"^\.create table (?=\w+\s*\()", ".create-merge table ", command
                )
                command = command.replace(
                    ".create async materialized-view with (backfill=true)",
                    ".create-or-alter materialized-view",
                    1,
                )
                commands.append(command)
            elif command.startswith(".") and not command.startswith(
                (".ingest inline ", ".show ")
            ):
                raise ValueError(f"Unsupported deployment command in {filename}")
    if len(commands) != 15 or commands.count(INGESTION_TIME_POLICY) != 1:
        raise ValueError(
            "Expected fifteen commands including the ingestion-time policy; review the KQL artifact compiler after changing command structure"
        )
    return (
        "\n\n".join(command for command in commands if command != INGESTION_TIME_POLICY)
        + "\n"
    )


def reference_ingest(config: dict, table: str, content: str) -> str:
    """Produce idempotent reference ingestion from CSV, without appending duplicates."""
    if table not in {"Plants", "Cells", "MonitoredPositions", "Cases"}:
        raise ValueError("Only reference tables may be replaced")
    script = (Path(config["artifactRoot"]) / "kql/01_create_tables.kql").read_text()
    schema = re.search(rf"\.create table {table} \((.*?)\)", script, re.DOTALL)
    if not schema:
        raise ValueError(f"Missing schema for {table}")
    fields = [field.strip().split(":") for field in schema[1].split(",")]
    values = []
    for row in csv.DictReader(io.StringIO(content)):
        for name, kind in fields:
            value = row[name.strip()]
            if kind.strip() == "string":
                values.append(json.dumps(value))
            elif kind.strip() == "datetime":
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                values.append(f"datetime({timestamp.isoformat()})")
            else:
                raise ValueError(f"Unsupported reference type: {kind}")
    return (
        f".set-or-replace {table} <|\ndatatable ({schema[1]}) [\n"
        + ",\n".join(values)
        + "\n]"
    )


def load_config(path: Path) -> dict:
    """Validate local settings and resolve reference data relative to the config."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", config["prefix"]):
        raise ValueError(
            "prefix must start with a letter and contain at most 40 letters, digits or underscores"
        )
    if not 5 <= config["targetLatencyMinutes"] <= 180:
        raise ValueError("targetLatencyMinutes must be between 5 and 180")
    if not config["observationTypes"] or not all(
        value in {"ObjectPresent", "PalletPresent"}
        for value in config["observationTypes"]
    ):
        raise ValueError("observationTypes must contain presence observation types")
    config["artifactRoot"] = str((path.parent / config["artifactRoot"]).resolve())
    return config


def reference_tables(config: dict) -> dict[str, str]:
    """Read the canonical KQL reference seeds using the standard CSV parser."""
    script = Path(config["artifactRoot"]) / "kql/01_create_tables.kql"
    content = script.read_text(encoding="utf-8")
    result = {}
    for name in ("Plants", "Cells", "MonitoredPositions", "Cases"):
        schema = re.search(rf"\.create table {name} \((.*?)\)", content, re.DOTALL)
        seed = re.search(
            rf"\.ingest inline into table {name} <\|\n(.*?)(?:\n\s*\n|$)",
            content,
            re.DOTALL,
        )
        if not schema or not seed:
            raise ValueError(f"Missing canonical schema or seed for {name}")
        columns = [column.strip().split(":")[0] for column in schema[1].split(",")]
        rows = list(csv.reader(io.StringIO(seed[1])))
        if not rows or any(len(row) != len(columns) or not all(row) for row in rows):
            raise ValueError(f"Invalid reference rows for {name}")
        if len({row[0] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate reference identity in {name}")
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        result[name] = output.getvalue()
    return result


def deployment_model(config: dict) -> dict:
    """Translate the PR's design reference into the inputs for public definitions."""
    ontology = json.loads(
        (
            Path(config["artifactRoot"]) / "digital_twin/ontology_definition.json"
        ).read_text()
    )
    types = {
        "string": "String",
        "boolean": "Bool",
        "double": "Double",
        "datetime": "DateTime",
    }
    tables = {
        "Plant": "Plants",
        "Cell": "Cells",
        "MonitoredPosition": "MonitoredPositions",
        "Case": "Cases",
    }
    bindings = {
        binding["targetEntityType"]: binding["mappingRule"]
        for binding in ontology["telemetryBindings"]
    }
    telemetry = {
        binding["targetEntityType"]: binding
        for binding in ontology["telemetryBindings"]
    }
    entities = []
    for index, entity in enumerate(ontology["entityTypes"], start=10001):
        name = entity["id"]
        binding = bindings.get(name, {})
        updates = binding.get("propertyUpdates", {})
        properties = {
            prop["name"]: [prop["name"], types[prop["type"]]]
            for prop in entity["properties"]
            if prop["name"] not in updates
        }
        key = next(
            prop["name"] for prop in entity["properties"] if prop.get("isPrimaryKey")
        )
        rendered = {
            "id": str(index),
            "name": name,
            "table": tables[name],
            "key": key,
            "properties": properties,
        }
        if updates:
            rendered["timeseries"] = {
                prop["name"]: [updates[prop["name"]], types[prop["type"]]]
                for prop in entity["properties"]
                if prop["name"] in updates
            }
            rendered["timeseries"]["eventId"] = ["eventId", "String"]
            rendered["timeseries"]["Timestamp"] = ["capturedAt", "DateTime"]
            rendered["linkProperty"] = binding["entityPrimaryKey"]
            rendered["historyStream"] = telemetry[name].get(
                "historyStream", "ConfirmedPresenceEvents"
            )
            rendered["observationTypes"] = telemetry[name].get(
                "observationTypes", config["observationTypes"]
            )
        entities.append(rendered)
    by_name = {entity["name"]: entity for entity in entities}
    relationships = []
    for index, relation in enumerate(ontology["relationshipTypes"], start=20001):
        first = by_name[relation["sourceEntityType"]]
        second = by_name[relation["targetEntityType"]]
        join_key = first["key"]
        second["properties"][join_key] = [join_key, "String"]
        relationships.append(
            {
                "id": str(index),
                "name": relation["id"],
                "from": first["name"],
                "to": second["name"],
                "join": [join_key, join_key],
            }
        )
    return {
        "baseEntityTypeId": "2",
        "entities": entities,
        "relationships": relationships,
    }


def substitute(value: Any, bindings: dict[str, str]) -> Any:
    """Replace whole JSON string placeholders, preserving escaping and types."""
    if isinstance(value, dict):
        return {key: substitute(child, bindings) for key, child in value.items()}
    if isinstance(value, list):
        return [substitute(child, bindings) for child in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return bindings[value[2:-1]]
    return value


def operation_id(name: str) -> str:
    """Keep mapping identifiers stable across deployments and retries."""
    return str(uuid5(NAMESPACE_URL, f"https://tiger-poc/fabric/operations/{name}"))


def twin_definition(
    config: dict, workspace: str, source: str, backing: str
) -> tuple[dict, dict]:
    """Build public definition parts and ordered flow groups from the local model."""
    model = deployment_model(config)
    parts = {"definition.json": {"LakehouseId": backing}}
    groups = {"reference": [], "relationships": [], "timeseries": []}
    entities = {entity["name"]: entity for entity in model["entities"]}
    filters = {
        "type": "logical",
        "LogicalOperatorKind": "Or",
        "FilterOperations": [
            {
                "type": "comparison",
                "SourceColumn": "observationType",
                "ComparisonOperatorKind": "Eq",
                "Value": value,
                "ValueType": "String",
            }
            for value in config["observationTypes"]
        ],
    }
    for entity in entities.values():
        identifier = entity["id"]
        property_index = int(identifier) * 100

        def properties(entries: dict, index: int) -> list[dict]:
            return [
                {"Id": str(index + offset), "Name": name, "ValueType": spec[1]}
                for offset, (name, spec) in enumerate(entries.items(), start=1)
            ]

        parts[f"EntityTypes/{identifier}.json"] = {
            "Id": identifier,
            "Namespace": "usertypes",
            "BaseEntityTypeId": model["baseEntityTypeId"],
            "Name": entity["name"],
            "Properties": properties(entity["properties"], property_index),
            "TimeseriesProperties": [],
        }
        if entity.get("timeseries"):
            property_index += 50
            parts[f"EntityTypes/{identifier}.json"]["TimeseriesProperties"] = (
                properties(entity["timeseries"], property_index)
            )
        for timeseries in [False, True] if entity.get("timeseries") else [False]:
            name = entity["name"] + ("_timeseries" if timeseries else "_reference")
            operation = operation_id(name)
            table = entity["historyStream"] if timeseries else entity["table"]
            mappings = [
                {"SourceColumn": spec[0], "EntityTypePropertyName": name}
                for name, spec in entity[
                    "timeseries" if timeseries else "properties"
                ].items()
            ]
            parts[f"MappingOperations/{operation}.json"] = {
                "OperationId": operation,
                "DisplayName": name,
                "OperationType": "Mapping",
                "EntityTypeId": identifier,
                "MappingOperationProperties": {
                    "MappingType": "TimeSeries" if timeseries else "NonTimeSeries",
                    "MappedProperties": mappings,
                    "ProcessingType": "Incremental" if timeseries else "Iterative",
                    "EntityInstanceIdSchema": [] if timeseries else [entity["key"]],
                    "TimeseriesEntityLinkProperties": {
                        "EntityProperty": entity["linkProperty"],
                        "TimeseriesProperty": "subjectId",
                    }
                    if timeseries
                    else None,
                },
                "SourceTableProperties": {
                    "SourceType": "LakehouseTables",
                    "WorkspaceId": workspace,
                    "ItemId": source,
                    "SourceTableName": table,
                    "SourceSchema": None,
                },
                "Filters": {
                    **filters,
                    "FilterOperations": [
                        {**filters["FilterOperations"][0], "Value": value}
                        for value in entity["observationTypes"]
                    ],
                }
                if timeseries
                else None,
            }
            group = "timeseries" if timeseries else "reference"
            groups[group].append(operation)
    for relation in model["relationships"]:
        identifier = relation["id"]
        first = entities[relation["from"]]["id"]
        second = entities[relation["to"]]["id"]
        parts[f"EntityTypeRelationships/{identifier}.json"] = {
            "Id": identifier,
            "Namespace": "usertypes",
            "RelationshipCardinality": "OneToMany",
            "Name": relation["name"],
            "FirstEntityTypeId": first,
            "SecondEntityTypeId": second,
        }
        operation = operation_id(f"relationship_{identifier}")
        parts[f"ContextualizationOperations/{operation}.json"] = {
            "OperationId": operation,
            "DisplayName": f"{relation['from']}_{relation['name']}_{relation['to']}",
            "OperationType": "Contextualization",
            "EntityTypeRelationshipId": identifier,
            "JoinColumns": {
                "FirstColumn": {
                    "EntityId": first,
                    "AttributeName": relation["join"][0],
                },
                "SecondColumn": {
                    "EntityId": second,
                    "AttributeName": relation["join"][1],
                },
            },
        }
        groups["relationships"].append(operation)
    return parts, groups

"""Manifest and mapping checks without cameras or inference dependencies."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from tiger_perception.config import Perception, load_workload, resolve_source
from tiger_perception.contracts import Observation
from tiger_perception.mapping import map_presence

MANIFESTS = Path(__file__).parents[1] / "manifests"


def test_given_default_compose_stack_when_configured_then_isolate_credentials_and_outputs():
    compose = yaml.safe_load((MANIFESTS.parents[1] / "docker-compose.yml").read_text())
    services = compose["services"]
    qr = services["detect-qr"]
    viewer = services["viewer"]

    assert set(services) == {"detect", "detect-qr", "viewer", "publisher", "publisher-qr"}
    assert all("profiles" not in service for service in services.values())
    assert set(services["detect"]["environment"]) == {"CAMERA_A_RTSP_URL"}
    assert qr["command"][-2:] == ["--manifest", "manifests/cell-c-qr.yaml"]
    assert set(qr["environment"]) == {"CAMERA_C_RTSP_URL"}
    assert qr["environment"]["CAMERA_C_RTSP_URL"] == "${CAMERA_C_RTSP_URL:?Set CAMERA_C_RTSP_URL in apps/.env}"
    assert qr["user"] == services["detect"]["user"]
    assert qr["volumes"][0]["bind"]["create_host_path"] is False
    assert "environment" not in viewer
    assert viewer["volumes"][0]["read_only"] is True
    assert "manifests/cell-a-jeep.yaml" in viewer["command"]
    assert "manifests/cell-c-qr.yaml" in viewer["command"]
    assert viewer["ports"] == ["127.0.0.1:${VIEWER_PORT:-8765}:8765"]
    assert "/workspace/data/cell-a/jeep-events.jsonl" in services["publisher"]["command"]
    publisher_qr = services["publisher-qr"]
    assert "/workspace/data/cell-c/events.jsonl" in publisher_qr["command"]
    assert publisher_qr["volumes"][0]["read_only"] is True
    assert publisher_qr["volumes"][1] == "publisher-qr-state:/var/lib/tiger-publisher"
    assert services["publisher"]["volumes"][1] == "publisher-state:/var/lib/tiger-publisher"
    assert set(compose["volumes"]) == {"publisher-state", "publisher-qr-state"}
    assert compose["secrets"] == {"fabric_connection_string": {"file": "./secrets/fabric-connection-string"}}
    for name in ("publisher", "publisher-qr"):
        assert services[name]["environment"] == {
            "FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE": "/run/secrets/fabric_connection_string"}
        assert services[name]["secrets"] == ["fabric_connection_string"]
        assert services[name]["restart"] == "no"
        assert services[name]["volumes"][0]["read_only"] is True
        assert "--follow" in services[name]["command"]
        assert "--live-fabric" in services[name]["command"]
    assert all("secrets" not in services[name] for name in ("detect", "detect-qr", "viewer"))


def test_given_qr_provider_when_configured_then_no_model_required():
    settings = Perception(provider="qr", observationType="BoxIdentified", sampleEveryFrames=1)

    assert settings.model is None
    assert settings.labels == ["qr"]


@pytest.mark.parametrize("overrides", [
    {"model": "chair.pt"}, {"labels": ["chair"]}, {"observationType": "ObjectPresent"},
])
def test_given_qr_provider_when_mixed_with_yolo_settings_then_reject(overrides):
    settings = {"provider": "qr", "observationType": "BoxIdentified", "sampleEveryFrames": 1}
    settings.update(overrides)

    with pytest.raises(ValueError):
        Perception(**settings)


@pytest.mark.parametrize("cell", ["a", "b"])
def test_given_manifest_when_loaded_then_paths_and_identity_are_independent(cell):
    workload = load_workload(MANIFESTS / f"cell-{cell}.yaml")

    assert workload.spec.source.id == f"cell-{cell}-camera-01"
    assert Path(workload.spec.destination.path).parts[-2:] == (f"cell-{cell}", "events.jsonl")
    assert Path(workload.spec.perception.model).is_file()


@pytest.mark.parametrize("section,field,value", [
    ("region", "bounds", [0.8, 0.2, 0.1, 0.9]),
    ("region", "coordinates", "pixels"), ("source", "subjectId", ""),
    ("presence", "staleSeconds", 0), ("presence", "confidence", float("nan")),
    ("presence", "emptySeconds", -1), ("presence", "confidence", True),
    ("perception", "observationType", "PalletPresent"),
    ("perception", "sampleEveryFrames", 0), ("perception", "provider", "foundry-local"),
])
def test_given_invalid_settings_when_loading_then_fail_without_value_leak(tmp_path, section, field, value):
    document = yaml.safe_load((MANIFESTS / "cell-a.yaml").read_text())
    document["spec"][section][field] = value
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(document))

    with pytest.raises(ValueError):
        load_workload(path)


def test_given_missing_reference_when_resolving_then_clear_error(monkeypatch):
    workload = load_workload(MANIFESTS / "cell-a.yaml")
    monkeypatch.delenv("CAMERA_A_RTSP_URL", raising=False)

    with pytest.raises(ValueError, match="CAMERA_A_RTSP_URL"):
        resolve_source(workload.spec.source)


def test_given_pallet_manifest_when_loaded_then_use_pallet_detection_contract():
    workload = load_workload(MANIFESTS / "cell-b-pallet.yaml")

    assert workload.spec.perception.observationType == "PalletPresent"
    assert workload.spec.perception.labels == ["pallet"]
    assert workload.spec.source.subjectId == "cell-b-pallet-position-01"


@pytest.mark.parametrize("cell,present", [("a", True), ("b", False)])
def test_given_confirmed_observation_when_mapping_then_preserve_identity_metadata_and_retry_id(cell, present):
    workload = load_workload(MANIFESTS / f"cell-{cell}.yaml")
    timestamp = "2026-09-15T12:00:00+00:00"
    observation = Observation("stable-retry-id", workload.spec.source.id, "ObjectPresent",
                              present, 0.8 if present else 0.0, timestamp, timestamp,
                              "ultralytics", "yolo26n.pt", workload.spec.source.subjectId,
                              "resolved", "boolean")

    event = map_presence(observation, workload)

    assert event["eventId"] == map_presence(observation, workload)["eventId"]
    assert event["value"] is present
    assert event["plantId"] == "demo-plant-01"
    assert event["plantName"] == "Demo Plant"
    assert event["subjectId"] == workload.spec.source.subjectId
    with pytest.raises(ValueError):
        map_presence(replace(observation, subject_resolution="unresolved"), workload)
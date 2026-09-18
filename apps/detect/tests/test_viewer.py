"""Viewer stale-state, identity, and HTTP surface checks."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from tiger_perception.config import load_workload
from tiger_perception.viewer import cell_status, create_parser, create_server

MANIFESTS = Path(__file__).parents[1] / "manifests"


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_given_bind_option_when_server_created_then_use_selected_address(host):
    args = create_parser().parse_args(["--manifest", str(MANIFESTS / "cell-a.yaml"),
                                      *(["--host", host] if host != "127.0.0.1" else [])])
    with create_server([load_workload(args.manifest[0])], 0, host=args.host) as server:
        assert server.server_address[0] == host


def test_given_stopped_producer_when_viewing_then_retain_value_but_mark_unavailable(tmp_path):
    workload = load_workload(MANIFESTS / "cell-a.yaml")
    workload.spec.destination.statusPath = str(tmp_path / "status.json")
    now = datetime.now(UTC)
    timestamp = (now - timedelta(seconds=10)).isoformat()
    Path(workload.spec.destination.statusPath).write_text(json.dumps({
        "sourceId": workload.spec.source.id, "subjectId": workload.spec.source.subjectId,
        "writtenAt": timestamp, "capturedAt": timestamp,
        "lastConfirmed": True, "availability": "current",
    }))

    status = cell_status(workload, now=now)

    assert status["lastConfirmed"] is True
    assert status["availability"] == "unavailable"


def test_given_missing_status_when_viewing_then_unknown_not_empty():
    workload = load_workload(MANIFESTS / "cell-a.yaml")
    workload.spec.destination.statusPath = "/nonexistent-tiger-status.json"

    assert cell_status(workload)["lastConfirmed"] is None


def test_given_same_camera_when_starting_viewer_then_reject():
    workload = load_workload(MANIFESTS / "cell-a.yaml")

    with pytest.raises(ValueError, match="independent"):
        create_server([workload, workload], 0)


def test_given_qr_and_chair_examples_when_viewing_together_then_keep_separate_identities():
    workloads = [load_workload(MANIFESTS / name) for name in ("cell-a.yaml", "cell-c-qr.yaml")]

    with create_server(workloads, 0) as server:
        assert server.server_port > 0
        assert workloads[0].spec.perception.labels == ["chair"]
        assert workloads[1].spec.perception.model is None
        assert len({item.spec.destination.path for item in workloads}) == 2


def test_given_viewer_when_requesting_routes_then_serve_only_public_artifacts():
    workload = load_workload(MANIFESTS / "cell-a.yaml")
    with create_server([workload], 0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/cells") as response:
                payload = json.load(response)
            with urlopen(base) as response:
                page = response.read().decode()

            assert payload[0]["sourceId"] == workload.spec.source.id
            assert "Cell Monitor" in page
            assert "uriFrom" not in json.dumps(payload)
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/../../apps/.env")
            assert error.value.code == 404
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_given_jeep_and_qr_scenarios_when_requesting_previews_then_keep_manifest_order(tmp_path):
    workloads = [load_workload(MANIFESTS / name) for name in ("cell-a-jeep.yaml", "cell-c-qr.yaml")]
    for index, workload in enumerate(workloads):
        workload.spec.destination.statusPath = str(tmp_path / f"status-{index}.json")
        Path(workload.spec.destination.statusPath).with_suffix(".jpg").write_bytes(f"preview-{index}".encode())

    with create_server(workloads, 0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/?scenario=cell-c-camera-01") as response:
                page = response.read().decode()
            assert 'id="scenario-tabs"' in page
            assert 'role="tablist" aria-label="Use cases"' in page
            assert 'role="tabpanel" tabindex="0" hidden' in page
            assert 'id="scenario-select"' not in page
            with urlopen(base + "/api/cells") as response:
                cells = json.load(response)
            assert [cell["sourceId"] for cell in cells] == [workload.spec.source.id for workload in workloads]
            for index in range(2):
                with urlopen(base + f"/preview/{index}.jpg") as response:
                    assert response.read() == f"preview-{index}".encode()
            with pytest.raises(HTTPError) as error:
                urlopen(base + "/preview/2.jpg")
            assert error.value.code == 404
        finally:
            server.shutdown()
            thread.join(timeout=2)
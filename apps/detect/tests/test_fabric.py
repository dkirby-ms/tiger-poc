"""Regression coverage for edge functionality migrated into detect."""

import json
from pathlib import Path
from typing import Any

import pytest
from tiger_perception import fabric as relay
from tiger_perception.contracts import ProcessEvent
from tiger_perception.sinks import (
    SinkError,
    SinkUnavailableError,
    validate_process_event,
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of real Fabric credentials and mock flags."""
    for name in (
        "FABRIC_EVENTSTREAM_CONNECTION_STRING", "FABRIC_EVENTSTREAM_EVENTHUB_NAME",
        "FABRIC_EVENTSTREAM_NAMESPACE", "FABRIC_EVENTSTREAM_REST_ENDPOINT", "MOCK_FABRIC",
    ):
        monkeypatch.delenv(name, raising=False)


def test_given_demo_when_generated_then_both_cells_have_valid_transitions() -> None:
    """Retain the multi-cell scenario with canonical presence semantics."""
    events = relay.generate_scenario_events()

    assert len(events) == 6
    assert len({event["eventId"] for event in events}) == 6
    assert [event["value"] for event in events] == [False, False, True, True, False, False]
    assert {event["observationType"] for event in events} == {"ObjectPresent", "PalletPresent"}
    assert all(validate_process_event(event) == event for event in events)
    assert all("plantId" not in event and "plantName" not in event for event in events)


def test_given_typed_event_when_traced_then_detect_redacts_evidence(tmp_path: Path) -> None:
    """Use the actual detect dataclass and recursive sanitization."""
    event = relay.generate_scenario_events()[0]
    event["observation"] = {"metadata": {"token": "do-not-publish"}}
    trace = tmp_path / "trace.jsonl"
    sink = relay.FabricEventstreamSink(dry_run=True, fallback_jsonl_path=trace)

    sink.publish(ProcessEvent.from_dict(event))
    sink.publish(event)

    records = [json.loads(line) for line in trace.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["observation"]["metadata"]["token"] == "[REDACTED]"


@pytest.mark.parametrize("value,unit", [("true", "boolean"), (1, "boolean"), (True, "status")])
def test_given_invalid_presence_when_published_then_detect_rejects(value: Any, unit: str) -> None:
    """Do not relax detect's boolean presence contract."""
    event = {**relay.generate_scenario_events()[0], "value": value, "unit": unit}

    with pytest.raises(SinkError):
        relay.FabricEventstreamSink(dry_run=True).publish(event)


def test_given_missing_destination_when_live_then_fail_closed() -> None:
    """Live publication cannot silently become a dry run."""
    with pytest.raises(SinkError, match="requires a Fabric destination"):
        relay.FabricEventstreamSink()


def test_given_eventhub_when_publishing_twice_then_reuse_open_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only close the producer after all events, not after the first batch."""
    EventHubProducerClient = pytest.importorskip("azure.eventhub").EventHubProducerClient

    class Producer:
        """Minimal producer that rejects sends after close."""

        closed = False
        sent = 0

        def create_batch(self, *, partition_key: str) -> list[Any]:
            """Create a fake batch with the SDK add interface."""
            assert partition_key.startswith("cell-")

            class Batch(list[Any]):
                """Accept EventData using the SDK method name."""

                add = list.append

            return Batch()

        def send_batch(self, batch: list[Any]) -> None:
            """Capture one send while the client is open."""
            assert not self.closed
            assert len(batch) == 1
            self.sent += 1

        def close(self) -> None:
            """Mark the client closed."""
            self.closed = True

    producer = Producer()
    monkeypatch.setattr(EventHubProducerClient, "from_connection_string", lambda **kwargs: producer)
    sink = relay.FabricEventstreamSink(connection_string="test-only")

    for event in relay.generate_scenario_events()[:2]:
        sink.publish(event)
    sink.close()

    assert producer.sent == 2
    assert producer.closed


def test_given_remote_failure_when_retried_then_trace_dedup_does_not_skip_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local audit record does not prove that remote delivery succeeded."""
    attempts: list[dict[str, Any]] = []

    def fail_post(*args: Any, **kwargs: Any) -> None:
        """Simulate a destination error containing secret material."""
        attempts.append(kwargs)
        raise OSError("sensitive-connection-string")

    requests = pytest.importorskip("requests")
    monkeypatch.setattr(requests, "post", fail_post)
    sink = relay.FabricEventstreamSink(
        rest_endpoint="https://example.invalid/events", fallback_jsonl_path=tmp_path / "trace.jsonl"
    )
    event = relay.generate_scenario_events()[0]

    for _attempt in range(2):
        with pytest.raises(SinkUnavailableError) as error:
            sink.publish(event)
        assert "sensitive-connection-string" not in str(error.value)

    assert len(attempts) == 2
    assert len((tmp_path / "trace.jsonl").read_text().splitlines()) == 1


def test_given_jsonl_when_relayed_then_preserve_ids_and_evidence(tmp_path: Path) -> None:
    """Exercise the CLI against a complete detection output file."""
    event = relay.generate_scenario_events()[0]
    event["observation"] = {"rawInferenceId": "inference-01"}
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(event) + "\n")
    trace = tmp_path / "trace.jsonl"

    result = relay.main(["--input", str(source), "--output", str(trace)])

    assert result == 0
    assert json.loads(trace.read_text()) == event


def test_given_input_as_output_when_relayed_then_refuse_to_modify(tmp_path: Path) -> None:
    """Never append the audit trace to the detection input."""
    source = tmp_path / "events.jsonl"
    source.write_text("unchanged\n")

    with pytest.raises(SystemExit):
        relay.main(["--input", str(source), "--output", str(source)])

    assert source.read_text() == "unchanged\n"


@pytest.mark.parametrize("status_code", [200, 202, 302, 500])
def test_given_rest_response_when_published_then_only_success_is_accepted(
    status_code: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept 2xx only, without following redirects or rewriting detector metadata."""
    requests = pytest.importorskip("requests")
    pytest.importorskip("azure.core")
    event = relay.generate_scenario_events()[0]
    event.update(plantId="demo-plant-01", plantName="Demo Plant")
    calls: list[dict[str, Any]] = []

    def post(url: str, **kwargs: Any) -> Any:
        """Return an actual requests response without network access."""
        calls.append(kwargs)
        response = requests.Response()
        response.status_code = status_code
        return response

    monkeypatch.setattr(requests, "post", post)
    sink = relay.FabricEventstreamSink(rest_endpoint="https://example.invalid/events")

    if status_code < 300:
        assert sink.publish(event) is True
    else:
        with pytest.raises(SinkUnavailableError):
            sink.publish(event)

    assert calls == [{"json": event, "timeout": 5.0, "allow_redirects": False}]
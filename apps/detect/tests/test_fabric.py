"""Regression coverage for edge functionality migrated into detect."""

import builtins
import json
from datetime import UTC, datetime, timedelta
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
        "FABRIC_EVENTSTREAM_NAMESPACE", "MOCK_FABRIC",
        "FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE",
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


def test_given_default_demo_when_generated_then_timestamps_are_not_future_dated() -> None:
    """Keep the entire sequence historical while preserving transition offsets."""
    events = relay.generate_scenario_events()
    captured = [datetime.fromisoformat(event["capturedAt"]) for event in events]

    assert captured[-1] <= datetime.now(UTC)
    assert [(timestamp - captured[0]).total_seconds() for timestamp in captured] == [
        0, 0, 5, 12, 20, 28,
    ]
    assert all(event["capturedAt"] == event["producedAt"] == event["publishedAt"] for event in events)


def test_given_explicit_start_when_generated_then_preserve_requested_timestamps() -> None:
    """Retain explicit start times for reproducible fixtures."""
    start_time = datetime(2026, 1, 1, tzinfo=UTC)

    events = relay.generate_scenario_events(start_time)

    assert datetime.fromisoformat(events[0]["capturedAt"]) == start_time
    assert datetime.fromisoformat(events[-1]["capturedAt"]) == start_time + timedelta(seconds=28)


@pytest.mark.parametrize("iterations", [1, 3])
def test_given_demo_cycles_when_relayed_immediately_then_all_events_end_by_run_start(
    iterations: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backdate the whole run, keeping cycles ordered and event IDs unique."""
    run_start = datetime(2026, 1, 1, tzinfo=UTC)

    class FrozenDatetime(datetime):
        """Supply a deterministic clock without publication delays."""

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            """Return the run start in the requested timezone."""
            return run_start.astimezone(tz)

    monkeypatch.setattr(relay, "datetime", FrozenDatetime)
    trace = tmp_path / "demo.jsonl"

    result = relay.main(["--demo", "--iterations", str(iterations), "--output", str(trace)])
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    captured = [datetime.fromisoformat(event["capturedAt"]) for event in events]

    assert result == 0
    assert len(events) == len({event["eventId"] for event in events}) == 6 * iterations
    assert captured == sorted(captured)
    assert captured[-1] == run_start
    assert all(timestamp <= run_start for timestamp in captured)
    assert (captured[-1] - captured[0]).total_seconds() == 29 * iterations - 1


def test_given_publish_interval_when_relayed_then_skip_sleep_after_last_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pause only between publications, not after the final event."""
    sleep_calls: list[float] = []
    published: list[dict[str, Any]] = []

    class StubSink:
        dry_run = True

        def publish(self, event: dict[str, Any]) -> None:
            """Capture the event stream without network effects."""
            published.append(event)

        def close(self) -> None:
            """No-op cleanup for the relay test."""

    monkeypatch.setattr(relay, "FabricEventstreamSink", lambda **kwargs: StubSink())
    monkeypatch.setattr(relay.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = relay.main([
        "--demo",
        "--interval", "0.5",
        "--output", str(tmp_path / "demo.jsonl"),
    ])

    assert result == 0
    assert len(published) == 6
    assert sleep_calls == [0.5, 0.5, 0.5, 0.5, 0.5]


def test_given_input_file_when_relayed_with_interval_then_sleep_between_each_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """Delay every publication after the first even when the input iterator is lazy."""
    sleep_calls: list[float] = []
    published: list[dict[str, Any]] = []
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(event) for event in relay.generate_scenario_events()) + "\n")

    class StubSink:
        dry_run = True

        def publish(self, event: dict[str, Any]) -> None:
            """Capture the event stream without network effects."""
            published.append(event)

        def close(self) -> None:
            """No-op cleanup for the relay test."""

    monkeypatch.setattr(relay, "FabricEventstreamSink", lambda **kwargs: StubSink())
    monkeypatch.setattr(relay.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = relay.main(["--input", str(source), "--interval", "0.25"])

    assert result == 0
    assert len(published) == 6
    assert sleep_calls == [0.25, 0.25, 0.25, 0.25, 0.25]
    assert "Relay failed" not in caplog.text


def test_given_cleanup_failure_when_relayed_then_exit_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """Cleanup errors should be surfaced as a failed relay exit status."""
    class BrokenSink:
        dry_run = True

        def publish(self, event: dict[str, Any]) -> None:
            """Dummy publisher for the failing close path."""

        def close(self) -> None:
            """Fail cleanup to validate the relay exit status."""
            raise SinkUnavailableError("Fabric client cleanup failed.")

    monkeypatch.setattr(relay, "FabricEventstreamSink", lambda **kwargs: BrokenSink())

    result = relay.main(["--demo", "--output", str(tmp_path / "demo.jsonl")])

    assert result == 1
    assert "Fabric client cleanup failed." in caplog.text


def test_given_invalid_jsonl_when_relayed_then_report_line_without_input_contents(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """Expose sanitized input diagnostics without echoing malformed data."""
    source = tmp_path / "events.jsonl"
    source.write_text("\nsensitive-invalid-json\n")

    result = relay.main(["--input", str(source)])

    assert result == 1
    assert "Invalid ProcessEvent at input line 2." in caplog.text
    assert "sensitive-invalid-json" not in caplog.text


def test_given_non_utf8_jsonl_when_relayed_then_keep_decode_error_private(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-UTF-8 input should fail via the sanitized relay error path."""
    source = tmp_path / "sensitive-binary.jsonl"
    source.write_bytes(b'{"eventId":"ok"}\xff\n')

    result = relay.main(["--input", str(source)])

    assert result == 1
    assert "Relay failed:" in caplog.text
    assert "UnicodeDecodeError" not in caplog.text
    assert "sensitive-binary" not in caplog.text


def test_given_missing_input_when_relayed_then_keep_oserror_details_private(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    """Do not expose raw filesystem paths in relay errors."""
    result = relay.main(["--input", str(tmp_path / "sensitive-missing-file.jsonl")])

    assert result == 1
    assert "Relay failed; verify input data, file access and Fabric configuration." in caplog.text
    assert "sensitive-missing-file" not in caplog.text


@pytest.mark.parametrize("value,unit", [("true", "boolean"), (1, "boolean"), (True, "status")])
def test_given_invalid_presence_when_published_then_detect_rejects(value: Any, unit: str) -> None:
    """Do not relax detect's boolean presence contract."""
    event = {**relay.generate_scenario_events()[0], "value": value, "unit": unit}

    with pytest.raises(SinkError):
        relay.FabricEventstreamSink(dry_run=True).publish(event)


def test_given_non_json_extension_when_published_then_fabric_rejects() -> None:
    """Reject extension values that Event Hubs cannot serialize."""
    event = {**relay.generate_scenario_events()[0], "observation": {"labels": {"person"}}}

    with pytest.raises(SinkError, match="JSON-serializable"):
        relay.FabricEventstreamSink(dry_run=True).publish(event)


def test_given_missing_destination_when_live_then_fail_closed() -> None:
    """Live publication cannot silently become a dry run."""
    with pytest.raises(SinkError, match="requires an Event Hubs destination"):
        relay.FabricEventstreamSink()


@pytest.mark.parametrize("missing_module", ["azure.eventhub", "azure.identity"])
def test_given_partial_azure_install_when_published_then_report_unavailable(
    monkeypatch: pytest.MonkeyPatch, missing_module: str,
) -> None:
    """Keep every optional Azure import inside the controlled failure path."""
    pytest.importorskip("azure.core")
    real_import = builtins.__import__

    def import_without_optional_module(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == missing_module:
            raise ImportError(f"No module named {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_optional_module)
    sink = relay.FabricEventstreamSink(
        namespace="test.servicebus.windows.net", eventhub_name="events"
    )

    with pytest.raises(SinkUnavailableError, match="fabric.*extra"):
        sink.publish(relay.generate_scenario_events()[0])


@pytest.mark.parametrize("authentication", ["connection_string", "namespace"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_given_eventhub_when_publishing_twice_then_reuse_open_producer(
    monkeypatch: pytest.MonkeyPatch, authentication: str, cleanup_fails: bool,
) -> None:
    """Reuse either authentication path and release credentials even if close fails."""
    eventhub = pytest.importorskip("azure.eventhub")
    identity = pytest.importorskip("azure.identity")
    producer_options = []
    credentials = []

    class Credential:
        """Record credential creation and cleanup without authenticating."""

        closed = False

        def __init__(self) -> None:
            """Track each credential created by the publisher."""
            credentials.append(self)

        def close(self) -> None:
            """Reject repeated cleanup."""
            assert not self.closed
            self.closed = True

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
            assert not self.closed
            self.closed = True
            if cleanup_fails:
                raise OSError("sensitive-cleanup-details")

    producer = Producer()

    def create_producer(**kwargs: Any) -> Producer:
        """Record constructor arguments and return the reusable producer."""
        producer_options.append(kwargs)
        return producer

    monkeypatch.setattr(identity, "DefaultAzureCredential", Credential)
    if authentication == "namespace":
        monkeypatch.setattr(eventhub, "EventHubProducerClient", create_producer)
        sink = relay.FabricEventstreamSink(namespace="test.servicebus.windows.net", eventhub_name="events")
    else:
        monkeypatch.setattr(eventhub.EventHubProducerClient, "from_connection_string", create_producer)
        sink = relay.FabricEventstreamSink(connection_string="test-only")

    for event in relay.generate_scenario_events()[:2]:
        sink.publish(event)

    if authentication == "namespace":
        assert len(credentials) == 1
        assert not credentials[0].closed
        assert producer_options == [{
            "fully_qualified_namespace": "test.servicebus.windows.net",
            "eventhub_name": "events",
            "credential": credentials[0],
        }]
    else:
        assert credentials == []
        assert producer_options == [{"conn_str": "test-only"}]

    if cleanup_fails:
        with pytest.raises(SinkUnavailableError, match=r"^Fabric client cleanup failed\.$"):
            sink.close()
    else:
        sink.close()
    sink.close()

    assert producer.sent == 2
    assert producer.closed
    assert all(credential.closed for credential in credentials)
    assert sink._producer_client is None
    assert sink._credential is None


def test_given_remote_failure_when_retried_then_trace_dedup_does_not_skip_send(
    tmp_path: Path,
) -> None:
    """A local audit record does not prove that remote delivery succeeded."""
    attempts = 0

    class FailingProducer:
        """Simulate an Event Hubs failure containing secret material."""

        def create_batch(self, *, partition_key: str) -> None:
            """Fail before creating a batch and count every delivery attempt."""
            nonlocal attempts
            attempts += 1
            raise OSError("sensitive-connection-string")

    sink = relay.FabricEventstreamSink(
        connection_string="test-only", fallback_jsonl_path=tmp_path / "trace.jsonl"
    )
    sink._producer_client = FailingProducer()
    event = relay.generate_scenario_events()[0]

    for _attempt in range(2):
        with pytest.raises(SinkUnavailableError) as error:
            sink.publish(event)
        assert "sensitive-connection-string" not in str(error.value)

    assert attempts == 2
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


def test_given_live_appends_when_followed_then_wait_for_newline_and_resume(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    checkpoint = tmp_path / "delivery.json"
    events = relay.generate_scenario_events()[:2]
    published = []

    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower:
        assert follower.poll_once(published.append) == 0
        source.write_text(json.dumps(events[0]), encoding="utf-8")
        assert follower.poll_once(published.append) == 0
        assert not checkpoint.exists()
        with source.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        assert follower.poll_once(published.append) == 1
        assert follower.poll_once(published.append) == 0

    with source.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(events[1]) + "\n")
    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower:
        assert follower.poll_once(published.append) == 1
    assert published == events


def test_given_failed_send_when_following_then_retry_same_event_on_restart(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    checkpoint = tmp_path / "delivery.json"
    events = relay.generate_scenario_events()[:2]
    source.write_text("".join(json.dumps(event) + "\n" for event in events))

    def fail_second(event):
        if event == events[1]:
            raise SinkUnavailableError("offline")

    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower, pytest.raises(SinkUnavailableError):
        follower.poll_once(fail_second)
    published = []
    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower:
        assert follower.poll_once(published.append) == 1
    assert published == events[1:]


@pytest.mark.parametrize("change", ["truncate", "replace", "corrupt", "prefix"])
def test_given_changed_input_when_following_then_fail_without_skipping(tmp_path: Path, change: str) -> None:
    source = tmp_path / "events.jsonl"
    checkpoint = tmp_path / "delivery.json"
    content = json.dumps(relay.generate_scenario_events()[0]) + "\n"
    source.write_text(content)
    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower:
        follower.poll_once(lambda event: True)
        original = checkpoint.read_bytes()
        if change == "replace":
            source.rename(tmp_path / "old.jsonl")
            source.write_text(content)
        elif change == "prefix":
            assert len(content) > 256
            with source.open("r+b") as handle:
                handle.write(b"x")
        else:
            source.write_text("" if change == "truncate" else "x" * len(content))
        with pytest.raises(SinkError, match="replaced or truncated"):
            follower.poll_once(lambda event: pytest.fail("Unexpected publication"))
        assert checkpoint.read_bytes() == original


def test_given_rewritten_prefix_when_resuming_then_reject_unchanged_tail(tmp_path: Path) -> None:
    source, checkpoint = tmp_path / "events.jsonl", tmp_path / "state.json"
    source.write_text(json.dumps(relay.generate_scenario_events()[0]) + "\n")
    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower:
        follower.poll_once(lambda event: True)
    original = checkpoint.read_bytes()

    with source.open("r+b") as handle:
        handle.write(b"x")

    with (relay.JsonlFollower([source], checkpoint, dry_run=False) as follower,
          pytest.raises(SinkError, match="replaced or truncated")):
        follower.poll_once(lambda event: pytest.fail("Unexpected publication"))
    assert checkpoint.read_bytes() == original


def test_given_legacy_checkpoint_when_resuming_then_require_reconciliation(tmp_path: Path) -> None:
    source, checkpoint = tmp_path / "events.jsonl", tmp_path / "state.json"
    original = json.dumps({"version": 1, "inputs": [str(source)], "mode": "live", "positions": {}})
    checkpoint.write_text(original)
    follower = relay.JsonlFollower([source], checkpoint, dry_run=False)

    with pytest.raises(SinkError, match="Unsupported delivery checkpoint version.*reconcile"), follower:
        pytest.fail("Legacy checkpoint was accepted")

    assert checkpoint.read_text() == original
    assert follower._lock is None


def test_given_checkpoint_owner_when_second_follower_starts_then_refuse(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    checkpoint = tmp_path / "delivery.json"
    with (relay.JsonlFollower([source], checkpoint, dry_run=False),
          pytest.raises(SinkError, match="ownership"),
          relay.JsonlFollower([source], checkpoint, dry_run=False)):
        pytest.fail("Second follower acquired checkpoint")


def test_given_dry_run_checkpoint_when_live_starts_then_refuse(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(json.dumps(relay.generate_scenario_events()[0]) + "\n")
    checkpoint = tmp_path / "delivery.json"
    with relay.JsonlFollower([source], checkpoint, dry_run=True) as follower:
        follower.poll_once(lambda event: True)
    with (pytest.raises(SinkError, match="does not match inputs or publication mode"),
          relay.JsonlFollower([source], checkpoint, dry_run=False)):
        pytest.fail("Dry run was reused as live delivery")


@pytest.mark.parametrize("content", [b"invalid\n", b"\xff\n", b"x" * (1024 * 1024 + 1)])
def test_given_invalid_live_record_when_followed_then_fail_without_acknowledging(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "events.jsonl"
    source.write_bytes(content)
    checkpoint = tmp_path / "delivery.json"
    with relay.JsonlFollower([source], checkpoint, dry_run=False) as follower, pytest.raises(SinkError):
        follower.poll_once(lambda event: pytest.fail("Unexpected publication"))
    assert not checkpoint.exists()


def test_given_multiple_inputs_when_one_is_partial_then_other_input_progresses(tmp_path: Path) -> None:
    first, second = tmp_path / "first.jsonl", tmp_path / "second.jsonl"
    events = relay.generate_scenario_events()[:2]
    first.write_text(json.dumps(events[0]))
    second.write_text(json.dumps(events[1]) + "\n")
    published = []
    with relay.JsonlFollower([first, second], tmp_path / "state.json", dry_run=False) as follower:
        assert follower.poll_once(published.append) == 1
    assert published == events[1:]


def test_given_follow_cli_when_new_events_arrive_then_publish_until_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, checkpoint, audit = (tmp_path / name for name in ("events.jsonl", "state.json", "audit.jsonl"))
    event = relay.generate_scenario_events()[0]
    polls = []

    def append_then_interrupt(seconds):
        polls.append(seconds)
        if len(polls) == 1:
            source.write_text(json.dumps(event) + "\n")
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(relay.time, "sleep", append_then_interrupt)
    result = relay.main(["--input", str(source), "--follow", "--checkpoint", str(checkpoint),
                         "--dry-run", "--output", str(audit)])

    assert result == 130
    assert json.loads(audit.read_text()) == event
    assert json.loads(checkpoint.read_text())["positions"][str(source)]["offset"] == source.stat().st_size


@pytest.mark.parametrize("failure", ["transient", "permanent", "exhausted"])
def test_given_follow_failure_when_publishing_then_retry_only_unavailability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    source, checkpoint = tmp_path / "events.jsonl", tmp_path / "state.json"
    event = relay.generate_scenario_events()[0]
    source.write_text(json.dumps(event) + "\n")
    attempts, delays = [], []

    def publish(_self, record):
        attempts.append(record)
        if failure == "permanent":
            raise SinkError("invalid input")
        if failure == "exhausted" or len(attempts) <= 2:
            raise SinkUnavailableError("offline")
        return True

    def pause(seconds):
        delays.append(seconds)
        if seconds == 0.25:
            raise KeyboardInterrupt

    monkeypatch.setattr(relay.FabricEventstreamSink, "publish", publish)
    monkeypatch.setattr(relay.time, "sleep", pause)

    result = relay.main(["--input", str(source), "--follow", "--checkpoint", str(checkpoint)])

    if failure == "transient":
        assert result == 130
        assert attempts == [event] * 3
        assert delays == [1, 2, 0.25]
        assert json.loads(checkpoint.read_text())["positions"][str(source)]["offset"] == source.stat().st_size
    else:
        assert result == 1
        assert attempts == [event] * (1 if failure == "permanent" else 6)
        assert delays == ([] if failure == "permanent" else [1, 2, 4, 8, 16])
        assert not checkpoint.exists()


@pytest.mark.parametrize("arguments", [
    ["--demo", "--follow"], ["--input", "events", "--follow"],
    ["--demo", "--checkpoint", "state"], ["--demo", "--poll-interval", "nan"],
    ["--demo", "--poll-interval", "0"],
])
def test_given_invalid_follow_options_when_parsed_then_reject(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        relay.main(arguments)


@pytest.mark.parametrize("collision", ["input", "audit", "lock", "temporary"])
def test_given_follow_path_collision_when_started_then_leave_files_unchanged(tmp_path: Path, collision: str) -> None:
    source, state, audit = (tmp_path / name for name in ("events.jsonl", "state.json", "audit.jsonl"))
    if collision == "input":
        state = source
    elif collision == "audit":
        audit = state
    elif collision == "lock":
        source = state.with_suffix(".json.lock")
    else:
        source = state.with_suffix(".json.tmp")
    source.write_text("unchanged\n")

    with pytest.raises(SystemExit):
        relay.main(["--input", str(source), "--follow", "--checkpoint", str(state), "--output", str(audit)])
    assert source.read_text() == "unchanged\n"


def test_given_secret_file_when_live_sink_created_then_load_without_environment_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = tmp_path / "connection"
    secret.write_text("test-only-secret\n")
    monkeypatch.setenv("FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE", str(secret))

    sink = relay.FabricEventstreamSink()

    assert sink.connection_string == "test-only-secret"


def test_given_unreadable_secret_when_live_sink_created_then_fail_without_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FABRIC_EVENTSTREAM_CONNECTION_STRING_FILE", str(tmp_path / "private-secret"))
    with pytest.raises(SinkError, match="secret file") as failure:
        relay.FabricEventstreamSink()
    assert "private-secret" not in str(failure.value)

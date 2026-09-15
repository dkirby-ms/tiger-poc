"""Deterministic rule semantics and fail-closed configuration tests."""

from copy import deepcopy
from datetime import UTC, datetime
from http.client import BadStatusLine

import pytest

from brain import Config, ZoneRules, poll_once


def envelope(sequence=1, present=True, session="a" * 32, age=0):
    stamp = datetime.now(UTC).isoformat()
    detections = [{
        "classId": 0, "label": "person", "confidence": 0.9,
        "boundingBox": {"xMin": 10, "yMin": 10, "xMax": 90, "yMax": 90},
    }] if present else []
    return {
        "schemaVersion": "1.0", "available": True, "ageSeconds": age,
        "observation": {
            "schemaVersion": "1.0", "cameraId": "camera-01", "sessionId": session,
            "frameNumber": sequence, "frameId": f"camera-01/{session}/{sequence}",
            "capturedAt": stamp, "processedAt": stamp, "timestamp": stamp,
            "frame": {"width": 100, "height": 100}, "detections": detections,
        },
    }


def states(events):
    return [event["state"] for event in events]


def test_given_repeated_polls_when_entering_and_exiting_then_only_distinct_frames_count():
    # Arrange
    rules = ZoneRules(Config(), clock=lambda: 0)
    rules.unavailable("starting")

    # Act / Assert
    assert rules.consume(envelope()) == []
    assert rules.consume(envelope()) == []
    assert states(rules.consume(envelope(2))) == ["occupied"]
    assert rules.consume(envelope(2)) == []
    assert rules.consume(envelope(3, False)) == []
    assert rules.consume(envelope(4, False)) == []
    assert states(rules.consume(envelope(5, False))) == ["clear"]
    assert rules.consume(envelope(6, False)) == []


def test_given_stale_duplicate_when_polling_then_deadline_never_refreshes():
    # Arrange
    now = [0]
    rules = ZoneRules(Config(enter_frames=1), clock=lambda: now[0])
    rules.consume(envelope())
    now[0] = 4
    rules.consume(envelope())

    # Act / Assert
    now[0] = 5
    assert states(rules.consume(envelope())) == ["unknown"]
    assert rules.consume(envelope()) == []
    assert states(rules.consume(envelope(2))) == ["occupied"]


def test_given_transport_failure_when_recovering_then_duplicate_cannot_restore_presence():
    # Arrange
    rules = ZoneRules(Config(), clock=lambda: 0)
    rules.consume(envelope())
    rules.consume(envelope(2))

    class FailingClient:
        def latest(self):
            raise OSError("not logged")

    # Act / Assert
    assert states(poll_once(FailingClient(), rules)) == ["unknown"]
    assert rules.consume(envelope(2)) == []
    assert rules.consume(envelope(3)) == []
    assert states(rules.consume(envelope(4))) == ["occupied"]


@pytest.mark.parametrize("error", [BadStatusLine("invalid"), ValueError("oversized")])
def test_given_invalid_transport_when_polled_then_unknown_not_crash(error):
    # Arrange
    rules = ZoneRules(Config())

    class FailingClient:
        def latest(self):
            raise error

    # Act / Assert
    assert states(poll_once(FailingClient(), rules)) == ["unknown"]


def test_given_restart_when_sequence_restarts_then_unknown_and_confirmation_reset():
    # Arrange
    rules = ZoneRules(Config(), clock=lambda: 0)
    rules.consume(envelope(10))
    rules.consume(envelope(11))

    # Act / Assert
    assert states(rules.consume(envelope(1, session="b" * 32))) == ["unknown"]
    assert states(rules.consume(envelope(2, session="b" * 32))) == ["occupied"]
    assert states(rules.consume(envelope(12))) == ["unknown"]
    assert rules.session == "b" * 32


def test_given_dwell_when_evidence_arrives_then_capture_age_controls_confirmation():
    # Arrange
    now = [0]
    rules = ZoneRules(Config(dwell_seconds=2), clock=lambda: now[0])
    rules.consume(envelope())
    now[0] = 2

    # Act / Assert
    assert rules.consume(envelope(2, age=1)) == []
    now[0] = 3
    assert states(rules.consume(envelope(3, age=1))) == ["occupied"]


def test_given_gap_when_next_fresh_frame_arrives_then_old_confirmation_is_reset():
    # Arrange
    now = [0]
    rules = ZoneRules(Config(), clock=lambda: now[0])
    rules.consume(envelope())
    now[0] = 6

    # Act / Assert
    assert states(rules.consume(envelope(2))) == ["unknown"]
    assert states(rules.consume(envelope(3))) == ["occupied"]


@pytest.mark.parametrize("change", [
    lambda e: e.update(available=False),
    lambda e: e.update(ageSeconds=float("nan")),
    lambda e: e.update(ageSeconds=10**400),
    lambda e: e.update(ageSeconds=6),
    lambda e: e["observation"].update(detections=None),
    lambda e: e["observation"].update(schemaVersion="2.0"),
    lambda e: e["observation"].update(cameraId="wrong"),
    lambda e: e["observation"].update(frameId="wrong"),
    lambda e: e["observation"].update(capturedAt="not-date"),
    lambda e: e["observation"]["frame"].update(width=0),
    lambda e: e["observation"]["detections"][0].update(confidence=float("inf")),
    lambda e: e["observation"]["detections"][0]["boundingBox"].update(xMin=-1),
])
def test_given_invalid_or_unavailable_evidence_when_consumed_then_not_clear(change):
    # Arrange
    rules = ZoneRules(Config(enter_frames=1), clock=lambda: 0)
    rules.consume(envelope())
    bad = deepcopy(envelope(2))
    change(bad)

    # Act / Assert
    assert states(rules.consume(bad)) == ["unknown"]


@pytest.mark.parametrize("kwargs", [
    {"zone": (1, 0, 0, 1)}, {"zone": (0, 0, float("nan"), 1)},
    {"confidence": float("inf")}, {"enter_frames": 0}, {"exit_frames": True},
    {"dwell_seconds": -1}, {"stale_seconds": 0}, {"poll_seconds": 10},
    {"vision_url": "http://user:password@vision"}, {"vision_url": "http://vision/path"},
    {"camera": "not/valid"},
])
def test_given_invalid_config_when_constructed_then_rejected(kwargs):
    # Act / Assert
    with pytest.raises(ValueError):
        Config(**kwargs)


@pytest.mark.parametrize(("zone", "confidence"), [
    ((0, 0, 0.2, 0.2), 0.5), ((0, 0, 1, 1), 0.95),
])
def test_given_person_outside_zone_or_below_threshold_when_confirmed_then_clear(zone, confidence):
    # Arrange
    rules = ZoneRules(Config(zone=zone, confidence=confidence, exit_frames=1), clock=lambda: 0)

    # Act / Assert
    assert states(rules.consume(envelope())) == ["clear"]

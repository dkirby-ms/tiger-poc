"""Tests for the non-secret Fabric prerequisite gate."""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from scripts import check_fabric_prerequisites as prerequisites


@pytest.fixture()
def passing_environment() -> dict[str, str]:
    """Return a complete set of non-secret prerequisite declarations."""
    return {
        "FABRIC_WORKSPACE_ID": "workspace-id",
        "FABRIC_REGION": "West US 2",
        "FABRIC_CAPACITY_OR_TRIAL": "capacity-id",
        "FABRIC_CONTRIBUTOR_ACCESS": "true",
        "FABRIC_DIGITAL_TWIN_BUILDER_ENABLED": "true",
        "FABRIC_SPARK_AUTOSCALE_BILLING_COMPATIBLE": "true",
        "FABRIC_AUTH_MODE": "entra",
        "FABRIC_EVENTSTREAM_HOSTNAME": "example.servicebus.windows.net",
        "FABRIC_PRIVATE_NETWORK_POLICY": "private",
        "FABRIC_TLS_VERIFY": "true",
        "FABRIC_PREVIEW_APPROVED": "true",
    }


def test_given_missing_setting_when_checked_then_returns_configuration_exit(
    passing_environment: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    del passing_environment["FABRIC_REGION"]

    # Act
    exit_code = prerequisites.run([], environ=passing_environment)

    # Assert
    assert exit_code == prerequisites.EXIT_CONFIGURATION
    assert "MISSING: FABRIC_REGION" in capsys.readouterr().out


def test_given_denied_gate_when_checked_then_returns_blocked_exit(
    passing_environment: dict[str, str],
) -> None:
    # Arrange
    passing_environment["FABRIC_PREVIEW_APPROVED"] = "false"

    # Act
    exit_code = prerequisites.run([], environ=passing_environment)

    # Assert
    assert exit_code == prerequisites.EXIT_BLOCKED


def test_given_secret_values_when_checked_then_output_is_redacted(
    passing_environment: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    secret = "Endpoint=sb://example/;SharedAccessKey=do-not-print"
    passing_environment["FABRIC_EVENTSTREAM_CONNECTION_STRING"] = secret

    # Act
    prerequisites.run([], environ=passing_environment)

    # Assert
    assert secret not in capsys.readouterr().out


def test_given_tls_probe_when_certificate_verifies_then_returns_success(
    passing_environment: dict[str, str], mocker: MockerFixture
) -> None:
    # Arrange
    probe = mocker.patch.object(prerequisites, "_probe_tls")

    # Act
    exit_code = prerequisites.run(["--probe-tls"], environ=passing_environment)

    # Assert
    assert exit_code == prerequisites.EXIT_SUCCESS
    probe.assert_called_once_with("example.servicebus.windows.net", 5.0)


def test_given_tls_probe_failure_when_checked_then_returns_connectivity_exit(
    passing_environment: dict[str, str], mocker: MockerFixture
) -> None:
    # Arrange
    mocker.patch.object(prerequisites, "_probe_tls", side_effect=OSError("unreachable"))

    # Act
    exit_code = prerequisites.run(["--probe-tls"], environ=passing_environment)

    # Assert
    assert exit_code == prerequisites.EXIT_CONNECTIVITY


@pytest.fixture(autouse=True)
def _no_environment_leak(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for setting in (*prerequisites.REQUIRED_TEXT_SETTINGS, *prerequisites.REQUIRED_TRUE_SETTINGS):
        monkeypatch.delenv(setting, raising=False)
    yield

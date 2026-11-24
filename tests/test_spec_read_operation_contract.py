"""The legacy and canonical read commands share one machine-readable error contract."""

import json

from click.testing import CliRunner

from atlawire.cli import cli


def _envelope(result):
    assert result.stdout
    document = json.loads(result.stdout)
    assert document["ok"] is False
    return document["error"]


def test_read_operation_unknown_id_prints_the_json_envelope():
    result = CliRunner().invoke(
        cli,
        ["read-operation", "unknown.id", "--params", "{}", "--token-from-env"],
    )

    assert result.exit_code == 2
    assert _envelope(result)["code"] == "validation_error"


def test_read_operation_malformed_params_prints_the_json_envelope():
    result = CliRunner().invoke(
        cli,
        [
            "read-operation",
            "jira.project.get",
            "--params",
            "not-json",
            "--token-from-env",
        ],
    )

    assert result.exit_code == 2
    assert _envelope(result)["code"] == "validation_error"


def test_read_operation_missing_credentials_print_the_json_envelope(monkeypatch):
    monkeypatch.delenv("ATLAWIRE_JIRA_URL", raising=False)
    monkeypatch.delenv("ATLAWIRE_JIRA_TOKEN", raising=False)

    result = CliRunner().invoke(
        cli,
        [
            "read-operation",
            "jira.project.get",
            "--params",
            '{"projectIdOrKey": "DEMO"}',
            "--token-from-env",
        ],
    )

    assert result.exit_code == 2
    assert _envelope(result)["code"] == "credentials_error"


def test_read_and_read_operation_agree_on_a_validation_failure():
    argv = ["unknown.id", "--params", "{}", "--token-from-env"]
    canonical = CliRunner().invoke(cli, ["read", *argv])
    legacy = CliRunner().invoke(cli, ["read-operation", *argv])

    assert canonical.exit_code == legacy.exit_code == 2
    assert _envelope(canonical)["code"] == _envelope(legacy)["code"]

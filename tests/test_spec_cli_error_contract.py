"""One error envelope, used by every command that prints one.

`_error_envelope` documents itself as "the one machine-readable error envelope",
and `read` promises a single JSON error for validation, configuration and
response failures. A handler that rebuilds the object by hand drifts: a missing
key breaks a consumer that keys on the canonical shape, and a local write failure
reported as a caller mistake sends an agent to fix the wrong thing.
"""

import json

from click.testing import CliRunner

from atlawire.cli import cli

TOKEN = "synthetic-envelope-token"
CANONICAL_KEYS = {
    "status",
    "code",
    "classification",
    "message",
    "path",
    "content_type",
    "body",
    "body_json",
    "body_truncated",
}


def _invoke(argv, base):
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={"ATLAWIRE_JIRA_URL": base, "ATLAWIRE_JIRA_TOKEN": TOKEN},
    )


def test_api_get_prints_the_canonical_envelope():
    result = _invoke(
        ["api-get", "jira", "/rest/api/2/admin/probe"], "https://example.invalid"
    )

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert set(document["error"]) == CANONICAL_KEYS


def test_api_request_prints_the_canonical_envelope():
    result = _invoke(
        ["api-request", "jira", "GET", "/rest/api/2/admin/probe"],
        "https://example.invalid",
    )

    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert set(document["error"]) == CANONICAL_KEYS


def test_a_local_write_failure_is_not_reported_as_a_caller_mistake(tmp_path):
    """An unwritable destination is an environment failure, not a bad argument."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    destination = str(blocker / "out.bin")

    result = _invoke(
        [
            "read",
            "jira.attachment.content",
            "--params",
            '{"id": "1"}',
            "--out",
            destination,
        ],
        "https://example.invalid",
    )

    document = json.loads(result.stdout)
    assert document["ok"] is False
    assert document["error"]["code"] == "read_error"
    assert result.exit_code == 1


def test_a_registry_validation_failure_stays_a_validation_error():
    result = _invoke(
        ["read", "jira.issue.issueidorkey", "--params", '{"wrong": "x"}'],
        "https://example.invalid",
    )

    document = json.loads(result.stdout)
    assert document["error"]["code"] == "validation_error"
    assert result.exit_code == 2

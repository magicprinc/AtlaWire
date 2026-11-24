"""End-to-end checks that both read commands answer with the same JSON envelope."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(argv):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("ATLAWIRE_JIRA_URL", None)
    env.pop("ATLAWIRE_JIRA_TOKEN", None)
    return subprocess.run(
        [sys.executable, "-B", "-m", "atlawire", *argv],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def _envelope(result):
    assert result.stdout, result.stderr
    document = json.loads(result.stdout)
    assert document["ok"] is False
    return document["error"]


def test_read_operation_unknown_id_is_a_json_usage_error():
    result = _run(
        ["read-operation", "unknown.id", "--params", "{}", "--token-from-env"]
    )

    assert result.returncode == 2
    assert _envelope(result)["code"] == "validation_error"
    assert "Traceback" not in result.stderr


def test_read_operation_and_read_share_the_envelope_contract():
    argv = [
        "unknown.id",
        "--params",
        "{}",
        "--token-from-env",
    ]
    legacy = _run(["read-operation", *argv])
    canonical = _run(["read", *argv])

    assert legacy.returncode == canonical.returncode == 2
    assert _envelope(legacy)["code"] == _envelope(canonical)["code"]

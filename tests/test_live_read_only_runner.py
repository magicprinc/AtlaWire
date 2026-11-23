"""Offline contract tests for the opt-in live read-only runner.

No test reads the real process environment or makes a product request. All
AtlaWire settings are synthetic, and the subprocess boundary is either injected
or exercised only on paths that cannot start a check.
"""

import hashlib
import importlib.util
import json
import os
import site
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "checks" / "live_read_only.py"

JIRA_URL = "https://jira.synthetic.invalid/jira"
CONFLUENCE_URL = "https://confluence.synthetic.invalid/wiki"
BITBUCKET_URL = "https://bitbucket.synthetic.invalid/scm"
SENTINEL = "SYNTHETIC-SECRET-SENTINEL"
JIRA_TOKEN = f"jira-{SENTINEL}"
CONFLUENCE_TOKEN = f"confluence-{SENTINEL}"
BITBUCKET_TOKEN = f"bitbucket-{SENTINEL}"

JQL = 'project = DEMO AND text ~ "Widget" ORDER BY updated DESC'
ISSUE = "DEMO-42"
COMMENT_ID = "101"
CQL = 'space = DEMO AND text ~ "Widget"'
PAGE_ID = "555"
MARKER = "SYNTHETIC-LIVE-MARKER"
REPO = "DEMO/widgets"
SEARCH_QUERY = "WidgetService"
SEARCH_PATH = "src/main/java/demo/WidgetService.java"
PR_ID = 7
PR_PATH = "src/main/java/demo/WidgetService.java"
FILE_PATH = "src/main/java/demo/WidgetService.java"
REF = "0123456789abcdef0123456789abcdef01234567"
FILE_BODY = b"package demo;\n\nfinal class WidgetService {}\n"
FILE_SHA = hashlib.sha256(FILE_BODY).hexdigest()


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("atlawire_live_read_only", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = cast(Any, _load_runner())


def synthetic_environment() -> dict[str, str]:
    """Return every required setting plus ordinary, non-secret OS settings."""
    return {
        "PATH": "synthetic-path",
        "LANG": "C",
        "APPDATA": "synthetic-appdata",
        "PYTHONPATH": "synthetic-shadow-path",
        "PYTHONUSERBASE": "synthetic-shadow-base",
        "PYTHONINSPECT": "1",
        "AWS_SECRET_ACCESS_KEY": SENTINEL,
        "ATLAWIRE_JIRA_URL": JIRA_URL,
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": CONFLUENCE_URL,
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "ATLAWIRE_BITBUCKET_URL": BITBUCKET_URL,
        "ATLAWIRE_BITBUCKET_TOKEN": BITBUCKET_TOKEN,
        "ATLAWIRE_LIVE_JIRA_JQL": JQL,
        "ATLAWIRE_LIVE_JIRA_ISSUE": ISSUE,
        "ATLAWIRE_LIVE_JIRA_COMMENT_ID": COMMENT_ID,
        "ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID": PAGE_ID,
        "ATLAWIRE_LIVE_CONFLUENCE_CQL": CQL,
        "ATLAWIRE_LIVE_CONFLUENCE_MARKER": MARKER,
        "ATLAWIRE_LIVE_BITBUCKET_REPO": REPO,
        "ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY": SEARCH_QUERY,
        "ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH": SEARCH_PATH,
        "ATLAWIRE_LIVE_BITBUCKET_PR_ID": str(PR_ID),
        "ATLAWIRE_LIVE_BITBUCKET_PR_PATH": PR_PATH,
        "ATLAWIRE_LIVE_BITBUCKET_FILE_PATH": FILE_PATH,
        "ATLAWIRE_LIVE_BITBUCKET_FILE_REF": REF,
        "ATLAWIRE_LIVE_BITBUCKET_FILE_SHA256": FILE_SHA,
    }


def default_output(key: str) -> bytes:
    payloads: dict[str, object] = {
        "jql": [{"key": "OTHER-9"}, {"key": ISSUE}],
        "issue": {"key": ISSUE, "fields": {"summary": "Synthetic"}},
        "issue-comments": [{"id": COMMENT_ID, "body": "Synthetic"}],
        "cql": [{"id": PAGE_ID, "title": "Synthetic"}],
        "page": {
            "id": PAGE_ID,
            "body": {"storage": {"value": f"<p>{MARKER}</p>"}},
        },
        "search": [
            {
                "project": "DEMO",
                "repository": "widgets",
                "file": SEARCH_PATH,
                "hitCount": 1,
                "matchEvidence": "highlight",
                "hits": [{"line": 3, "text": SEARCH_QUERY}],
                "context": [],
            }
        ],
        "pr:show": {"id": PR_ID, "title": "Synthetic", "state": "OPEN"},
        "pr:files": [{"path": PR_PATH, "type": "MODIFY", "node": "abc1234"}],
        "file": FILE_BODY,
    }
    value = payloads[key]
    if isinstance(value, bytes):
        return value
    return json.dumps(value).encode()


def command_key(argv: list[str]) -> str:
    prefix = len(live.CLI_PREFIX)
    command = argv[prefix]
    if command == "pr":
        return f"pr:{argv[prefix + 3]}"
    return command


class Recorder:
    """Capture the injected subprocess calls and return synthetic bytes."""

    def __init__(
        self,
        *,
        overrides: dict[str, bytes] | None = None,
        returncode: int = 0,
        stderr: bytes = b"",
        error: BaseException | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.overrides = dict(overrides or {})
        self.returncode = returncode
        self.stderr = stderr
        self.error = error

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(argv), dict(kwargs)))
        if self.error is not None:
            raise self.error
        key = command_key(argv)
        output = self.overrides.get(key, default_output(key))
        return subprocess.CompletedProcess(argv, self.returncode, output, self.stderr)


def run_runner(
    environ: dict[str, str],
    *,
    argv: list[str] | None = None,
    recorder: Recorder | None = None,
) -> tuple[int, str, str, Recorder]:
    recording = recorder or Recorder()
    out = StringIO()
    err = StringIO()
    code = live.main(
        ["--live"] if argv is None else argv,
        environ=environ,
        runner=recording,
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue(), recording


def forbidden_calls() -> Recorder:
    return Recorder(error=AssertionError("no subprocess was authorized"))


def test_without_live_flag_runs_nothing() -> None:
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(synthetic_environment(), argv=[], recorder=recorder)

    assert code == 2
    assert "opt-in" in err
    assert out == ""
    assert recorder.calls == []
    assert SENTINEL not in out + err


def test_help_is_static_and_starts_nothing() -> None:
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(
        synthetic_environment(), argv=["--help"], recorder=recorder
    )

    assert code == 0
    assert "Usage:" in out
    assert "docs/AGENT-QUICKSTART.md" in out
    assert err == ""
    assert recorder.calls == []


def test_missing_configuration_names_labels_and_runs_nothing() -> None:
    recorder = forbidden_calls()

    code, out, err, _ = run_runner({}, recorder=recorder)

    assert code == 2
    assert out == ""
    assert "missing: ATLAWIRE_JIRA_URL" in err
    assert "missing: ATLAWIRE_LIVE_BITBUCKET_FILE_SHA256" in err
    assert "missing: ATLAWIRE_LIVE_JIRA_JQL" in err
    assert "ATLAWIRE_LIVE_CONFLUENCE_MARKER" not in err
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATLAWIRE_LIVE_JIRA_JQL", "--all"),
        ("ATLAWIRE_LIVE_CONFLUENCE_CQL", "-x"),
        ("ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY", "--all"),
        ("ATLAWIRE_LIVE_BITBUCKET_FILE_PATH", "-x.java"),
    ],
)
def test_option_like_fixture_values_are_rejected(name: str, value: str) -> None:
    environ = synthetic_environment()
    environ[name] = value
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(environ, recorder=recorder)

    assert code == 2
    assert f"invalid: {name}" in err
    assert value not in out + err
    assert recorder.calls == []


def test_invalid_url_value_is_never_echoed() -> None:
    environ = synthetic_environment()
    environ["ATLAWIRE_JIRA_URL"] = f"http://{SENTINEL}.invalid"
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(environ, recorder=recorder)

    assert code == 2
    assert "invalid: ATLAWIRE_JIRA_URL" in err
    assert SENTINEL not in out + err
    assert recorder.calls == []


def test_cli_prefix_uses_safe_installed_module_invocation() -> None:
    assert live.CLI_PREFIX[0] == sys.executable
    assert "-P" in live.CLI_PREFIX
    assert "-B" in live.CLI_PREFIX
    assert "-I" not in live.CLI_PREFIX


def test_plan_uses_fixed_cli_command_scheme() -> None:
    code, out, err, recorder = run_runner(synthetic_environment())

    assert code == 0
    assert err == ""
    assert len(recorder.calls) == 9
    assert "live-read-only: PASS (9 checks)" in out
    assert "jira.discovery: ok" in out
    assert "bitbucket.indexed_search: ok" in out

    expected_commands = (
        ("jql", JQL, "--json", "--limit", "10", "--token-from-env"),
        ("issue", ISSUE, "--token-from-env"),
        (
            "issue-comments",
            ISSUE,
            "--max-pages",
            "1",
            "--token-from-env",
        ),
        ("cql", CQL, "--json", "--limit", "10", "--token-from-env"),
        ("page", PAGE_ID, "--token-from-env"),
        (
            "search",
            SEARCH_QUERY,
            "--repo",
            REPO,
            "--limit",
            "10",
            "--json",
            "--token-from-env",
        ),
        ("pr", REPO, str(PR_ID), "show", "--token-from-env"),
        ("pr", REPO, str(PR_ID), "files", "--json", "--token-from-env"),
        (
            "file",
            REPO,
            FILE_PATH,
            "--at",
            REF,
            "--token-from-env",
        ),
    )
    for (argv, kwargs), command in zip(recorder.calls, expected_commands, strict=True):
        assert tuple(argv[: len(live.CLI_PREFIX)]) == live.CLI_PREFIX
        assert tuple(argv[len(live.CLI_PREFIX) :]) == command
        assert command[0] in live.READ_COMMANDS
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] == 30
        assert kwargs["shell"] is False
        assert kwargs["stdin"] == subprocess.DEVNULL


def test_plan_isolates_product_credentials() -> None:
    code, _, err, recorder = run_runner(synthetic_environment())

    assert code == 0
    assert err == ""
    expected_prefixes = (
        ["ATLAWIRE_JIRA"] * 3 + ["ATLAWIRE_CONFLUENCE"] * 2 + ["ATLAWIRE_BITBUCKET"] * 4
    )
    secrets = (
        JIRA_URL,
        CONFLUENCE_URL,
        BITBUCKET_URL,
        JIRA_TOKEN,
        CONFLUENCE_TOKEN,
        BITBUCKET_TOKEN,
    )
    for (argv, kwargs), env_prefix in zip(
        recorder.calls, expected_prefixes, strict=True
    ):
        joined = " ".join(argv)
        assert all(secret not in joined for secret in secrets)
        environment = cast(dict[str, str], kwargs["env"])
        atlawire_keys = sorted(
            key for key in environment if key.startswith("ATLAWIRE_")
        )
        assert atlawire_keys == sorted({f"{env_prefix}_URL", f"{env_prefix}_TOKEN"})
        assert environment["PATH"] == "synthetic-path"
        assert environment["LANG"] == "C"
        assert environment["APPDATA"] == "synthetic-appdata"
        for excluded in (
            "PYTHONPATH",
            "PYTHONUSERBASE",
            "PYTHONINSPECT",
            "AWS_SECRET_ACCESS_KEY",
        ):
            assert excluded not in environment


def test_successful_output_contains_only_fixed_labels() -> None:
    code, out, err, _ = run_runner(synthetic_environment())

    assert code == 0
    combined = out + err
    for value in (
        JIRA_URL,
        CONFLUENCE_URL,
        BITBUCKET_URL,
        JIRA_TOKEN,
        CONFLUENCE_TOKEN,
        BITBUCKET_TOKEN,
        JQL,
        CQL,
        SEARCH_QUERY,
        ISSUE,
        PAGE_ID,
        REPO,
        SEARCH_PATH,
        PR_PATH,
        REF,
    ):
        assert value not in combined


@pytest.mark.parametrize(
    ("override", "check_name"),
    [
        ({"jql": b"[]"}, "jira.discovery"),
        ({"cql": b"[]"}, "confluence.search_page"),
        ({"search": b"[]"}, "bitbucket.indexed_search"),
    ],
)
def test_empty_discovery_result_is_not_a_pass(
    override: dict[str, bytes], check_name: str
) -> None:
    code, out, err, _ = run_runner(
        synthetic_environment(), recorder=Recorder(overrides=override)
    )

    assert code == 1
    assert f"{check_name}: FAIL oracle_mismatch" in out
    assert "live-read-only: FAIL" in out
    assert "live-read-only: PASS" not in out
    assert err == ""


def test_jira_discovery_requires_the_known_key() -> None:
    recorder = Recorder(overrides={"jql": b'[{"key": "OTHER-1"}]'})

    code, out, _, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL oracle_mismatch" in out
    assert "OTHER-1" not in out
    assert SENTINEL not in out


def test_indexed_search_rejects_context_only_evidence() -> None:
    context_only = (
        b'[{"project": "DEMO", "repository": "widgets", '
        b'"file": "src/main/java/demo/WidgetService.java", '
        b'"hitCount": 1, "matchEvidence": "context-only", '
        b'"hits": [], "context": [[{"line": 3, "text": "WidgetService"}]]}]'
    )
    recorder = Recorder(overrides={"search": context_only})

    code, out, _, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "bitbucket.indexed_search: FAIL oracle_mismatch" in out
    assert "WidgetService" not in out


def test_configured_confluence_marker_must_appear() -> None:
    page = b'{"id": "555", "body": {"storage": {"value": "<p>other</p>"}}}'
    recorder = Recorder(overrides={"page": page})

    code, out, _, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "confluence.page: FAIL oracle_mismatch" in out
    assert MARKER not in out


def test_unhashable_match_evidence_is_invalid_output() -> None:
    evidence = (
        b'[{"project": "DEMO", "repository": "widgets", '
        b'"file": "src/main/java/demo/WidgetService.java", '
        b'"matchEvidence": [], "hits": []}]'
    )
    recorder = Recorder(overrides={"search": evidence})

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "bitbucket.indexed_search: FAIL invalid_output" in out
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    ("case", "value", "check"),
    [
        ("issue-comments", [{"id": 101, "body": "Synthetic"}], "jira.comments"),
        ("issue-comments", [{"id": COMMENT_ID}], "jira.comments"),
        (
            "search",
            [
                {
                    "project": "DEMO",
                    "repository": "widgets",
                    "file": SEARCH_PATH,
                    "matchEvidence": "highlight",
                    "hits": [None],
                }
            ],
            "bitbucket.indexed_search",
        ),
        (
            "search",
            json.loads(default_output("search"))
            + [
                {
                    "project": "OTHER",
                    "repository": "widgets",
                    "file": "Other.java",
                    "matchEvidence": "none",
                    "hits": [],
                }
            ],
            "bitbucket.indexed_search",
        ),
    ],
)
def test_malformed_evidence_cannot_look_like_success(
    case: str, value: object, check: str
) -> None:
    code, out, err, _ = run_runner(
        synthetic_environment(),
        recorder=Recorder(overrides={case: json.dumps(value).encode()}),
    )

    assert code == 1
    assert f"{check}: FAIL invalid_output" in out
    assert "live-read-only: PASS" not in out
    assert err == ""


def test_oversized_json_integer_is_invalid_output() -> None:
    huge = b'[{"key": ' + b"9" * 5000 + b"}]"
    recorder = Recorder(overrides={"jql": huge})

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL invalid_output" in out
    assert "Traceback" not in out + err


def test_deep_json_is_invalid_output() -> None:
    deep = b"[" * 5000 + b"]" * 5000
    recorder = Recorder(overrides={"jql": deep})

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL invalid_output" in out
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATLAWIRE_LIVE_BITBUCKET_PR_ID", "9" * 5000),
        ("ATLAWIRE_LIVE_BITBUCKET_FILE_PATH", "src/main/java/demo/WidgetService.txt"),
        ("ATLAWIRE_LIVE_BITBUCKET_FILE_REF", "main"),
        ("ATLAWIRE_LIVE_BITBUCKET_FILE_REF", "0123456789abcdef0123456789abcdef0123456"),
    ],
)
def test_unbounded_or_unpinned_fixtures_are_rejected(name: str, value: str) -> None:
    environ = synthetic_environment()
    environ[name] = value
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(environ, recorder=recorder)

    assert code == 2
    assert f"invalid: {name}" in err
    assert "Traceback" not in out + err
    assert recorder.calls == []


@pytest.mark.parametrize("value", ["9" * 5000, "٥", "²", "0", "301"])
def test_timeout_rejects_unbounded_or_non_ascii_values(value: str) -> None:
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(
        synthetic_environment(),
        argv=["--live", "--timeout", value],
        recorder=recorder,
    )

    assert code == 2
    assert "invalid arguments" in err
    assert value not in out + err
    assert recorder.calls == []


def test_successful_cli_with_wrong_identity_fails() -> None:
    recorder = Recorder(
        overrides={"pr:show": b'{"id": 987654, "title": "Synthetic", "state": "OPEN"}'}
    )

    code, out, _, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "bitbucket.pull_request: FAIL oracle_mismatch" in out
    assert "987654" not in out
    assert "live-read-only: FAIL" in out


def test_cli_failure_hides_stderr_and_stdout() -> None:
    recorder = Recorder(
        returncode=1,
        stderr=f"raw diagnostic {SENTINEL}".encode(),
    )

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL cli_failed" in out
    assert SENTINEL not in out + err
    assert "raw diagnostic" not in out + err


def test_timeout_is_reported_without_exception_text() -> None:
    error = subprocess.TimeoutExpired(
        ["atlawire", SENTINEL],
        30,
        output=f"stdout {SENTINEL}".encode(),
        stderr=f"stderr {SENTINEL}".encode(),
    )
    recorder = Recorder(error=error)

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL timeout" in out
    assert SENTINEL not in out + err
    assert "Traceback" not in out + err


def test_invalid_json_is_reported_without_payload() -> None:
    recorder = Recorder(overrides={"jql": b"\xff" + SENTINEL.encode()})

    code, out, err, _ = run_runner(synthetic_environment(), recorder=recorder)

    assert code == 1
    assert "jira.discovery: FAIL invalid_output" in out
    assert SENTINEL not in out + err


def test_wrong_file_digest_fails_without_printing_the_file() -> None:
    environ = synthetic_environment()
    environ["ATLAWIRE_LIVE_BITBUCKET_FILE_SHA256"] = "0" * 64

    code, out, err, _ = run_runner(environ)

    assert code == 1
    assert "bitbucket.java_file: FAIL oracle_mismatch" in out
    assert "final class WidgetService" not in out + err
    assert FILE_SHA not in out + err


@pytest.mark.parametrize(
    "argv",
    [
        ["--live", f"--{SENTINEL}"],
        ["--live", SENTINEL],
        ["--live", "--timeout", SENTINEL],
        ["--live", f"--timeout={SENTINEL}"],
        [f"--{SENTINEL}"],
    ],
)
def test_secret_bearing_invalid_arguments_are_not_echoed(
    argv: list[str],
) -> None:
    recorder = forbidden_calls()

    code, out, err, _ = run_runner(
        synthetic_environment(), argv=argv, recorder=recorder
    )

    assert code == 2
    assert "invalid arguments" in err
    assert SENTINEL not in out + err
    assert recorder.calls == []


def test_fixed_prefix_runs_installed_cli_outside_checkout(
    tmp_path: Path,
) -> None:
    # Seed only the non-secret user-site location and the Windows runtime
    # variables the child needs to start; no product settings or secrets come
    # from the test process environment.
    environment = {"PYTHONUSERBASE": site.getuserbase(), "PATH": ""}
    for name in ("SYSTEMDRIVE", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    result = subprocess.run(
        [*live.CLI_PREFIX, "--version"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("atlawire, version")
    assert result.stderr == ""


def test_runner_cli_refusal_makes_no_check_run() -> None:
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--live"],
        env={},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 2
    assert "missing: ATLAWIRE_JIRA_URL" in result.stderr
    assert "jira.discovery" not in result.stdout
    assert "Traceback" not in result.stderr


def test_script_help_and_opt_in_paths_need_no_environment() -> None:
    help_result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--help"],
        env={},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert help_result.returncode == 0
    assert "Usage:" in help_result.stdout

    script_environment = synthetic_environment()
    script_environment.pop("PYTHONINSPECT")
    script_environment.pop("PYTHONPATH")
    no_live = subprocess.run(
        [sys.executable, "-B", str(SCRIPT)],
        env=script_environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert no_live.returncode == 2
    assert "opt-in" in no_live.stderr
    assert "jira.discovery" not in no_live.stdout

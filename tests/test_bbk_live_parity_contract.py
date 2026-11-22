"""Offline contract tests for the opt-in BBK/AtlaWire live parity checks.

The live module in ``checks`` is imported by path. Every test supplies a
synthetic environment, a synthetic BBK package root, and fake subprocess
results; no test reads a real credential or fixture, the real
``D:/zcache/bbk`` default, or a product endpoint. One subprocess regression
copies only PATH/SYSTEMROOT/TEMP-style OS settings to run pytest and passes no
credentials. The command-shape tests inspect the real AtlaWire Click group and
its ``--help`` rendering without resolving a URL, a token, or a network call.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import click
import pytest
from click.testing import CliRunner

from atlawire.cli import cli as atlawire_cli

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "checks" / "test_bbk_live_parity.py"

SENTINEL = "SYNTHETIC-BBK-PARITY-SENTINEL"
QUERY = "project = DEMO ORDER BY key ASC"
CQL_QUERY = "space = DEMO AND type = page"
SEARCH_QUERY = "WidgetService"
REPO = "DEMO/widgets"
PATH = "src/main/java/demo/WidgetService.java"
KEY = "DEMO-42"
OTHER_KEY = "DEMO-43"
CONTENT_ID = "123456"
OTHER_CONTENT_ID = "654321"
COMMENT_ID = "10001"
OTHER_COMMENT_ID = "10002"
REF = "0123456789abcdef0123456789abcdef01234567"
SHOWLOCALS_EXPECTED = "SYNTHETIC-SHOWLOCALS-EXPECTED"
SHOWLOCALS_FIXTURE = "SYNTHETIC-SHOWLOCALS-FIXTURE"
SHOWLOCALS_UNEXPECTED = "SYNTHETIC-SHOWLOCALS-UNEXPECTED"
SHOWLOCALS_INCONCLUSIVE = "SYNTHETIC-SHOWLOCALS-INCONCLUSIVE"
SHOWLOCALS_CONTROL = "SYNTHETIC-SHOWLOCALS-CONTROL"
SHOWLOCALS_SECRETS = (
    SHOWLOCALS_EXPECTED,
    SHOWLOCALS_FIXTURE,
    SHOWLOCALS_UNEXPECTED,
    SHOWLOCALS_INCONCLUSIVE,
)


def _load_live() -> ModuleType:
    spec = importlib.util.spec_from_file_location("atlawire_bbk_live_parity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = cast(Any, _load_live())


def synthetic_environment(tmp_path: Path) -> dict[str, str]:
    """Return credential-like sentinels and fixtures for complete isolation."""
    root = tmp_path / "synthetic-bbk-root"
    (root / "bbk").mkdir(parents=True)
    (root / "bbk" / "__main__.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    return {
        "PATH": "synthetic-path",
        "HOME": "synthetic-home",
        "USERPROFILE": "synthetic-profile",
        "APPDATA": "synthetic-appdata",
        "BBK_CREDENTIALS": "synthetic-bbk-credentials.json",
        "HTTP_PROXY": "http://synthetic-proxy.invalid:3128",
        "HTTPS_PROXY": "http://synthetic-proxy.invalid:3128",
        "ATLAWIRE_PARITY_BBK_ROOT": str(root),
        "ATLAWIRE_LIVE_JIRA_JQL": QUERY,
        "ATLAWIRE_LIVE_JIRA_ISSUE": KEY,
        "ATLAWIRE_LIVE_JIRA_COMMENT_ID": COMMENT_ID,
        "ATLAWIRE_LIVE_CONFLUENCE_CQL": CQL_QUERY,
        "ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID": CONTENT_ID,
        "ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY": SEARCH_QUERY,
        "ATLAWIRE_LIVE_BITBUCKET_REPO": REPO,
        "ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH": PATH,
        "ATLAWIRE_LIVE_BITBUCKET_FILE_REF": REF,
        "ATLAWIRE_JIRA_URL": "https://jira.synthetic.invalid",
        "ATLAWIRE_JIRA_TOKEN": SENTINEL,
        "ATLAWIRE_CONFLUENCE_TOKEN": SENTINEL,
        "ATLAWIRE_BITBUCKET_TOKEN": SENTINEL,
        "AWS_SECRET_ACCESS_KEY": SENTINEL,
        "PYTHONPATH": "synthetic-shadow-path",
    }


@pytest.fixture()
def environ(tmp_path: Path) -> dict[str, str]:
    return synthetic_environment(tmp_path)


class Result:
    """One synthetic subprocess outcome."""

    def __init__(
        self,
        *,
        stdout: bytes = b"[]",
        returncode: int = 0,
        stderr: bytes = b"",
        error: BaseException | None = None,
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.error = error


class Recorder:
    """Capture subprocess arguments and return queued synthetic outcomes."""

    def __init__(self, *results: Result) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.results = list(results)

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(argv), dict(kwargs)))
        if not self.results:
            raise AssertionError("unexpected subprocess launch")
        result = self.results.pop(0)
        if result.error is not None:
            raise result.error
        return subprocess.CompletedProcess(
            argv, result.returncode, result.stdout, result.stderr
        )


def json_bytes(value: object) -> bytes:
    return json.dumps(value).encode()


def jql_rows(*keys: str) -> bytes:
    return json_bytes([{"key": key, "summary": SENTINEL} for key in keys])


def cql_rows(*identifiers: object) -> bytes:
    return json_bytes([{"id": value, "title": SENTINEL} for value in identifiers])


def search_rows(*paths: str) -> bytes:
    return json_bytes(
        [
            {
                "project": "DEMO",
                "repository": "widgets",
                "file": path,
                "hitCount": 1,
                "hits": [{"line": 1, "text": SENTINEL}],
            }
            for path in paths
        ]
    )


def author_comment_rows(*pairs: tuple[str, str]) -> bytes:
    return json_bytes(
        [
            {
                "key": key,
                "comment_id": comment_id,
                "summary": SENTINEL,
                "body": SENTINEL,
            }
            for key, comment_id in pairs
        ]
    )


def bbk_grep_text(
    *hits: tuple[str, int], partial: bool = False
) -> bytes:
    header = (
        f"# {len(hits)} hit(s), engine=archive, scanned=1, partial={partial}"
    )
    body = [f"{path}:{line}: {SENTINEL}" for path, line in hits]
    return "\n".join([header, *body]).encode()


def atlawire_grep_json(
    *hits: tuple[str, int], complete: bool = True, truncated: bool = False
) -> bytes:
    return json_bytes(
        {
            "hits": [
                {"file": path, "line": line, "text": SENTINEL} for path, line in hits
            ],
            "complete": complete,
            "truncated": truncated,
        }
    )


def test_jql_identical_ordered_keys_pass(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY, OTHER_KEY)),
        Result(
            stdout=json_bytes(
                [
                    {"key": KEY, "status": "Done", "priority": None},
                    {"key": OTHER_KEY, "status": None, "assignee": "ada"},
                ]
            )
        ),
    )

    live._live_jql(environ, recorder)

    assert len(recorder.calls) == 2


def test_cql_identical_ordered_ids_pass(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=cql_rows(CONTENT_ID, int(OTHER_CONTENT_ID))),
        Result(stdout=cql_rows(int(CONTENT_ID), OTHER_CONTENT_ID)),
    )

    live._live_cql(environ, recorder)

    assert len(recorder.calls) == 2


def test_search_identical_ordered_paths_pass(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=search_rows(PATH)),
        Result(
            stdout=json_bytes(
                [
                    {
                        "project": "DEMO",
                        "repository": "widgets",
                        "file": PATH,
                        "matchEvidence": "none",
                        "context": [],
                    }
                ]
            )
        ),
    )

    live._live_search(environ, recorder)

    assert len(recorder.calls) == 2


def test_jql_ordering_mismatch_fails(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY, OTHER_KEY)),
        Result(stdout=jql_rows(OTHER_KEY, KEY)),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert str(info.value) == "parity_mismatch"
    assert QUERY not in str(info.value)
    assert KEY not in repr(info.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_jql_later_row_mismatch_fails(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY, OTHER_KEY)),
        Result(stdout=jql_rows(KEY, "DEMO-44")),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert OTHER_KEY not in str(info.value)


def test_cql_identifier_mismatch_fails(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=cql_rows(CONTENT_ID)),
        Result(stdout=cql_rows(OTHER_CONTENT_ID)),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_cql(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert CONTENT_ID not in str(info.value)
    assert OTHER_CONTENT_ID not in str(info.value)


def test_search_identifier_mismatch_fails(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=search_rows(PATH)),
        Result(stdout=search_rows("src/main/java/demo/Other.java")),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_search(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert PATH not in str(info.value)


def test_author_comment_identical_sets_pass(environ: dict[str, str]) -> None:
    rows = author_comment_rows(
        (KEY, COMMENT_ID), (OTHER_KEY, OTHER_COMMENT_ID)
    )
    recorder = Recorder(Result(stdout=rows), Result(stdout=rows))

    live._live_author_comments(environ, recorder)

    assert len(recorder.calls) == 2


def test_author_comment_set_mismatch_fails(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(
            stdout=author_comment_rows(
                (KEY, COMMENT_ID), (OTHER_KEY, OTHER_COMMENT_ID)
            )
        ),
        Result(stdout=author_comment_rows((KEY, COMMENT_ID), (OTHER_KEY, "10003"))),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_author_comments(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert COMMENT_ID not in str(info.value)


def test_author_comment_fixture_absent_is_inconclusive(
    environ: dict[str, str],
) -> None:
    rows = author_comment_rows((OTHER_KEY, OTHER_COMMENT_ID))
    recorder = Recorder(Result(stdout=rows), Result(stdout=rows))

    with pytest.raises(live.InconclusiveError) as info:
        live._live_author_comments(environ, recorder)

    assert info.value.reason == "author_comment_fixture_not_in_both"


def test_author_comment_anchor_missing_from_one_tool_is_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=author_comment_rows((KEY, COMMENT_ID))),
        Result(stdout=author_comment_rows((OTHER_KEY, OTHER_COMMENT_ID))),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_author_comments(environ, recorder)

    assert info.value.reason == "author_comment_fixture_not_in_both"


def test_author_comment_empty_results_are_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(Result(stdout=b"[]"), Result(stdout=b"[]"))

    with pytest.raises(live.InconclusiveError) as info:
        live._live_author_comments(environ, recorder)

    assert info.value.reason == "author_comment_fixture_not_in_both"


@pytest.mark.parametrize(
    "raw",
    [
        b'[{"comment_id": "10001"}]',
        b'[{"key": "DEMO-42"}]',
        b'[{"key": "demo-42", "comment_id": "10001"}]',
        b'[{"key": "DEMO-42", "comment_id": "0"}]',
        b'[{"key": "DEMO-42", "comment_id": true}]',
        json_bytes(
            [
                {"key": "DEMO-42", "comment_id": "10001"},
                {"key": "DEMO-42", "comment_id": "10001"},
            ]
        ),
    ],
)
def test_invalid_author_comment_rows_are_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._author_comment_pairs(raw)

    assert info.value.category == "invalid_output"


def test_repo_grep_identical_sets_pass(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10), (PATH, 20))),
        Result(stdout=atlawire_grep_json((PATH, 20), (PATH, 10))),
    )

    live._live_repo_grep(environ, recorder)

    assert len(recorder.calls) == 2


def test_repo_grep_line_mismatch_fails(environ: dict[str, str]) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10))),
        Result(stdout=atlawire_grep_json((PATH, 11))),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert PATH not in str(info.value)


def test_repo_grep_missing_expected_file_is_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text(("src/Other.java", 10))),
        Result(stdout=atlawire_grep_json(("src/Other.java", 10))),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.reason == "grep_fixture_no_hit"


def test_repo_grep_bbk_partial_is_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10), partial=True)),
        Result(stdout=atlawire_grep_json((PATH, 10))),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.reason == "grep_partial"


def test_repo_grep_atlawire_truncated_is_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10))),
        Result(stdout=atlawire_grep_json((PATH, 10), truncated=True)),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.reason == "grep_limit_reached"


def test_repo_grep_atlawire_incomplete_is_inconclusive(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10))),
        Result(stdout=atlawire_grep_json((PATH, 10), complete=False)),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.reason == "grep_partial"


def test_repo_grep_limit_is_inconclusive(environ: dict[str, str]) -> None:
    capped = tuple((PATH, number) for number in range(1, live.GREP_LIMIT + 1))
    recorder = Recorder(
        Result(stdout=bbk_grep_text(*capped)),
        Result(stdout=atlawire_grep_json((PATH, 1))),
    )

    with pytest.raises(live.InconclusiveError) as info:
        live._live_repo_grep(environ, recorder)

    assert info.value.reason == "grep_limit_reached"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"# not a grep header\n",
        b"# 2 hit(s), engine=archive, scanned=1, partial=False\nsrc/A.java:1: x",
        b"# 1 hit(s), engine=archive, scanned=1, partial=False\nnot-a-hit",
        b"# 1 hit(s), engine=archive, scanned=1, partial=False\n/abs/A.java:1: x",
    ],
)
def test_invalid_bbk_grep_output_is_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._bbk_grep_page(raw)

    assert info.value.category == "invalid_output"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"hits": []}',
        b'{"hits": [], "complete": true}',
        b'{"hits": [], "complete": true, "truncated": "no"}',
        b'{"hits": [{"file": "/abs/A.java", "line": 1}], '
        b'"complete": true, "truncated": false}',
        b'{"hits": [{"file": "src/A.java", "line": 0}], '
        b'"complete": true, "truncated": false}',
        json_bytes(
            {
                "hits": [
                    {"file": PATH, "line": 1},
                    {"file": PATH, "line": 1},
                ],
                "complete": True,
                "truncated": False,
            }
        ),
    ],
)
def test_invalid_atlawire_grep_output_is_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._atlawire_grep_page(raw)

    assert info.value.category == "invalid_output"


def test_expected_key_absent_from_agreeing_results_fails(
    environ: dict[str, str],
) -> None:
    agreeing = jql_rows(OTHER_KEY)
    recorder = Recorder(Result(stdout=agreeing), Result(stdout=agreeing))

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert KEY not in str(info.value)


def test_empty_result_is_rejected(environ: dict[str, str]) -> None:
    recorder = Recorder(Result(stdout=b"[]"), Result(stdout=b"[]"))

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "empty_result"


def test_nonzero_exit_reports_only_a_fixed_category(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        Result(
            stdout=SENTINEL.encode(),
            stderr=SENTINEL.encode(),
            returncode=1,
        )
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "tool_failed"
    assert SENTINEL not in str(info.value)
    assert SENTINEL not in repr(info.value)
    assert len(recorder.calls) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_empty_stdout_is_invalid(environ: dict[str, str]) -> None:
    recorder = Recorder(Result(stdout=b""))

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "invalid_output"
    assert SENTINEL not in str(info.value)


def test_timeout_reports_only_a_fixed_category(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        Result(error=subprocess.TimeoutExpired([SENTINEL], live.TIMEOUT_SECONDS))
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "timeout"
    assert SENTINEL not in str(info.value)
    assert SENTINEL not in repr(info.value)
    assert len(recorder.calls) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_launch_failure_reports_only_a_fixed_category(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(Result(error=OSError(f"{SENTINEL} unavailable")))

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "tool_unavailable"
    assert SENTINEL not in str(info.value)
    assert SENTINEL not in repr(info.value)
    assert len(recorder.calls) == 1


def test_atlawire_failure_after_bbk_success_is_sanitized(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY)),
        Result(
            stdout=SENTINEL.encode(),
            stderr=SENTINEL.encode(),
            returncode=1,
        ),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "tool_failed"
    assert SENTINEL not in str(info.value)
    assert SENTINEL not in repr(info.value)
    assert len(recorder.calls) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json",
        b"\xff",
        b"\xef\xbb\xbf[]",
        b"{}",
        b"null",
        b'"text"',
        b"[] trailing",
    ],
)
def test_malformed_json_is_invalid(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._jql_keys(raw)

    assert info.value.category == "invalid_output"
    assert SENTINEL not in str(info.value)


def test_oversized_output_is_rejected_before_decode() -> None:
    raw = b"x" * (live.MAX_OUTPUT_BYTES + 1)

    with pytest.raises(live.ParityError) as info:
        live._jql_keys(raw)

    assert info.value.category == "invalid_output"


def test_rows_beyond_the_fixed_limit_are_invalid() -> None:
    raw = jql_rows(KEY, OTHER_KEY)

    with pytest.raises(live.ParityError) as info:
        live._jql_keys(raw, limit=1)

    assert info.value.category == "invalid_output"


@pytest.mark.parametrize(
    "raw",
    [
        b'[{"key": "demo-42"}]',
        b'[{"key": "--help"}]',
        b'[{"key": 42}]',
        b'[{"summary": "missing key"}]',
        json_bytes([{"key": KEY}, {"key": KEY}]),
    ],
)
def test_invalid_jql_rows_are_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._jql_keys(raw)

    assert info.value.category == "invalid_output"


@pytest.mark.parametrize(
    "raw",
    [
        b'[{"id": 0}]',
        b'[{"id": "0"}]',
        b'[{"id": true}]',
        b'[{"id": null}]',
        b'[{"id": "12 34"}]',
        b'[{"title": "no id"}]',
    ],
)
def test_invalid_cql_rows_are_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._content_ids(raw)

    assert info.value.category == "invalid_output"


@pytest.mark.parametrize(
    "raw",
    [
        b'[{"project": "DEMO", "repository": "widgets"}]',
        b'[{"project": null, "repository": null, "file": "src/A.java"}]',
        b'[{"project": "DEMO", "repository": "..", "file": "src/A.java"}]',
        b'[{"project": "DEMO", "repository": "widgets", "file": "/etc/passwd"}]',
        b'[{"project": "DEMO", "repository": "widgets", "file": "src\\\\A.java"}]',
        b'[{"project": "DEMO", "repository": "widgets", "file": "src/../A.java"}]',
    ],
)
def test_invalid_search_rows_are_rejected(raw: bytes) -> None:
    with pytest.raises(live.ParityError) as info:
        live._search_ids(raw)

    assert info.value.category == "invalid_output"


@pytest.mark.parametrize(
    ("name", "check"),
    [
        pytest.param(live.JQL_QUERY_ENV, live._live_jql, id="jql-query"),
        pytest.param(live.JQL_KEY_ENV, live._live_jql, id="jql-key"),
        pytest.param(
            live.JIRA_COMMENT_ENV,
            live._live_author_comments,
            id="jira-comment",
        ),
        pytest.param(live.CQL_QUERY_ENV, live._live_cql, id="cql-query"),
        pytest.param(live.CQL_ID_ENV, live._live_cql, id="cql-id"),
        pytest.param(live.SEARCH_QUERY_ENV, live._live_search, id="search-query"),
        pytest.param(live.SEARCH_REPO_ENV, live._live_search, id="search-repo"),
        pytest.param(live.SEARCH_PATH_ENV, live._live_search, id="search-path"),
        pytest.param(live.GREP_REF_ENV, live._live_repo_grep, id="grep-ref"),
    ],
)
def test_missing_or_blank_fixture_fails_before_any_subprocess(
    environ: dict[str, str],
    name: str,
    check: Any,
) -> None:
    without = dict(environ)
    without.pop(name)
    recorder = Recorder()

    with pytest.raises(live.FixtureError) as missing:
        check(without, recorder)
    assert missing.value.name == name
    assert recorder.calls == []

    without[name] = ""
    with pytest.raises(live.FixtureError) as blank:
        check(without, recorder)
    assert blank.value.name == name
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("name", "value", "check"),
    [
        pytest.param(live.JQL_QUERY_ENV, "--help", live._live_jql, id="jql-query"),
        pytest.param(live.CQL_QUERY_ENV, "-x", live._live_cql, id="cql-query"),
        pytest.param(
            live.SEARCH_QUERY_ENV, "--all", live._live_search, id="search-query"
        ),
        pytest.param(
            live.SEARCH_REPO_ENV, "DEMO/..", live._live_search, id="search-parent"
        ),
        pytest.param(
            live.SEARCH_REPO_ENV, "DEMO/a/b", live._live_search, id="search-nested"
        ),
        pytest.param(
            live.SEARCH_PATH_ENV,
            "/absolute.java",
            live._live_search,
            id="path-absolute",
        ),
        pytest.param(
            live.SEARCH_PATH_ENV,
            "src\\windows.java",
            live._live_search,
            id="path-backslash",
        ),
        pytest.param(
            live.SEARCH_PATH_ENV,
            "src/main/java/demo/WidgetService.kt",
            live._live_search,
            id="path-non-java",
        ),
        pytest.param(
            live.SEARCH_PATH_ENV,
            "src/*.java",
            live._live_repo_grep,
            id="grep-glob-meta",
        ),
        pytest.param(live.JQL_KEY_ENV, "demo-42", live._live_jql, id="jql-key"),
        pytest.param(live.CQL_ID_ENV, "0", live._live_cql, id="cql-id"),
        pytest.param(
            live.JIRA_COMMENT_ENV,
            "0",
            live._live_author_comments,
            id="jira-comment-id",
        ),
        pytest.param(
            live.GREP_REF_ENV,
            "abc",
            live._live_repo_grep,
            id="grep-ref",
        ),
    ],
)
def test_option_like_or_invalid_fixture_never_starts_subprocess(
    environ: dict[str, str], name: str, value: str, check: Any
) -> None:
    invalid = dict(environ)
    invalid[name] = value
    recorder = Recorder()

    with pytest.raises(live.FixtureError) as info:
        check(invalid, recorder)

    assert info.value.name == name
    assert recorder.calls == []


def test_missing_bbk_root_fails_before_subprocess(
    environ: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "DEFAULT_BBK_ROOT", str(tmp_path / "absent-bbk-root"))
    without = dict(environ)
    without.pop(live.BBK_ROOT_ENV)
    recorder = Recorder()

    with pytest.raises(live.FixtureError) as info:
        live._live_jql(without, recorder)

    assert info.value.name == live.BBK_ROOT_ENV
    assert recorder.calls == []


def test_default_bbk_root_is_used_when_override_is_absent(
    environ: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_root = tmp_path / "default-bbk-root"
    (default_root / "bbk").mkdir(parents=True)
    (default_root / "bbk" / "__main__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(live, "DEFAULT_BBK_ROOT", str(default_root))
    without = dict(environ)
    without.pop(live.BBK_ROOT_ENV)

    assert live.bbk_root(without) == str(default_root)


def test_explicit_bbk_root_override_wins(
    environ: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "DEFAULT_BBK_ROOT", str(tmp_path / "absent-default-root"))

    assert live.bbk_root(environ) == environ[live.BBK_ROOT_ENV]


def test_invalid_bbk_root_override_does_not_fall_back(
    environ: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "DEFAULT_BBK_ROOT", environ[live.BBK_ROOT_ENV])
    invalid = dict(environ)
    invalid[live.BBK_ROOT_ENV] = str(tmp_path / "absent-override-root")

    with pytest.raises(live.FixtureError) as info:
        live.bbk_root(invalid)

    assert info.value.name == live.BBK_ROOT_ENV


def test_relative_bbk_root_is_rejected(environ: dict[str, str]) -> None:
    invalid = dict(environ)
    invalid[live.BBK_ROOT_ENV] = "relative/root"
    recorder = Recorder()

    with pytest.raises(live.FixtureError) as info:
        live._live_jql(invalid, recorder)

    assert info.value.name == live.BBK_ROOT_ENV
    assert recorder.calls == []


def test_bbk_root_without_the_package_is_rejected(
    environ: dict[str, str], tmp_path: Path
) -> None:
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    invalid = dict(environ)
    invalid[live.BBK_ROOT_ENV] = str(empty_root)
    recorder = Recorder()

    with pytest.raises(live.FixtureError) as info:
        live._live_jql(invalid, recorder)

    assert info.value.name == live.BBK_ROOT_ENV
    assert recorder.calls == []


def test_both_plans_are_fixed_read_only_and_shellless(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY)),
        Result(stdout=jql_rows(KEY)),
    )

    live._live_jql(environ, recorder)

    expected_plan = ("jql", QUERY, "--json", "--limit", str(live.JQL_LIMIT))
    bbk_argv, bbk_kwargs = recorder.calls[0]
    atlawire_argv, atlawire_kwargs = recorder.calls[1]
    assert tuple(bbk_argv) == (*live.BBK_PREFIX, *expected_plan)
    assert tuple(atlawire_argv) == (*live.ATLAWIRE_PREFIX, *expected_plan)
    for kwargs in (bbk_kwargs, atlawire_kwargs):
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] == live.TIMEOUT_SECONDS
        assert kwargs["check"] is False
        assert kwargs["shell"] is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert set(kwargs) == {
            "env",
            "capture_output",
            "timeout",
            "check",
            "shell",
            "stdin",
        }


def test_search_plan_passes_only_the_fixed_repository_scope(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=search_rows(PATH)),
        Result(stdout=search_rows(PATH)),
    )

    live._live_search(environ, recorder)

    expected_plan = (
        "search",
        SEARCH_QUERY,
        "--repo",
        REPO,
        "--json",
        "--limit",
        str(live.SEARCH_LIMIT),
    )
    assert tuple(recorder.calls[0][0]) == (*live.BBK_PREFIX, *expected_plan)
    assert tuple(recorder.calls[1][0]) == (*live.ATLAWIRE_PREFIX, *expected_plan)


def test_author_comment_plans_are_fixed_and_use_the_issue_project(
    environ: dict[str, str],
) -> None:
    rows = author_comment_rows((KEY, COMMENT_ID))
    recorder = Recorder(Result(stdout=rows), Result(stdout=rows))

    live._live_author_comments(environ, recorder)

    bbk_plan = (
        "comments",
        "--days",
        str(live.AUTHOR_COMMENT_DAYS),
        "--limit",
        str(live.AUTHOR_COMMENT_LIMIT),
        "--project",
        "DEMO",
        "--strict",
        "--json",
    )
    atlawire_plan = (
        "jira-author-comments",
        "--days",
        str(live.AUTHOR_COMMENT_DAYS),
        "--limit",
        str(live.AUTHOR_COMMENT_LIMIT),
        "--project",
        "DEMO",
        "--json",
    )
    assert tuple(recorder.calls[0][0]) == (*live.BBK_PREFIX, *bbk_plan)
    assert tuple(recorder.calls[1][0]) == (*live.ATLAWIRE_PREFIX, *atlawire_plan)
    for _, kwargs in recorder.calls:
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == live.TIMEOUT_SECONDS
        assert kwargs["stdin"] == subprocess.DEVNULL


def test_repo_grep_plans_are_fixed_and_escape_the_literal(
    environ: dict[str, str],
) -> None:
    custom = dict(environ)
    custom[live.SEARCH_QUERY_ENV] = "Widget.Service"
    recorder = Recorder(
        Result(stdout=bbk_grep_text((PATH, 10))),
        Result(stdout=atlawire_grep_json((PATH, 10))),
    )

    live._live_repo_grep(custom, recorder)

    pattern = "Widget\\.Service"
    bbk_plan = (
        "grep",
        REPO,
        pattern,
        "--glob",
        PATH,
        "--ref",
        REF,
        "--limit",
        "20",
    )
    atlawire_plan = (
        "grep-repo",
        REPO,
        pattern,
        "--glob",
        PATH,
        "--ref",
        REF,
        "--limit",
        "20",
        "--json",
    )
    assert tuple(recorder.calls[0][0]) == (*live.BBK_PREFIX, *bbk_plan)
    assert tuple(recorder.calls[1][0]) == (*live.ATLAWIRE_PREFIX, *atlawire_plan)


def test_child_environment_drops_credentials_and_fixture_values(
    environ: dict[str, str],
) -> None:
    recorder = Recorder(
        Result(stdout=jql_rows(KEY)),
        Result(stdout=jql_rows(KEY)),
    )

    live._live_jql(environ, recorder)

    bbk_environment = cast(dict[str, str], recorder.calls[0][1]["env"])
    atlawire_environment = cast(dict[str, str], recorder.calls[1][1]["env"])
    for environment in (bbk_environment, atlawire_environment):
        assert environment["PATH"] == "synthetic-path"
        assert environment["HOME"] == "synthetic-home"
        assert environment["BBK_CREDENTIALS"] == "synthetic-bbk-credentials.json"
        assert environment["HTTP_PROXY"] == "http://synthetic-proxy.invalid:3128"
        assert environment["PYTHONIOENCODING"] == "utf-8"
        assert environment["PYTHONUTF8"] == "1"
        for excluded in (
            "ATLAWIRE_JIRA_URL",
            "ATLAWIRE_JIRA_TOKEN",
            "ATLAWIRE_CONFLUENCE_TOKEN",
            "ATLAWIRE_BITBUCKET_TOKEN",
            "ATLAWIRE_LIVE_JIRA_JQL",
            "ATLAWIRE_LIVE_JIRA_ISSUE",
            "ATLAWIRE_LIVE_JIRA_COMMENT_ID",
            "ATLAWIRE_LIVE_CONFLUENCE_CQL",
            "ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID",
            "ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY",
            "ATLAWIRE_LIVE_BITBUCKET_REPO",
            "ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH",
            "ATLAWIRE_LIVE_BITBUCKET_FILE_REF",
            "ATLAWIRE_PARITY_BBK_ROOT",
            "AWS_SECRET_ACCESS_KEY",
        ):
            assert excluded not in environment
        assert SENTINEL not in json.dumps(environment)
    assert bbk_environment["PYTHONPATH"] == environ[live.BBK_ROOT_ENV]
    assert "PYTHONPATH" not in atlawire_environment


def test_allowlist_contains_only_the_read_only_commands() -> None:
    assert live.BBK_COMMANDS == frozenset(
        {"jql", "cql", "search", "comments", "grep"}
    )
    assert live.ATLAWIRE_COMMANDS == frozenset(
        {"jql", "cql", "search", "jira-author-comments", "grep-repo"}
    )
    assert live.ALLOWED_COMMANDS == live.BBK_COMMANDS | live.ATLAWIRE_COMMANDS
    # The two tools spell the repository grep workflow differently, so neither
    # spelling may be accepted for the other tool.
    assert "grep" not in live.ATLAWIRE_COMMANDS
    assert "grep-repo" not in live.BBK_COMMANDS
    for forbidden in (
        "merge",
        "pr-merge",
        "pr_merge",
        "write",
        "comment",
        "issue-comment",
        "page-create",
        "delete",
    ):
        assert forbidden not in live.ALLOWED_COMMANDS


# Independently written from the documented command reference, not read back from
# the live module: each compared AtlaWire workflow and the long options its plan
# passes. The harness plan is checked against this table below.
ATLAWIRE_WORKFLOW_OPTIONS = {
    "jql": frozenset({"--json", "--limit"}),
    "cql": frozenset({"--json", "--limit"}),
    "search": frozenset({"--repo", "--json", "--limit"}),
    "jira-author-comments": frozenset({"--days", "--limit", "--project", "--json"}),
    "grep-repo": frozenset({"--glob", "--ref", "--limit", "--json"}),
}


def atlawire_workflow_plans() -> dict[str, tuple[str, ...]]:
    """Return the AtlaWire side of every compared workflow plan."""
    _, atlawire_comments = live.author_comment_plans("DEMO")
    _, atlawire_grep = live.repo_grep_plans(REPO, SEARCH_QUERY, PATH, REF)
    return {
        "jql": tuple(live._json_plan("jql", QUERY, live.JQL_LIMIT)),
        "cql": tuple(live._json_plan("cql", CQL_QUERY, live.CQL_LIMIT)),
        "search": tuple(live.search_plan(SEARCH_QUERY, REPO)),
        "jira-author-comments": tuple(atlawire_comments),
        "grep-repo": tuple(atlawire_grep),
    }


def test_every_atlawire_plan_uses_a_registered_command_and_options() -> None:
    plans = atlawire_workflow_plans()

    assert set(plans) == set(ATLAWIRE_WORKFLOW_OPTIONS)
    assert live.ATLAWIRE_COMMANDS == frozenset(ATLAWIRE_WORKFLOW_OPTIONS)
    for name, plan in plans.items():
        command = atlawire_cli.commands.get(name)
        assert command is not None, f"{name} is not a registered AtlaWire command"
        assert plan[0] == name
        passed_options = {
            token for token in plan if token.startswith("--")
        }
        assert passed_options == ATLAWIRE_WORKFLOW_OPTIONS[name]
        declared_options = {
            option
            for parameter in command.params
            if isinstance(parameter, click.Option)
            for option in (*parameter.opts, *parameter.secondary_opts)
        }
        assert passed_options <= declared_options, name


@pytest.mark.parametrize("name", sorted(ATLAWIRE_WORKFLOW_OPTIONS))
def test_every_atlawire_plan_is_accepted_by_its_click_command(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The plans never pass --base-url, but its envvar would still be consulted;
    # clear product URLs so this contract test cannot depend on the machine.
    for variable in (
        "ATLAWIRE_JIRA_URL",
        "ATLAWIRE_CONFLUENCE_URL",
        "ATLAWIRE_BITBUCKET_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    plan = atlawire_workflow_plans()[name]
    command = atlawire_cli.commands[name]

    # Click itself parses the exact plan: unknown options, a wrong argument
    # count, or a value outside the declared range would raise a UsageError.
    # The command body is never invoked.
    context = command.make_context(name, list(plan[1:]))
    assert context.command is command


@pytest.mark.parametrize("name", sorted(ATLAWIRE_WORKFLOW_OPTIONS))
def test_every_atlawire_workflow_help_needs_no_authentication(name: str) -> None:
    runner = CliRunner()

    result = runner.invoke(atlawire_cli, [name, "--help"])

    assert result.exit_code == 0
    assert name in result.output
    for option in ATLAWIRE_WORKFLOW_OPTIONS[name]:
        assert option in result.output


def test_failure_categories_are_a_fixed_set() -> None:
    assert live.PARITY_CATEGORIES == frozenset(
        {
            "invalid_plan",
            "timeout",
            "tool_unavailable",
            "tool_failed",
            "invalid_output",
            "empty_result",
            "parity_mismatch",
        }
    )
    with pytest.raises(ValueError):
        live.ParityError("free-form-server-text")
    assert live.INCONCLUSIVE_REASONS == frozenset(
        {
            "author_comment_fixture_not_in_both",
            "grep_fixture_no_hit",
            "grep_partial",
            "grep_limit_reached",
        }
    )
    with pytest.raises(ValueError):
        live.InconclusiveError("free-form-server-text")


def test_live_wrapper_reports_inconclusive_without_traceback() -> None:
    def fail() -> None:
        raise live.InconclusiveError("author_comment_fixture_not_in_both")

    with pytest.raises(pytest.fail.Exception) as info:
        live._run_live_check(fail)

    assert info.value.pytrace is False
    assert str(info.value) == (
        "inconclusive:author_comment_fixture_not_in_both"
    )
    assert info.value.__context__ is None


def test_live_wrapper_reports_parity_category_without_traceback() -> None:
    def fail() -> None:
        raise live.ParityError("parity_mismatch")

    with pytest.raises(pytest.fail.Exception) as info:
        live._run_live_check(fail)

    assert info.value.pytrace is False
    assert str(info.value) == "parity_mismatch"
    assert info.value.__context__ is None


def test_live_wrapper_reports_fixture_category_without_traceback() -> None:
    def fail() -> None:
        raise live.FixtureError(live.JQL_QUERY_ENV)

    with pytest.raises(pytest.fail.Exception) as info:
        live._run_live_check(fail)

    assert info.value.pytrace is False
    assert str(info.value) == f"fixture:{live.JQL_QUERY_ENV}"
    assert info.value.__context__ is None


def test_live_wrapper_hides_unknown_fixture_names() -> None:
    secret = SHOWLOCALS_FIXTURE

    def fail() -> None:
        raise live.FixtureError(secret)

    with pytest.raises(pytest.fail.Exception) as info:
        live._run_live_check(fail)

    assert info.value.pytrace is False
    assert str(info.value) == "fixture_error"
    assert secret not in str(info.value)
    assert secret not in repr(info.value)
    assert info.value.__context__ is None


def test_live_wrapper_reports_unexpected_exception_without_text() -> None:
    secret = SHOWLOCALS_UNEXPECTED

    def fail() -> None:
        local_secret = secret
        raise RuntimeError("boom " + local_secret)

    with pytest.raises(pytest.fail.Exception) as info:
        live._run_live_check(fail)

    assert info.value.pytrace is False
    assert str(info.value) == "unexpected_error"
    assert secret not in str(info.value)
    assert secret not in repr(info.value)
    assert info.value.__context__ is None


def test_live_wrapper_does_not_swallow_base_exceptions() -> None:
    def fail() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        live._run_live_check(fail)


def test_live_wrapper_success_returns() -> None:
    live._run_live_check(lambda: None)


@pytest.mark.parametrize(
    "args",
    [
        ("merge", REPO, "7"),
        ("pr-merge", REPO, "7"),
        ("jql", QUERY, "--json", "--base-url", "https://synthetic.invalid"),
        ("jql", QUERY, "--json", "--limit", "0"),
        ("jql", QUERY, "--json", "--limit", "1001"),
        ("jql", "--help", "--json", "--limit", "10"),
        ("search", SEARCH_QUERY, "--repo", REPO, "--json"),
        ("search", SEARCH_QUERY, "--project", "DEMO", "--json", "--limit", "5"),
        ("search", SEARCH_QUERY, "--repo", "DEMO/..", "--json", "--limit", "5"),
        ("comments", "--days", "90", "--limit", "10", "--project", "DEMO", "--json"),
        (
            "comments",
            "--days",
            "90",
            "--limit",
            "10",
            "--project",
            "DEMO",
            "--strict",
            "--json",
            "--grep",
            "x",
        ),
        (
            "jira-author-comments",
            "--days",
            "90",
            "--limit",
            "10",
            "--project",
            "DEMO",
            "--json",
        ),
        ("grep", REPO, "x", "--path", PATH, "--limit", "20", "--json"),
        ("grep", REPO, "x", "--path", "/abs/A.java", "--limit", "20"),
        ("grep", REPO, "x", "--path", PATH, "--limit", "20", "--all"),
        ("grep", REPO, "x", "--glob", "/abs/A.java", "--limit", "20"),
        ("grep", REPO, "x", "--glob", "src/*.java", "--limit", "20"),
        ("grep", REPO, "x", "--glob", PATH, "--limit", "20", "--json"),
        ("grep", REPO, "x", "--glob", PATH, "--ref", "abc", "--limit", "20"),
        (
            "grep",
            REPO,
            "x",
            "--glob",
            PATH,
            "--ref",
            REF,
            "--limit",
            "20",
            "--json",
        ),
        ("grep", REPO, "x", "--glob", PATH, "--limit", "20", "--ref", REF),
    ],
)
def test_unknown_or_override_arguments_never_start_subprocess(
    args: tuple[str, ...],
) -> None:
    recorder = Recorder()

    with pytest.raises(live.ParityError) as info:
        live.run_tool("bbk", args, runner=recorder, environ={})

    assert info.value.category == "invalid_plan"
    assert recorder.calls == []


def test_unknown_tool_name_is_rejected() -> None:
    with pytest.raises(live.ParityError) as info:
        live.run_tool("other", ("jql", QUERY), runner=Recorder(), environ={})

    assert info.value.category == "invalid_plan"


@pytest.mark.parametrize(
    "args",
    [
        ("grep-repo", REPO, "x", "--path", PATH, "--limit", "20", "--json"),
        (
            "grep-repo",
            REPO,
            "x",
            "--glob",
            PATH,
            "--at",
            REF,
            "--limit",
            "20",
            "--json",
        ),
        (
            "grep-repo",
            REPO,
            "x",
            "--glob",
            PATH,
            "--ref",
            REF,
            "--limit",
            "5",
            "--json",
        ),
        ("grep-repo", REPO, "x", "--glob", PATH, "--ref", REF, "--limit", "20"),
        (
            "grep-repo",
            REPO,
            "x",
            "--glob",
            PATH,
            "--ref",
            REF,
            "--limit",
            "20",
            "--json",
            "--timeout",
            "5",
        ),
    ],
)
def test_atlawire_grep_repo_plan_overrides_never_start_subprocess(
    args: tuple[str, ...],
) -> None:
    recorder = Recorder()

    with pytest.raises(live.ParityError) as info:
        live.run_tool("atlawire", args, runner=recorder, environ={})

    assert info.value.category == "invalid_plan"
    assert recorder.calls == []


def test_tool_specific_plan_names_are_not_interchangeable() -> None:
    cases = (
        (
            "atlawire",
            (
                "comments",
                "--days",
                "90",
                "--limit",
                "10",
                "--project",
                "DEMO",
                "--strict",
                "--json",
            ),
        ),
        (
            "bbk",
            (
                "jira-author-comments",
                "--days",
                "90",
                "--limit",
                "10",
                "--project",
                "DEMO",
                "--json",
            ),
        ),
        # AtlaWire registers ``grep-repo``; BBK registers ``grep``. The exact
        # expected shapes below must still be rejected when only the command
        # name belongs to the other tool.
        (
            "atlawire",
            (
                "grep",
                REPO,
                "x",
                "--glob",
                PATH,
                "--ref",
                REF,
                "--limit",
                "20",
                "--json",
            ),
        ),
        (
            "bbk",
            (
                "grep-repo",
                REPO,
                "x",
                "--glob",
                PATH,
                "--ref",
                REF,
                "--limit",
                "20",
            ),
        ),
    )
    for tool, args in cases:
        recorder = Recorder()
        with pytest.raises(live.ParityError) as info:
            live.run_tool(tool, args, runner=recorder, environ={})
        assert info.value.category == "invalid_plan"
        assert recorder.calls == []


def test_mismatch_never_echoes_captured_payloads(
    environ: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        Result(
            stdout=json_bytes([{"key": KEY, "summary": SENTINEL, "url": SENTINEL}]),
            stderr=SENTINEL.encode(),
        ),
        Result(
            stdout=json_bytes(
                [{"key": OTHER_KEY, "summary": SENTINEL, "url": SENTINEL}]
            ),
            stderr=SENTINEL.encode(),
        ),
    )

    with pytest.raises(live.ParityError) as info:
        live._live_jql(environ, recorder)

    assert info.value.category == "parity_mismatch"
    assert SENTINEL not in str(info.value)
    assert SENTINEL not in repr(info.value)
    assert QUERY not in str(info.value)
    assert environ[live.BBK_ROOT_ENV] not in str(info.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


_SHOWLOCALS_TEST_TEMPLATE = """\
import importlib.util

LIVE_PATH = {live_path}


def _load_live():
    spec = importlib.util.spec_from_file_location("live_child", LIVE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load live module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = _load_live()
fixture_name = {fixture_name}


def _expected(environ, runner):
    synthetic_secret = {expected}
    raise live.ParityError("parity_mismatch")


def _fixture(environ, runner):
    synthetic_secret = {fixture}
    raise live.FixtureError(fixture_name)


def _unexpected(environ, runner):
    synthetic_secret = {unexpected}
    raise RuntimeError("boom " + synthetic_secret)


def _inconclusive(environ, runner):
    synthetic_secret = {inconclusive}
    raise live.InconclusiveError("author_comment_fixture_not_in_both")


def _grep_unexpected(environ, runner):
    synthetic_secret = {unexpected}
    raise RuntimeError("grep boom " + synthetic_secret)


def test_expected_failure(monkeypatch):
    synthetic_secret = {expected}
    monkeypatch.setattr(live, "_live_jql", _expected)
    live.test_bbk_jql_issue_keys_match_atlawire()


def test_fixture_failure(monkeypatch):
    synthetic_secret = {fixture}
    monkeypatch.setattr(live, "_live_jql", _fixture)
    live.test_bbk_jql_issue_keys_match_atlawire()


def test_unexpected_failure(monkeypatch):
    synthetic_secret = {unexpected}
    monkeypatch.setattr(live, "_live_jql", _unexpected)
    live.test_bbk_jql_issue_keys_match_atlawire()


def test_inconclusive_failure(monkeypatch):
    synthetic_secret = {inconclusive}
    monkeypatch.setattr(live, "_live_author_comments", _inconclusive)
    live.test_bbk_jira_author_comments_match_atlawire()


def test_grep_unexpected_failure(monkeypatch):
    synthetic_secret = {unexpected}
    monkeypatch.setattr(live, "_live_repo_grep", _grep_unexpected)
    live.test_bbk_repo_grep_matches_atlawire()


def _control_failure():
    control_secret = {control}
    raise RuntimeError("control failure")


def test_control_showlocals():
    _control_failure()
"""


def _subprocess_environment() -> dict[str, str]:
    """Pass only ordinary OS settings, never credentials or fixtures."""
    keep = {
        "APPDATA",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        name: value for name, value in os.environ.items() if name.upper() in keep
    }
    environment.update(
        {
            "NO_COLOR": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    return environment


def test_showlocals_never_reveals_synthetic_values(tmp_path: Path) -> None:
    test_file = tmp_path / "test_showlocals_contract.py"
    test_file.write_text(
        _SHOWLOCALS_TEST_TEMPLATE.format(
            live_path=repr(str(SCRIPT)),
            expected=repr(SHOWLOCALS_EXPECTED),
            fixture=repr(SHOWLOCALS_FIXTURE),
            unexpected=repr(SHOWLOCALS_UNEXPECTED),
            inconclusive=repr(SHOWLOCALS_INCONCLUSIVE),
            control=repr(SHOWLOCALS_CONTROL),
            fixture_name=repr(live.JQL_QUERY_ENV),
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "--showlocals",
            str(test_file),
        ],
        capture_output=True,
        timeout=120,
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        env=_subprocess_environment(),
    )
    output = (completed.stdout or b"") + (completed.stderr or b"")
    text = output.decode("utf-8", errors="replace")

    assert completed.returncode != 0
    for secret in SHOWLOCALS_SECRETS:
        assert secret not in text
    assert SHOWLOCALS_CONTROL in text
    assert "parity_mismatch" in text
    assert f"fixture:{live.JQL_QUERY_ENV}" in text
    assert "unexpected_error" in text
    assert "inconclusive:author_comment_fixture_not_in_both" in text


def test_live_checks_stay_outside_default_testpaths() -> None:
    import tomllib

    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert Path(live.__file__).resolve().parent == PROJECT_ROOT / "checks"

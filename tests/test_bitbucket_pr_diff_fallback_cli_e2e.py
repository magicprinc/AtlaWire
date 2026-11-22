"""Installed-CLI loopback tests for the complete pull request diff fallback."""

import json
import subprocess
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-pr-diff-fallback"
JIRA_TOKEN = "wrong-product-jira-diff-fallback"
CONFLUENCE_TOKEN = "wrong-product-confluence-diff-fallback"
SENTINEL = "PR-DIFF-FALLBACK-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
PR_ID = "7"
DIFF_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7/diff"
)
CHANGES_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets"
    "/pull-requests/7/changes"
)
FILE_A = "src/é +&?.py"
FILE_A_ENCODED = "src/%C3%A9%20%2B%26%3F.py"
FILE_B = "docs/read me.md"
FILE_B_ENCODED = "docs/read%20me.md"
DIFF_QUERY = {
    "contextLines": ["3"],
    "whitespace": ["ignore-all"],
    "withComments": ["false"],
}


def file_diff(path: str, *, truncated: object = False) -> dict[str, object]:
    return {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [],
            }
        ],
        "truncated": truncated,
    }


def whole_diff(*, truncated: object = False) -> dict[str, object]:
    return file_diff("src/a.py", truncated=truncated)


def nested_truncated_diff() -> dict[str, object]:
    body = file_diff("src/a.py")
    diffs = body["diffs"]
    assert isinstance(diffs, list)
    diff = diffs[0]
    assert isinstance(diff, dict)
    diff["truncated"] = True
    return body


def change(
    path: str,
    *,
    change_type: str = "MODIFY",
    source_path: object = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path,
        "type": change_type,
        "nodeType": "FILE",
    }
    if source_path is not None:
        row["srcPath"] = source_path
    return row


def changes_page(
    rows: list[object],
    *,
    limit: int = 1000,
    is_last: bool = True,
    truncated: object = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "values": rows,
        "size": len(rows),
        "limit": limit,
        "start": 0,
        "isLastPage": is_last,
    }
    if truncated is not None:
        body["truncated"] = truncated
    return body


def environment(origin: str) -> dict[str, str]:
    """Point both products at the loopback server and keep Confluence inert."""
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "BBK_CREDENTIALS": (
            "C:/TMP/opencode/nonexistent-bbk-pr-diff-fallback.json"
        ),
    }


def run_complete(
    *arguments: str,
    routes: Mapping[str, tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    seen: list[Request] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            path = urlsplit(self.path).path
            status, body = routes.get(
                path,
                (500, {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]}),
            )
            if 300 <= status < 400:
                self.send_response(status)
                self.send_header("Location", "https://evil.invalid/next")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                send_json(self, status, body)

        def _refuse_write(self, method: str) -> None:
            extra_methods.append(method)
            send_json(self, 405, {"errors": [{"message": "write refused"}]})

        def do_POST(self) -> None:
            self._refuse_write("POST")

        def do_PUT(self) -> None:
            self._refuse_write("PUT")

        def do_DELETE(self) -> None:
            self._refuse_write("DELETE")

        def do_PATCH(self) -> None:
            self._refuse_write("PATCH")

        def do_HEAD(self) -> None:
            extra_methods.append("HEAD")
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            extra_methods.append("OPTIONS")
            self.send_error(405)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "pr-diff-complete",
                REPO,
                PR_ID,
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment(origin),
        )
    return result, seen, extra_methods


def diff_request() -> Request:
    return ("GET", DIFF_PATH, dict(DIFF_QUERY), f"Bearer {TOKEN}")


def changes_request() -> Request:
    return ("GET", CHANGES_PATH, {"limit": ["1000"]}, f"Bearer {TOKEN}")


def file_request(encoded_path: str, *, src_path: str | None = None) -> Request:
    query = dict(DIFF_QUERY)
    if src_path is not None:
        query["srcPath"] = [src_path]
    return (
        "GET",
        f"{DIFF_PATH}/{encoded_path}",
        query,
        f"Bearer {TOKEN}",
    )


def test_complete_whole_diff_is_returned_without_fallback() -> None:
    body = whole_diff()

    result, seen, extra = run_complete(
        "--json", routes={DIFF_PATH: (200, body)}
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "fallback": False,
        "fallback_reason": None,
        "diff": body,
        "files": [],
    }
    assert seen == [diff_request()]
    assert extra == []


def test_declared_whole_diff_truncation_fetches_every_file_once() -> None:
    first = file_diff(FILE_A)
    second = file_diff(FILE_B)

    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (
                200,
                changes_page(
                    [change(FILE_A), change(FILE_B, change_type="ADD")]
                ),
            ),
            f"{DIFF_PATH}/{FILE_A_ENCODED}": (200, first),
            f"{DIFF_PATH}/{FILE_B_ENCODED}": (200, second),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "fallback": True,
        "fallback_reason": "Bitbucket reported a truncated pull request diff.",
        "diff": None,
        "files": [
            {"path": FILE_A, "source_path": None, "diff": first},
            {"path": FILE_B, "source_path": None, "diff": second},
        ],
    }
    assert seen == [
        diff_request(),
        changes_request(),
        file_request(FILE_A_ENCODED),
        file_request(FILE_B_ENCODED),
    ]
    assert extra == []


def test_nested_declared_truncation_also_fetches_the_file_fallback() -> None:
    body = file_diff(FILE_A)

    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, nested_truncated_diff()),
            CHANGES_PATH: (200, changes_page([change(FILE_A)])),
            f"{DIFF_PATH}/{FILE_A_ENCODED}": (200, body),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    assert parsed["fallback"] is True
    assert parsed["diff"] is None
    assert parsed["files"] == [
        {"path": FILE_A, "source_path": None, "diff": body}
    ]
    assert seen == [
        diff_request(),
        changes_request(),
        file_request(FILE_A_ENCODED),
    ]
    assert extra == []


def test_a_moved_file_sends_its_source_path_in_the_fixed_get() -> None:
    body = file_diff(FILE_A)

    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (
                200,
                changes_page(
                    [
                        change(
                            FILE_A,
                            change_type="MOVE",
                            source_path={
                                "toString": "old/name.py",
                                "components": ["old", "name.py"],
                                "name": "name.py",
                            },
                        )
                    ]
                ),
            ),
            f"{DIFF_PATH}/{FILE_A_ENCODED}": (200, body),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["files"] == [
        {"path": FILE_A, "source_path": "old/name.py", "diff": body}
    ]
    assert seen == [
        diff_request(),
        changes_request(),
        file_request(FILE_A_ENCODED, src_path="old/name.py"),
    ]
    assert extra == []


def test_a_later_file_failure_leaves_no_partial_stdout() -> None:
    failure = (
        503,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (
                200,
                changes_page([change(FILE_A), change(FILE_B)]),
            ),
            f"{DIFF_PATH}/{FILE_A_ENCODED}": (200, file_diff(FILE_A)),
            f"{DIFF_PATH}/{FILE_B_ENCODED}": failure,
        },
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [
        diff_request(),
        changes_request(),
        file_request(FILE_A_ENCODED),
        file_request(FILE_B_ENCODED),
    ]
    assert extra == []


def test_a_capped_changes_page_fails_before_any_file_request() -> None:
    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (
                200,
                changes_page(
                    [change(FILE_A), change(FILE_B)], limit=2
                ),
            ),
        },
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "reported limit" in result.stderr
    assert seen == [diff_request(), changes_request()]
    assert extra == []


def test_a_truncated_whole_diff_with_an_empty_changes_page_fails() -> None:
    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (200, changes_page([])),
        },
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "empty changes page" in result.stderr
    assert "HTTP" not in result.stderr
    assert seen == [diff_request(), changes_request()]
    assert extra == []


def test_a_truncated_changes_page_fails_before_any_file_request() -> None:
    result, seen, extra = run_complete(
        "--json",
        routes={
            DIFF_PATH: (200, whole_diff(truncated=True)),
            CHANGES_PATH: (
                200,
                changes_page([change(FILE_A)], truncated=True),
            ),
        },
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated pull request changes" in result.stderr
    assert seen == [diff_request(), changes_request()]
    assert extra == []


def test_a_malformed_whole_diff_flag_does_not_fall_back() -> None:
    result, seen, extra = run_complete(
        "--json",
        routes={DIFF_PATH: (200, whole_diff(truncated="yes"))},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncation flag" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [diff_request()]
    assert extra == []


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (302, "redirect refused"),
    ],
    ids=["401", "403", "404", "redirect"],
)
def test_whole_diff_failures_never_start_the_fallback(
    status: int, detail: str
) -> None:
    failure = (
        status,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_complete(
        "--json", routes={DIFF_PATH: failure}
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert detail in result.stderr
    for secret in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert secret not in result.stderr
    assert seen == [diff_request()]
    assert extra == []

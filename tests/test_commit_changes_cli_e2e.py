import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-commit-changes"
JIRA_TOKEN = "wrong-product-jira-commit-changes"
CONFLUENCE_TOKEN = "wrong-product-confluence-commit-changes"
SENTINEL = "COMMIT-CHANGES-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
SHA = "a1b2c3d"
CHANGES_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}/changes"
)

MOVED: dict[str, object] = {
    "path": {
        "toString": "src/ü +&?.py",
        "components": ["ignored", "metadata"],
        "name": "unused.py",
    },
    "srcPath": {"toString": "old/name.py"},
    "type": "MOVE",
    "nodeType": "FILE",
}
PLAIN: dict[str, object] = {"path": "README.md"}


def page(values: list[dict[str, object]], **fields: object) -> dict[str, object]:
    body: dict[str, object] = {
        "size": len(values),
        "limit": 100,
        "isLastPage": True,
        "values": values,
    }
    body.update(fields)
    return body


def run_changes(
    *arguments: str,
    sha: str = SHA,
    responses: Sequence[tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    seen: list[Request] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            index = len(seen) - 1
            if index >= len(responses):
                status, body = (
                    500,
                    {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]},
                )
            else:
                status, body = responses[index]
            send_json(self, status, body)

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
                "commit-changes",
                REPO,
                sha,
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            {
                "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
            },
        )
    return result, seen, extra_methods


def changes_request(start: int) -> Request:
    return (
        "GET",
        CHANGES_PATH,
        {"start": [str(start)], "limit": ["100"]},
        f"Bearer {TOKEN}",
    )


def test_changes_follow_a_noncontiguous_cursor_and_keep_server_order_as_json() -> None:
    responses = [
        (200, page([MOVED], isLastPage=False, nextPageStart=57)),
        (200, page([PLAIN])),
    ]

    result, seen, extra = run_changes("--json", responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {"path": "src/ü +&?.py", "type": "MOVE", "node": "FILE"},
        {"path": "README.md", "type": None, "node": None},
    ]
    assert seen == [changes_request(0), changes_request(57)]
    assert extra == []


def test_changes_tsv_projects_path_objects_and_plain_optional_fields() -> None:
    responses = [(200, page([MOVED, PLAIN]))]

    result, seen, extra = run_changes(responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 2 row(s)\npath\ttype\tnode\nsrc/ü +&?.py\tMOVE\tFILE\nREADME.md\t\t\n"
    )
    assert seen == [changes_request(0)]
    assert extra == []


@pytest.mark.parametrize(
    "sha",
    ["abc123", "a" * 41, "refs/heads/main", "main", "g" * 7, "a1b2c3d\n"],
    ids=[
        "too-short",
        "too-long",
        "symbolic-ref",
        "branch",
        "non-hex",
        "control",
    ],
)
def test_a_non_hex_or_out_of_range_commit_id_fails_before_any_request(
    sha: str,
) -> None:
    result, seen, extra = run_changes("--json", sha=sha, responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "commit ID" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == []
    assert extra == []


def test_a_page_cap_mid_fetch_fails_without_partial_rows() -> None:
    responses = [(200, page([MOVED], isLastPage=False, nextPageStart=57))]

    result, seen, extra = run_changes("--max-pages", "1", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "page limit" in result.stderr
    assert seen == [changes_request(0)]
    assert extra == []


@pytest.mark.parametrize("flag", [True, "true"], ids=["bool", "string"])
def test_a_declared_truncated_page_fails_without_partial_rows(flag: object) -> None:
    responses = [
        (200, page([MOVED], isLastPage=False, nextPageStart=57)),
        (
            200,
            page(
                [PLAIN],
                isLastPage=True,
                truncated=flag,
            ),
        ),
    ]

    result, seen, extra = run_changes("--json", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [changes_request(0), changes_request(57)]
    assert extra == []


@pytest.mark.parametrize("arguments", [(), ("--json",)], ids=["tsv", "json"])
def test_a_late_lone_surrogate_path_fails_without_partial_output(
    arguments: tuple[str, ...],
) -> None:
    responses = [
        (200, page([MOVED], isLastPage=False, nextPageStart=57)),
        (200, page([{"path": "ok.py"}, {"path": "\ud800"}])),
    ]

    result, seen, extra = run_changes(*arguments, responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "change path" in result.stderr
    assert "valid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [changes_request(0), changes_request(57)]
    assert extra == []


def test_a_malformed_truncation_flag_is_rejected() -> None:
    responses = [(200, page([PLAIN], truncated=1))]

    result, seen, extra = run_changes("--json", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncation flag" in result.stderr
    assert seen == [changes_request(0)]
    assert extra == []

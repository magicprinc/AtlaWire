"""Installed-CLI loopback contract for the ``pr-review`` command.

The command is wired by the CLI integration slice before the batch run. A
missing launcher or a missing ``pr-review`` command is a failure here, not a
skip, so the installed interface cannot silently go unverified.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance, reads a real credential store, installs anything or
mutates server state.
"""

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from atlawire.cli import cli as source_cli
from tests._loopback import (
    Request,
    request_record,
    send_json,
    serving,
)

BITBUCKET_TOKEN = "synthetic-pr-review-token-7c3"
JIRA_TOKEN = "synthetic-pr-review-jira-token-8d4"
SENTINEL = "PR-REVIEW-CLI-SENTINEL"
JIRA_PATH = "/jira/rest/api/2/issue/DEMO-42"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-pr-review.json")
)

BASE_PATH = "/bitbucket/rest/api/1.0/projects/DEMO/repos/widgets"
PR_PATH = f"{BASE_PATH}/pull-requests/7"
COMMITS_PATH = f"{PR_PATH}/commits"
CHANGES_PATH = f"{PR_PATH}/changes"
DIFF_PATH = f"{PR_PATH}/diff"
AUTHORIZATION = f"Bearer {BITBUCKET_TOKEN}"

FROM_HASH = "a" * 40
TO_HASH = "b" * 40


def pr_payload(*, from_branch: str = "feature") -> dict[str, object]:
    return {
        "id": 7,
        "title": "Example review",
        "description": "Example description",
        "state": "OPEN",
        "author": {"user": {"displayName": "Reviewer"}},
        "fromRef": {"displayId": from_branch, "latestCommit": FROM_HASH},
        "toRef": {"displayId": "main", "latestCommit": TO_HASH},
        "links": {"self": [{"href": "https://evil.invalid/never-followed"}]},
    }


def jira_payload() -> dict[str, object]:
    return {
        "key": "DEMO-42",
        "fields": {
            "summary": "Do the thing",
            "status": {"name": "Open"},
            "issuetype": {"name": "Task"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Bob"},
            "reporter": {"displayName": "Alice"},
            "description": "raw fallback",
        },
        "renderedFields": {"description": "<p>Do the <b>thing</b></p>"},
    }


def page(values: list[object], *, limit: int) -> dict[str, object]:
    return {
        "values": values,
        "size": len(values),
        "limit": limit,
        "start": 0,
        "isLastPage": True,
    }


def commits_payload() -> dict[str, object]:
    return page(
        [
            {
                "id": "c" * 40,
                "author": {"name": "alice"},
                "authorTimestamp": 1_700_000_000_000,
                "message": "Change the widget",
            }
        ],
        limit=100,
    )


def changes_payload() -> dict[str, object]:
    return page(
        [
            {
                "path": {"toString": "README.txt"},
                "type": "MODIFY",
                "nodeType": "FILE",
            }
        ],
        limit=1000,
    )


def diff_payload() -> dict[str, object]:
    return {
        "diffs": [
            {
                "source": {"toString": "README.txt"},
                "destination": {"toString": "README.txt"},
                "hunks": [
                    {
                        "sourceLine": 1,
                        "sourceSpan": 1,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "before"}],
                            },
                            {
                                "type": "ADDED",
                                "lines": [{"line": "after"}],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def environment(origin: str, *, jira: bool = False) -> dict[str, str]:
    """Point products at the loopback and keep every other source inert."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("ATLAWIRE_", "BBK_"))
    }
    env.update(
        {
            "ATLAWIRE_BITBUCKET_URL": f"{origin}/bitbucket/",
            "ATLAWIRE_BITBUCKET_TOKEN": BITBUCKET_TOKEN,
            "ATLAWIRE_JIRA_URL": (
                f"{origin}/jira/" if jira else f"{origin}/wrong-jira/"
            ),
            "ATLAWIRE_JIRA_TOKEN": (
                JIRA_TOKEN if jira else "wrong-product-fixture"
            ),
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
            "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
            "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
            "NO_PROXY": "127.0.0.1",
        }
    )
    return env


def review_args(*extra: str) -> list[str]:
    return [
        "pr-review",
        "DEMO/widgets",
        "7",
        "--json",
        "--token-from-env",
        "--allow-http-loopback",
        *extra,
    ]


def routes(
    *, diff: tuple[int, object] | None = None
) -> dict[str, tuple[int, object]]:
    return {
        PR_PATH: (200, pr_payload()),
        COMMITS_PATH: (200, commits_payload()),
        CHANGES_PATH: (200, changes_payload()),
        DIFF_PATH: (200, diff_payload()) if diff is None else diff,
    }


def file_links(origin: str, path: str) -> dict[str, str]:
    return {
        "before": (
            f"{origin}/bitbucket/projects/DEMO/repos/widgets/browse/"
            f"{path}?at={TO_HASH}"
        ),
        "after": (
            f"{origin}/bitbucket/projects/DEMO/repos/widgets/browse/"
            f"{path}?at={FROM_HASH}"
        ),
        "diff": (
            f"{origin}/bitbucket/projects/DEMO/repos/widgets/"
            f"pull-requests/7/diff#{path}"
        ),
    }


def origin_of(packet: dict[str, object]) -> str:
    links = packet["links"]
    assert isinstance(links, dict)
    overview = links["overview"]
    assert isinstance(overview, str)
    parts = urlsplit(overview)
    return f"{parts.scheme}://{parts.netloc}"


def expected_requests(*, include_diff: bool) -> list[Request]:
    rows: list[Request] = [
        ("GET", PR_PATH, {}, AUTHORIZATION),
        ("GET", COMMITS_PATH, {"start": ["0"], "limit": ["100"]}, AUTHORIZATION),
        ("GET", CHANGES_PATH, {"limit": ["1000"]}, AUTHORIZATION),
    ]
    if include_diff:
        rows.append(
            (
                "GET",
                DIFF_PATH,
                {
                    "contextLines": ["2"],
                    "whitespace": ["ignore-all"],
                    "withComments": ["false"],
                },
                AUTHORIZATION,
            )
        )
    return rows


def run_cli(
    script: str,
    args: list[str],
    route_table: dict[str, tuple[int, object]],
    *,
    jira: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *values: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            _, path, _, authorization = record
            expected = (
                f"Bearer {JIRA_TOKEN}"
                if path.startswith("/jira/")
                else AUTHORIZATION
            )
            if authorization != expected:
                send_json(self, 401, {"message": SENTINEL})
                return
            route = route_table.get(path)
            if route is None:
                send_json(self, 404, {"message": SENTINEL})
                return
            status, body = route
            send_json(self, status, body)

        def do_POST(self) -> None:
            seen.append(request_record(self))
            send_json(self, 405, {"message": SENTINEL})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        resolved = [arg.replace("{origin}", origin) for arg in args]
        result = subprocess.run(
            [script, *resolved],
            env=environment(origin, jira=jira),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    return result, seen


@pytest.fixture(scope="module")
def installed_cli() -> str:
    script = shutil.which("atlawire")
    if script is None:
        pytest.fail("Install AtlaWire before running its CLI E2E suite.")

    catalog = subprocess.run(
        [script, "--catalog"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if catalog.returncode != 0:
        pytest.fail(f"atlawire --catalog failed: {catalog.stderr}")
    try:
        commands = json.loads(catalog.stdout)["commands"]
    except (KeyError, TypeError, ValueError):
        pytest.fail("atlawire --catalog did not return a command catalog")
    if not isinstance(commands, dict):
        pytest.fail("atlawire --catalog did not return a command mapping")
    if "pr-review" in source_cli.commands and "pr-review" not in commands:
        pytest.fail(
            "pr-review is registered in the working tree but missing from the "
            "installed atlawire script; reinstall before running this suite"
        )
    if "pr-review" not in commands:
        pytest.fail(
            "pr-review is missing from the installed CLI; wire the command and "
            "reinstall before running this batch"
        )
    return script


def test_pr_review_prints_the_complete_packet_from_four_fixed_gets(
    installed_cli: str,
) -> None:
    result, seen = run_cli(installed_cli, review_args(), routes())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    packet = json.loads(result.stdout)
    assert packet["repo"] == "DEMO/widgets"
    assert packet["pr_id"] == 7
    assert packet["title"] == "Example review"
    assert packet["author"] == "Reviewer"
    assert packet["from_branch"] == "feature"
    assert packet["to_branch"] == "main"
    assert packet["commits"][0]["message"] == "Change the widget"
    origin = origin_of(packet)
    assert packet["files"] == [
        {
            "path": "README.txt",
            "type": "MODIFY",
            "node": "FILE",
            "added": 1,
            "removed": 1,
            "lines_source": "server-diff",
            "test": False,
            "links": file_links(origin, "README.txt"),
        }
    ]
    assert packet["diff"]["requested"] is True
    assert packet["diff"]["text_truncated"] is False
    assert packet["diff"]["proven_complete"] is False
    assert "-before" in packet["diff"]["text"]
    assert "+after" in packet["diff"]["text"]
    assert packet["profile"]["partial"] is False
    assert packet["ticket"] is None
    assert packet["checks"]["heuristic"] is True
    assert SENTINEL not in result.stdout
    assert "evil.invalid" not in result.stdout
    assert BITBUCKET_TOKEN not in result.stdout
    assert seen == expected_requests(include_diff=True)


def test_no_diff_skips_the_diff_route_and_leaves_counts_unknown(
    installed_cli: str,
) -> None:
    # The failing diff route proves that --no-diff avoids the request rather
    # than merely ignoring its result.
    result, seen = run_cli(
        installed_cli,
        review_args("--no-diff"),
        routes(diff=(500, {"message": SENTINEL})),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    packet = json.loads(result.stdout)
    origin = origin_of(packet)
    assert packet["files"] == [
        {
            "path": "README.txt",
            "type": "MODIFY",
            "node": "FILE",
            "added": None,
            "removed": None,
            "lines_source": "not-requested",
            "test": False,
            "links": file_links(origin, "README.txt"),
        }
    ]
    assert packet["diff"]["requested"] is False
    assert packet["diff"]["text"] is None
    assert packet["diff"]["added"] is None
    assert packet["diff"]["removed"] is None
    assert packet["diff"]["counts_complete"] is None
    assert packet["profile"]["partial"] is True
    assert any(
        "intentionally omitted" in reason
        for reason in packet["profile"]["partial_reasons"]
    )
    assert seen == expected_requests(include_diff=False)
    assert all(urlsplit(path).path != DIFF_PATH for _, path, _, _ in seen)


def test_a_later_diff_failure_prints_no_partial_packet(
    installed_cli: str,
) -> None:
    result, seen = run_cli(
        installed_cli,
        review_args(),
        routes(diff=(500, {"message": SENTINEL})),
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 500" in result.stderr
    assert SENTINEL not in result.stderr
    assert BITBUCKET_TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_requests(include_diff=True)


def test_invalid_id_fails_before_any_request(installed_cli: str) -> None:
    args = review_args()
    args[2] = "0"

    result, seen = run_cli(installed_cli, args, routes())

    assert result.returncode in {1, 2}
    assert result.stdout == ""
    assert seen == []
    assert BITBUCKET_TOKEN not in result.stderr


@pytest.mark.parametrize("flag", ["--refresh", "--no-pull", "--root", "--refr"])
def test_removed_bbk_flags_are_rejected_before_any_request(
    installed_cli: str, flag: str
) -> None:
    extra = [flag, "unused"] if flag == "--root" else [flag]

    result, seen = run_cli(installed_cli, review_args(*extra), routes())

    assert result.returncode == 2
    assert result.stdout == ""
    assert "No such option" in result.stderr
    assert flag in result.stderr
    assert seen == []


def test_pr_review_enriches_a_detected_ticket_with_only_the_jira_pair(
    installed_cli: str,
) -> None:
    table = routes()
    table[PR_PATH] = (200, pr_payload(from_branch="feature/DEMO-42"))
    table[JIRA_PATH] = (200, jira_payload())
    args = review_args(
        "--jira-base-url",
        "{origin}/jira/",
        "--jira-token-from-env",
    )

    result, seen = run_cli(
        installed_cli, args, table, jira=True
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["ticket"]["verified"] is True
    assert packet["ticket"]["key"] == "DEMO-42"
    assert packet["profile"]["partial"] is False
    assert packet["ticket"]["summary"] == "Do the thing"
    assert packet["ticket"]["status"] == "Open"
    assert packet["checks"]["heuristic"] is True
    assert BITBUCKET_TOKEN not in result.stdout
    assert JIRA_TOKEN not in result.stdout
    expected = expected_requests(include_diff=True)
    expected.append(
        (
            "GET",
            JIRA_PATH,
            {"expand": ["renderedFields"]},
            f"Bearer {JIRA_TOKEN}",
        )
    )
    assert seen == expected


def test_pr_review_reports_a_detected_ticket_without_jira_as_unverified(
    installed_cli: str,
) -> None:
    table = routes()
    table[PR_PATH] = (200, pr_payload(from_branch="feature/DEMO-42"))

    result, seen = run_cli(installed_cli, review_args(), table)

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["ticket"]["key"] == "DEMO-42"
    assert packet["ticket"]["verified"] is False
    assert "not supplied" in packet["ticket"]["error"]
    assert packet["profile"]["partial"] is True
    assert any(
        "unverified" in reason for reason in packet["profile"]["partial_reasons"]
    )
    assert seen == expected_requests(include_diff=True)

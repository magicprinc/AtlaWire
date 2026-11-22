"""Unit contracts for the API-only pull request review packet.

Every test uses synthetic adapter results or the loopback-free ``responses``
transport. No test reads a credential, calls a real server, starts a local
process or inspects a repository.
"""

import ast
import base64
import inspect
import json
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from atlawire import bitbucket, jira, pr_review
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-pr-review-token"
JIRA_BASE = "https://jira.example.invalid"
JIRA_TOKEN = "fixture-only-jira-review-token"
REPO = "DEMO/widgets"
PR_ID = 7
LOOPBACK = "http://127.0.0.1:8123"

PR_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7"
COMMITS_URL = f"{PR_URL}/commits"
CHANGES_URL = f"{PR_URL}/changes"
DIFF_URL = f"{PR_URL}/diff"

FROM_HASH = "a" * 40
TO_HASH = "b" * 40

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "atlawire" / "pr_review.py"
)
PR_LINKS = {
    "overview": f"{BASE}/projects/DEMO/repos/widgets/pull-requests/7/overview",
    "diff": f"{BASE}/projects/DEMO/repos/widgets/pull-requests/7/diff",
}


def expected_links(path: str, *, change_type: str = "MODIFY") -> dict[str, str]:
    before = (
        f"{BASE}/projects/DEMO/repos/widgets/browse/{path}?at={TO_HASH}"
        if change_type != "ADD"
        else ""
    )
    after = (
        f"{BASE}/projects/DEMO/repos/widgets/browse/{path}?at={FROM_HASH}"
        if change_type != "DELETE"
        else ""
    )
    diff = f"{BASE}/projects/DEMO/repos/widgets/pull-requests/7/diff#{path}"
    return {"before": before, "after": after, "diff": diff}

Call = tuple[str, tuple[object, ...], dict[str, object]]


def commit_payload(index: int = 1, *, message: str = "Change") -> dict[str, object]:
    """Return the server shape of one commit."""
    return {
        "id": f"{index:040x}",
        "author": {"name": "alice"},
        "authorTimestamp": 1_700_000_000_000,
        "message": message,
        "links": {"self": [{"href": "https://evil.invalid/commit"}]},
    }


def commit_row(index: int = 1, *, message: str = "Change") -> dict[str, object]:
    """Return the public adapter projection of one commit."""
    return {
        "hash": f"{index:040x}",
        "date": "2023-11-14 22:13",
        "author": "alice",
        "message": message,
    }


def file_row(
    path: str, *, change_type: str = "MODIFY", node: str = "FILE"
) -> dict[str, object]:
    """Return the public adapter projection of one changed file."""
    return {"path": path, "type": change_type, "node": node}


def default_files() -> list[dict[str, object]]:
    return [
        file_row("src/App.txt"),
        file_row("docs/README.md"),
        file_row("images/logo.png"),
    ]


def pr_body(**overrides: object) -> dict[str, object]:
    """Return a pull request object with useful and unknown server fields."""
    body: dict[str, object] = {
        "id": PR_ID,
        "title": "Example review",
        "description": "  Purpose and risk.  ",
        "state": "OPEN",
        "author": {"user": {"displayName": "Alice Reviewer"}},
        "fromRef": {"displayId": "feature", "latestCommit": FROM_HASH},
        "toRef": {"displayId": "main", "latestCommit": TO_HASH},
        "createdDate": 1_700_000_000_000,
        "updatedDate": 1_700_000_001_000,
        "links": {"self": [{"href": "https://evil.invalid/never-followed"}]},
        "unknown": {"nested": [None, True, "alpha"]},
    }
    body.update(overrides)
    return body


def hunk(segments: object) -> dict[str, object]:
    """Return a valid hunk around one segment collection."""
    return {
        "sourceLine": 0,
        "sourceSpan": 0,
        "destinationLine": 1,
        "destinationSpan": 1,
        "segments": segments,
    }


def diff_body() -> dict[str, object]:
    """Return a diff with counted lines, a no-hunk file and an omitted file."""
    return {
        "links": {"self": [{"href": "https://evil.invalid/diff"}]},
        "diffs": [
            {
                "source": {"toString": "src/App.txt"},
                "destination": {"toString": "src/App.txt"},
                "hunks": [
                    hunk(
                        [
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "old"}],
                            },
                            {
                                "type": "ADDED",
                                "lines": [{"line": "new"}, {"line": "more"}],
                            },
                        ]
                    )
                ],
            },
            {
                "source": {"toString": "docs/README.md"},
                "destination": {"toString": "docs/README.md"},
                "hunks": [],
            },
        ]
    }


def literal_diff() -> dict[str, object]:
    """Return a representative modification plus deletion with context."""
    return {
        "diffs": [
            {
                "source": {"toString": "src/Widget.java"},
                "destination": {"toString": "src/Widget.java"},
                "hunks": [
                    {
                        "sourceLine": 10,
                        "sourceSpan": 3,
                        "destinationLine": 10,
                        "destinationSpan": 4,
                        "segments": [
                            {
                                "type": "CONTEXT",
                                "lines": [{"line": "context"}],
                            },
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "old"}],
                            },
                            {
                                "type": "ADDED",
                                "lines": [
                                    {"line": "new"},
                                    {"line": "more"},
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "source": {"toString": "src/Legacy.java"},
                "destination": None,
                "hunks": [
                    {
                        "sourceLine": 1,
                        "sourceSpan": 1,
                        "destinationLine": 0,
                        "destinationSpan": 0,
                        "segments": [
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "deleted"}],
                            }
                        ],
                    }
                ],
            },
        ]
    }


# Hand-derived from the documented review format: header, blank line, file
# header pair, hunk range header, then one prefix per segment line.
LITERAL_DIFF_TEXT = (
    "# Bitbucket PR diff review "
    "(context=2; whitespace=ignore-all; not a patch)\n"
    "\n"
    "--- a/src/Widget.java\n"
    "+++ b/src/Widget.java\n"
    "@@ -10,3 +10,4 @@\n"
    " context\n"
    "-old\n"
    "+new\n"
    "+more\n"
    "--- a/src/Legacy.java\n"
    "+++ /dev/null\n"
    "@@ -1,1 +0,0 @@\n"
    "-deleted\n"
)


def page(values: list[object], *, limit: int) -> dict[str, object]:
    """Return a terminal Bitbucket page."""
    return {
        "values": values,
        "size": len(values),
        "limit": limit,
        "start": 0,
        "isLastPage": True,
    }


def stub_collect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    info: object | None = None,
    commits: object | None = None,
    files: object | None = None,
    diff: object | None = None,
) -> list[Call]:
    """Replace the four public adapters with recorders.

    A result that is an exception instance is raised instead of returned, which
    makes a later constituent failure easy to model without real I/O.
    """
    results: dict[str, object] = {
        "pr": pr_body() if info is None else info,
        "commits": [commit_row()] if commits is None else commits,
        "files": default_files() if files is None else files,
        "diff": diff_body() if diff is None else diff,
    }
    functions = {
        "pr": "get_pull_request",
        "commits": "list_pull_request_commits",
        "files": "list_pull_request_files",
        "diff": "get_pull_request_diff",
    }
    calls: list[Call] = []

    def make(name: str) -> Any:
        result = results[name]

        def fake(*args: object, **kwargs: object) -> object:
            calls.append((name, args, dict(kwargs)))
            if isinstance(result, BaseException):
                raise result
            return result

        return fake

    for name, function in functions.items():
        monkeypatch.setattr(bitbucket, function, make(name))
    # Heuristic source reads are separate reads; return empty source unless a
    # test installs its own fixture.
    monkeypatch.setattr(
        bitbucket, "get_repository_file", lambda *args, **kwargs: ""
    )
    return calls


def jira_issue() -> dict[str, object]:
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


def stub_jira(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issue: object | None = None,
    error: BaseException | None = None,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(
        base_url: str,
        key: str,
        *,
        token: str,
        allow_http_loopback: bool = False,
    ) -> dict[str, object]:
        calls.append(
            {
                "base_url": base_url,
                "key": key,
                "token": token,
                "allow_http_loopback": allow_http_loopback,
            }
        )
        if error is not None:
            raise error
        if isinstance(issue, dict):
            return cast(dict[str, object], issue)
        return jira_issue()

    monkeypatch.setattr(jira, "get_issue", fake)
    return calls


def java_files() -> list[dict[str, object]]:
    return [
        file_row("src/main/java/demo/Widget.java"),
        file_row("src/test/java/demo/WidgetTest.java"),
    ]


def java_sources() -> dict[tuple[str, str], str]:
    before = "\n".join(
        [
            "class Widget {",
            "    public void run() {",
            '        System.out.print("removed");',
            "    }",
            "}",
            "",
        ]
    )
    after = "\n".join(
        [
            "class Widget {",
            "    public void run() {",
            "        TODO fix;",
            '        System.out.print("x");',
            "    }",
            "}",
            "",
        ]
    )
    return {
        ("src/main/java/demo/Widget.java", TO_HASH): before,
        ("src/main/java/demo/Widget.java", FROM_HASH): after,
    }


def java_diff() -> dict[str, object]:
    return {
        "diffs": [
            {
                "source": {"toString": "src/main/java/demo/Widget.java"},
                "destination": {"toString": "src/main/java/demo/Widget.java"},
                "hunks": [
                    {
                        "sourceLine": 2,
                        "sourceSpan": 3,
                        "destinationLine": 2,
                        "destinationSpan": 4,
                        "segments": [
                            {
                                "type": "CONTEXT",
                                "lines": [{"line": "    public void run() {"}],
                            },
                            {
                                "type": "REMOVED",
                                "lines": [
                                    {"line": '        System.out.print("removed");'}
                                ],
                            },
                            {
                                "type": "ADDED",
                                "lines": [{"line": "        TODO fix;"}],
                            },
                            {
                                "type": "ADDED",
                                "lines": [{"line": '        System.out.print("x");'}],
                            },
                            {
                                "type": "CONTEXT",
                                "lines": [{"line": "    }"}],
                            },
                        ],
                    }
                ],
            }
        ]
    }


def stub_repository_files(
    monkeypatch: pytest.MonkeyPatch,
    sources: dict[tuple[str, str], str],
    *,
    failing: set[tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    failures = failing or set()

    def fake(
        base_url: str,
        repo: str,
        path: str,
        *,
        token: str,
        at: str = "master",
        allow_http_loopback: bool = False,
    ) -> str:
        calls.append(
            {
                "base_url": base_url,
                "repo": repo,
                "path": path,
                "at": at,
                "token": token,
            }
        )
        if (path, at) in failures or (path, at) not in sources:
            raise AtlaWireError("HTTP 404: request failed.")
        return sources[(path, at)]

    monkeypatch.setattr(bitbucket, "get_repository_file", fake)
    return calls


def test_public_interface_matches_the_documented_signature() -> None:
    parameters = inspect.signature(pr_review.collect_pr_review).parameters

    assert list(parameters) == [
        "base_url",
        "repo",
        "pr_id",
        "token",
        "include_diff",
        "context",
        "allow_http_loopback",
        "jira_base_url",
        "jira_token",
    ]
    assert parameters["token"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["include_diff"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["context"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["allow_http_loopback"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["jira_base_url"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["jira_token"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["include_diff"].default is True
    assert parameters["context"].default == 2
    assert parameters["allow_http_loopback"].default is False
    assert parameters["jira_base_url"].default is None
    assert parameters["jira_token"].default is None


def test_collect_uses_only_the_four_public_adapter_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert [name for name, _, _ in calls] == ["pr", "commits", "files", "diff"]
    assert calls[0][1] == (BASE, REPO, PR_ID)
    assert calls[0][2] == {"token": TOKEN, "allow_http_loopback": False}
    assert calls[1][1] == (BASE, REPO, PR_ID)
    assert calls[1][2] == {"token": TOKEN, "allow_http_loopback": False}
    assert calls[2][1] == (BASE, REPO, PR_ID)
    assert calls[2][2] == {"token": TOKEN, "allow_http_loopback": False}
    assert calls[3][1] == (BASE, REPO, PR_ID)
    assert calls[3][2] == {
        "token": TOKEN,
        "context": 2,
        "allow_http_loopback": False,
    }
    assert packet["profile"]["name"] == "read-only-review"
    # The default fixture intentionally has one file missing from the diff.
    assert packet["profile"]["partial"] is True
    assert any(
        "no matching diff entry" in reason
        for reason in packet["profile"]["partial_reasons"]
    )
    assert packet["profile"]["deferred"] == []
    assert any("heuristic" in item for item in packet["profile"]["limitations"])


def test_packet_preserves_projected_pr_commit_and_file_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["repo"] == REPO
    assert packet["pr_id"] == PR_ID
    assert packet["title"] == "Example review"
    assert packet["description"] == "Purpose and risk."
    assert packet["description_truncated"] is False
    assert packet["author"] == "Alice Reviewer"
    assert packet["state"] == "OPEN"
    assert packet["from_branch"] == "feature"
    assert packet["to_branch"] == "main"
    assert packet["from_hash"] == FROM_HASH
    assert packet["to_hash"] == TO_HASH
    assert packet["created"] == 1_700_000_000_000
    assert packet["updated"] == 1_700_000_001_000
    assert packet["commits"] == [
        {
            "hash": f"{1:040x}",
            "date": "2023-11-14 22:13",
            "author": "alice",
            "message": "Change",
            "message_truncated": False,
        }
    ]
    assert packet["commits_total"] == 1
    assert packet["commits_truncated"] is False
    assert packet["files"] == [
        {
            "path": "src/App.txt",
            "type": "MODIFY",
            "node": "FILE",
            "added": 2,
            "removed": 1,
            "lines_source": "server-diff",
            "test": False,
            "links": expected_links("src/App.txt"),
        },
        {
            "path": "docs/README.md",
            "type": "MODIFY",
            "node": "FILE",
            "added": 0,
            "removed": 0,
            "lines_source": "server-diff-no-textual-hunks",
            "test": False,
            "links": expected_links("docs/README.md"),
        },
        {
            "path": "images/logo.png",
            "type": "MODIFY",
            "node": "FILE",
            "added": None,
            "removed": None,
            "lines_source": "server-diff-missing-file",
            "test": False,
            "links": expected_links("images/logo.png"),
        },
    ]
    text = cast(str, packet["diff"]["text"])
    assert "--- a/src/App.txt" in text
    assert "+++ b/src/App.txt" in text
    assert "-old" in text
    assert "+new" in text
    assert "+more" in text
    assert "(no textual hunks in this file)" in text
    assert packet["diff"]["text_bytes"] == len(text.encode("utf-8"))
    assert packet["diff"]["text_returned_bytes"] == len(text.encode("utf-8"))
    assert packet["diff"]["text_truncated"] is False
    assert packet["links"] == PR_LINKS
    assert packet["ticket"] is None
    assert packet["checks"]["heuristic"] is True
    assert "evil.invalid" not in json.dumps(packet)


def test_diff_text_matches_the_shared_in_package_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    expected = bitbucket._render_pull_request_diff_text(
        diff_body(), context=2
    )
    assert cast(str, packet["diff"]["text"]) == expected


def test_representative_diff_matches_the_literal_documented_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The expected text is hand-derived from the documented review format."""
    stub_collect(
        monkeypatch,
        files=[
            file_row("src/Widget.java"),
            file_row("src/Legacy.java", change_type="DELETE"),
        ],
        diff=literal_diff(),
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["diff"]["text"] == LITERAL_DIFF_TEXT
    assert packet["diff"]["text_truncated"] is False
    widget, legacy = packet["files"]
    assert (widget["added"], widget["removed"]) == (2, 1)
    assert (legacy["added"], legacy["removed"]) == (0, 1)
    assert packet["diff"]["added"] == 2
    assert packet["diff"]["removed"] == 2
    assert packet["diff"]["files_with_changes"] == 2
    assert packet["diff"]["counts_complete"] is True


def test_diff_text_is_taken_from_the_shared_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[object, int]] = []

    def fake_renderer(value: object, *, context: int) -> str:
        recorded.append((value, context))
        return "SHARED-RENDERER-OUTPUT\n"

    monkeypatch.setattr(
        bitbucket, "_render_pull_request_diff_text", fake_renderer
    )
    stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["diff"]["text"] == "SHARED-RENDERER-OUTPUT\n"
    assert recorded == [(diff_body(), 2)]


def test_counts_are_derived_from_the_diff_and_missing_files_stay_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["diff"]["requested"] is True
    assert packet["diff"]["context"] == 2
    assert packet["diff"]["files_with_changes"] == 2
    assert packet["diff"]["added"] == 2
    assert packet["diff"]["removed"] == 1
    assert packet["diff"]["counts_complete"] is False
    assert packet["diff"]["declared_truncation_checked"] is True
    # No declared truncation flag means the adapter accepted the response. It
    # still does not prove that the server sent everything.
    assert packet["diff"]["proven_complete"] is False


def test_no_diff_makes_three_reads_and_never_reports_zero_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(
        monkeypatch, diff=AssertionError("the diff adapter must not be called")
    )

    packet = pr_review.collect_pr_review(
        BASE, REPO, PR_ID, token=TOKEN, include_diff=False
    )

    assert [name for name, _, _ in calls] == ["pr", "commits", "files"]
    for row in packet["files"]:
        assert row["added"] is None
        assert row["removed"] is None
        assert row["lines_source"] == "not-requested"
    assert packet["diff"] == {
        "requested": False,
        "context": 2,
        "text": None,
        "text_bytes": 0,
        "text_returned_bytes": 0,
        "text_truncated": False,
        "declared_truncation_checked": False,
        "proven_complete": False,
        "files_with_changes": None,
        "added": None,
        "removed": None,
        "counts_complete": None,
    }
    assert packet["checks"]["diff_requested"] is False
    assert packet["checks"]["analysis_complete"] is None
    assert packet["checks"]["symbols"] == []
    assert packet["profile"]["partial"] is True
    assert any(
        "intentionally omitted" in reason
        for reason in packet["profile"]["partial_reasons"]
    )


def test_packet_schema_is_stable_with_and_without_the_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch)

    with_diff = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    without_diff = pr_review.collect_pr_review(
        BASE, REPO, PR_ID, token=TOKEN, include_diff=False
    )

    assert set(with_diff) == set(without_diff)
    assert set(with_diff["diff"]) == set(without_diff["diff"])
    assert set(with_diff["files"][0]) == set(without_diff["files"][0])
    assert set(with_diff["commits"][0]) == set(without_diff["commits"][0])
    assert set(with_diff["profile"]) == set(without_diff["profile"])
    assert json.loads(json.dumps(with_diff)) == with_diff
    assert json.loads(json.dumps(without_diff)) == without_diff


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("pr", ["pr"]),
        ("commits", ["pr", "commits"]),
        ("files", ["pr", "commits", "files"]),
        ("diff", ["pr", "commits", "files", "diff"]),
    ],
    ids=["pr", "commits", "files", "diff"],
)
def test_a_failed_read_stops_later_reads_and_returns_no_packet(
    monkeypatch: pytest.MonkeyPatch, failure: str, expected: list[str]
) -> None:
    parameter = "info" if failure == "pr" else failure
    calls = stub_collect(
        monkeypatch,
        **cast(
            Any,
            {parameter: AtlaWireError("HTTP 500: request failed.")},
        ),
    )

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert [name for name, _, _ in calls] == expected


def test_an_empty_diff_response_never_becomes_zero_line_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch, diff={"diffs": []})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    for row in packet["files"]:
        assert row["added"] is None
        assert row["removed"] is None
        assert row["lines_source"] == "server-diff-missing-file"
    assert packet["diff"]["files_with_changes"] == 0
    assert packet["diff"]["added"] is None
    assert packet["diff"]["removed"] is None
    assert packet["diff"]["counts_complete"] is False
    assert "(no textual hunks in the response)" in cast(
        str, packet["diff"]["text"]
    )


def test_renamed_and_deleted_files_use_the_path_the_server_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diff = {
        "diffs": [
            {
                "source": {"toString": "old/name.py"},
                "destination": {"toString": "new/name.py"},
                "hunks": [
                    hunk(
                        [
                            {
                                "type": "ADDED",
                                "lines": [{"line": "new"}],
                            }
                        ]
                    )
                ],
            },
            {
                "source": {"toString": "gone.txt"},
                "destination": None,
                "hunks": [
                    hunk(
                        [
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "a"}, {"line": "b"}],
                            }
                        ]
                    )
                ],
            },
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row("new/name.py"), file_row("gone.txt")],
        diff=diff,
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    renamed, deleted = packet["files"]
    assert (renamed["added"], renamed["removed"]) == (1, 0)
    assert (deleted["added"], deleted["removed"]) == (0, 2)
    text = cast(str, packet["diff"]["text"])
    assert "--- a/old/name.py" in text
    assert "+++ b/new/name.py" in text
    assert "+++ /dev/null" in text
    assert packet["diff"]["added"] == 1
    assert packet["diff"]["removed"] == 2
    assert packet["diff"]["counts_complete"] is True


def test_control_bidi_and_backslash_characters_are_escaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diff = {
        "diffs": [
            {
                "destination": {"toString": "src/App.txt"},
                "hunks": [
                    hunk(
                        [
                            {
                                "type": "ADDED",
                                "lines": [
                                    {"line": "a\x1bb\u202eC:\\temp"}
                                ],
                            }
                        ]
                    )
                ],
            }
        ]
    }
    stub_collect(monkeypatch, files=[file_row("src/App.txt")], diff=diff)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    text = cast(str, packet["diff"]["text"])
    assert "a\\x1bb\\u202eC:\\\\temp" in text
    assert "\x1b" not in text
    assert "\u202e" not in text


def test_packet_bounds_rows_and_long_text_with_explicit_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = [
        commit_row(index, message="m" * 20_000)
        for index in range(1, pr_review.COMMIT_LIMIT + 101)
    ]
    diff = {
        "diffs": [
            {
                "source": {"toString": "src/App.txt"},
                "destination": {"toString": "src/App.txt"},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 300,
                        "segments": [
                            {
                                "type": "ADDED",
                                "lines": [
                                    {"line": "x" * 1000} for _ in range(300)
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        info=pr_body(description="d" * 100_000),
        commits=commits,
        files=[file_row("src/App.txt")],
        diff=diff,
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["commits_total"] == pr_review.COMMIT_LIMIT + 100
    assert len(packet["commits"]) == pr_review.COMMIT_LIMIT
    assert packet["commits_truncated"] is True
    for row in packet["commits"]:
        assert len(row["message"]) == pr_review.COMMIT_MESSAGE_LIMIT
        assert row["message_truncated"] is True
    assert len(packet["description"]) == pr_review.DESCRIPTION_LIMIT
    assert packet["description_truncated"] is True
    assert packet["files_truncated"] is False
    assert packet["files"][0]["added"] == 300
    assert packet["files"][0]["removed"] == 0
    assert packet["files"][0]["lines_source"] == "server-diff"
    assert packet["diff"]["text_truncated"] is True
    assert packet["diff"]["text_bytes"] > pr_review.DIFF_TEXT_BYTES_LIMIT
    assert (
        packet["diff"]["text_returned_bytes"]
        <= pr_review.DIFF_TEXT_BYTES_LIMIT
    )
    assert cast(str, packet["diff"]["text"]).endswith("\n")
    assert packet["diff"]["added"] == 300
    assert packet["diff"]["counts_complete"] is True
    assert packet["profile"]["partial"] is True
    reasons = packet["profile"]["partial_reasons"]
    assert any("description" in reason.lower() for reason in reasons)
    assert any("commit" in reason.lower() for reason in reasons)
    assert any("diff text" in reason.lower() for reason in reasons)


def test_context_is_forwarded_once_to_the_diff_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(
        BASE, REPO, PR_ID, token=TOKEN, context=0
    )

    assert calls[3][2]["context"] == 0
    assert packet["diff"]["context"] == 0
    assert "context=0" in cast(str, packet["diff"]["text"])


INVALID_ARGUMENTS: list[tuple[dict[str, object], str]] = [
    ({"base_url": "http://bitbucket.example.invalid/scm"}, "base URL"),
    (
        {"base_url": "https://user:secret@bitbucket.example.invalid/scm"},
        "base URL",
    ),
    ({"base_url": "https://bitbucket.example.invalid/scm?x=1"}, "base URL"),
    ({"base_url": None}, "base URL"),
    ({"repo": "DEMO"}, "PROJECT/slug"),
    ({"repo": ""}, "PROJECT/slug"),
    ({"repo": "DEMO/a/b"}, "PROJECT/slug"),
    ({"repo": "DEMO/wid gets"}, "PROJECT/slug"),
    ({"repo": "DEMO\\widgets"}, "PROJECT/slug"),
    ({"pr_id": "0"}, "pull request ID"),
    ({"pr_id": "01"}, "pull request ID"),
    ({"pr_id": "+1"}, "pull request ID"),
    ({"pr_id": " 1"}, "pull request ID"),
    ({"pr_id": True}, "pull request ID"),
    ({"pr_id": False}, "pull request ID"),
    ({"pr_id": 0}, "pull request ID"),
    ({"pr_id": 2**63}, "pull request ID"),
    ({"pr_id": None}, "pull request ID"),
    ({"context": -1}, "diff context"),
    ({"context": 101}, "diff context"),
    ({"context": True}, "diff context"),
    ({"context": "2"}, "diff context"),
    ({"include_diff": 1}, "flag must be a boolean"),
    ({"include_diff": None}, "flag must be a boolean"),
    ({"allow_http_loopback": "yes"}, "flag must be a boolean"),
    ({"token": ""}, "bearer token"),
    ({"token": "bad token"}, "bearer token"),
    ({"token": None}, "bearer token"),
]


@pytest.mark.parametrize(
    ("overrides", "message"),
    INVALID_ARGUMENTS,
    ids=[
        f"{key}-{index}"
        for index, (overrides, _) in enumerate(INVALID_ARGUMENTS)
        for key in overrides
    ],
)
def test_invalid_arguments_fail_before_the_first_read(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("an adapter ran before argument validation")

    for name in (
        "get_pull_request",
        "list_pull_request_commits",
        "list_pull_request_files",
        "get_pull_request_diff",
    ):
        monkeypatch.setattr(bitbucket, name, forbidden)

    arguments: dict[str, object] = {
        "base_url": BASE,
        "repo": REPO,
        "pr_id": PR_ID,
        "token": TOKEN,
    }
    arguments.update(overrides)

    with pytest.raises(AtlaWireError, match=message):
        pr_review.collect_pr_review(**cast(Any, arguments))


@pytest.mark.parametrize("argument", ["refresh", "pull", "root"])
def test_removed_bbk_arguments_are_rejected_by_the_signature(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("an adapter ran before argument binding")

    for name in (
        "get_pull_request",
        "list_pull_request_commits",
        "list_pull_request_files",
        "get_pull_request_diff",
    ):
        monkeypatch.setattr(bitbucket, name, forbidden)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        pr_review.collect_pr_review(
            BASE,
            REPO,
            PR_ID,
            token=TOKEN,
            **cast(Any, {argument: True}),
        )


def test_http_loopback_requires_the_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("an adapter ran before base URL validation")

    monkeypatch.setattr(bitbucket, "get_pull_request", forbidden)

    with pytest.raises(AtlaWireError, match="base URL"):
        pr_review.collect_pr_review(LOOPBACK, REPO, PR_ID, token=TOKEN)

    calls = stub_collect(monkeypatch)
    packet = pr_review.collect_pr_review(
        LOOPBACK, REPO, PR_ID, token=TOKEN, allow_http_loopback=True
    )

    assert packet["pr_id"] == PR_ID
    assert calls[0][1] == (LOOPBACK, REPO, PR_ID)
    assert calls[0][2]["allow_http_loopback"] is True


def test_a_trailing_slash_and_string_id_are_canonicalised_before_the_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(
        BASE + "/", "~user/my.repo", "7", token=TOKEN
    )

    assert packet["repo"] == "~user/my.repo"
    assert packet["pr_id"] == 7
    assert calls[0][1] == (BASE, "~user/my.repo", 7)
    assert all(call[1][0] == BASE for call in calls)


MALFORMED_DIFFS: list[tuple[object, str]] = [
    ({}, "diffs array"),
    ({"diffs": {}}, "diffs array"),
    ({"diffs": [7]}, "diff object"),
    ({"diffs": [{"hunks": []}]}, "must declare a path"),
    (
        {"diffs": [{"destination": {"toString": "a"}, "hunks": {}}]},
        "Invalid hunks",
    ),
    (
        {"diffs": [{"destination": {"toString": "a"}, "hunks": [7]}]},
        "hunk object",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [{"segments": []}],
                }
            ]
        },
        "line range",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [
                        {
                            "sourceLine": 0,
                            "sourceSpan": 0,
                            "destinationLine": 1,
                            "destinationSpan": 1,
                        }
                    ],
                }
            ]
        },
        "Invalid segments",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [
                        hunk(
                            [
                                {
                                    "type": "UNKNOWN",
                                    "lines": [{"line": "x"}],
                                }
                            ]
                        )
                    ],
                }
            ]
        },
        "Unsupported type",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [hunk([{"type": "ADDED"}])],
                }
            ]
        },
        "Invalid lines",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [hunk([{"type": "ADDED", "lines": [7]}])],
                }
            ]
        },
        "line object",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [
                        hunk([{"type": "ADDED", "lines": [{"line": 7}]}])
                    ],
                }
            ]
        },
        "Invalid text",
    ),
    (
        {
            "diffs": [
                {
                    "destination": {"toString": "a"},
                    "hunks": [
                        hunk(
                            [
                                {
                                    "type": "ADDED",
                                    "lines": [{"line": "a\nb"}],
                                }
                            ]
                        )
                    ],
                }
            ]
        },
        "line break",
    ),
]


@pytest.mark.parametrize(
    ("diff", "message"),
    MALFORMED_DIFFS,
    ids=[message for _, message in MALFORMED_DIFFS],
)
def test_malformed_diff_projection_rejects_the_whole_packet(
    monkeypatch: pytest.MonkeyPatch, diff: object, message: str
) -> None:
    stub_collect(monkeypatch, diff=diff)

    with pytest.raises(AtlaWireError, match=message):
        pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)


def test_module_never_imports_process_git_or_filesystem_helpers() -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(
        {"git", "os", "pathlib", "shutil", "subprocess", "tempfile"}
    )
    assert ".write(" not in source
    assert "open(" not in source


def test_module_does_not_reimplement_the_shared_diff_renderer() -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")

    for helper in (
        "_change_path",
        "_diff_file",
        "_diff_side",
        "_hunk_text",
        "_range_number",
        "_render_pull_request_diff",
        "_safe_diff_text",
    ):
        assert f"def {helper}(" not in source
    assert "_DIFF_SEGMENT_PREFIXES" not in source
    assert "_DIFF_UNSAFE" not in source


def test_ambient_product_settings_and_repo_root_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BBK_REPO_ROOT", "not-a-repository")
    monkeypatch.setenv("GIT_DIR", "not-a-repository")
    monkeypatch.setenv("ATLAWIRE_BITBUCKET_URL", "https://wrong.invalid")
    monkeypatch.setenv("ATLAWIRE_BITBUCKET_TOKEN", "wrong-ambient-token")
    calls = stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["repo"] == REPO
    assert calls[0][1][0] == BASE
    assert calls[0][2]["token"] == TOKEN


def test_token_and_response_links_never_reach_the_packet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    serialized = json.dumps(packet)
    assert TOKEN not in serialized
    assert "evil.invalid" not in serialized
    assert packet["links"] == PR_LINKS
    assert calls[0][2]["token"] == TOKEN


@responses.activate
def test_real_transport_makes_exactly_four_authenticated_gets() -> None:
    responses.get(PR_URL, json=pr_body())
    responses.get(
        COMMITS_URL,
        json=page([commit_payload()], limit=100),
    )
    responses.get(
        CHANGES_URL,
        json=page(
            [
                {
                    "path": {"toString": "src/App.txt"},
                    "type": "MODIFY",
                    "nodeType": "FILE",
                    "links": {"self": [{"href": "https://evil.invalid/file"}]},
                }
            ],
            limit=1000,
        ),
    )
    responses.get(DIFF_URL, json=diff_body())

    packet = pr_review.collect_pr_review(BASE, REPO, "7", token=TOKEN)

    assert packet["pr_id"] == 7
    assert packet["files"][0]["path"] == "src/App.txt"
    assert packet["files"][0]["added"] == 2
    assert packet["diff"]["proven_complete"] is False
    assert "evil.invalid" not in json.dumps(packet)
    assert len(responses.calls) == 4
    expected: list[tuple[str, dict[str, list[str]]]] = [
        (PR_URL, {}),
        (COMMITS_URL, {"start": ["0"], "limit": ["100"]}),
        (CHANGES_URL, {"limit": ["1000"]}),
        (DIFF_URL, {
            "contextLines": ["2"],
            "whitespace": ["ignore-all"],
            "withComments": ["false"],
        }),
    ]
    for call, (url, params) in zip(responses.calls, expected, strict=True):
        request = call.request
        assert request.method == "GET"
        assert request.url.split("?")[0] == url
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        query = parse_qs(urlsplit(request.url).query, keep_blank_values=True)
        assert query == params


@responses.activate
def test_a_declared_truncated_diff_rejects_the_whole_packet() -> None:
    responses.get(PR_URL, json=pr_body())
    responses.get(COMMITS_URL, json=page([commit_payload()], limit=100))
    responses.get(
        CHANGES_URL,
        json=page(
            [
                {
                    "path": {"toString": "src/App.txt"},
                    "type": "MODIFY",
                    "nodeType": "FILE",
                }
            ],
            limit=1000,
        ),
    )
    responses.get(DIFF_URL, json={"diffs": [], "truncated": True})

    with pytest.raises(AtlaWireError, match="truncated"):
        pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert len(responses.calls) == 4


@responses.activate
def test_a_failing_diff_read_rejects_the_packet_without_emitting_it() -> None:
    responses.get(PR_URL, json=pr_body())
    responses.get(COMMITS_URL, json=page([commit_payload()], limit=100))
    responses.get(
        CHANGES_URL,
        json=page(
            [
                {
                    "path": {"toString": "src/App.txt"},
                    "type": "MODIFY",
                    "nodeType": "FILE",
                }
            ],
            limit=1000,
        ),
    )
    responses.get(DIFF_URL, status=500, json={"message": "boom"})

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert len(responses.calls) == 4


def test_detected_ticket_without_jira_pair_is_visibly_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
    )
    jira_calls = stub_jira(monkeypatch)
    monkeypatch.setenv("ATLAWIRE_JIRA_URL", JIRA_BASE)
    monkeypatch.setenv("ATLAWIRE_JIRA_TOKEN", JIRA_TOKEN)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["ticket"] is not None
    assert packet["ticket"]["key"] == "DEMO-42"
    assert packet["ticket"]["verified"] is False
    assert "not supplied" in (packet["ticket"]["error"] or "")
    assert jira_calls == []
    markdown = pr_review.render_markdown(packet)
    assert "DEMO-42" in markdown
    assert "unverified" in markdown
    assert "Heuristic checks" in markdown


def test_ticket_enrichment_uses_only_the_explicit_jira_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
    )
    jira_calls = stub_jira(monkeypatch)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    ticket = packet["ticket"]
    assert ticket is not None
    assert ticket["verified"] is True
    assert ticket["heuristic"] is True
    assert ticket["key"] == "DEMO-42"
    assert ticket["summary"] == "Do the thing"
    assert ticket["status"] == "Open"
    assert ticket["type"] == "Task"
    assert ticket["priority"] == "High"
    assert ticket["assignee"] == "Bob"
    assert ticket["reporter"] == "Alice"
    assert ticket["url"] == f"{JIRA_BASE}/browse/DEMO-42"
    assert "Do" in ticket["description"]
    assert "thing" in ticket["description"]
    assert "<p>" not in ticket["description"]
    assert jira_calls == [
        {
            "base_url": JIRA_BASE,
            "key": "DEMO-42",
            "token": JIRA_TOKEN,
            "allow_http_loopback": False,
        }
    ]
    assert all(call[2]["token"] == TOKEN for call in calls)
    serialized = json.dumps(packet)
    assert TOKEN not in serialized
    assert JIRA_TOKEN not in serialized


def test_jira_failure_keeps_the_ticket_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
    )
    stub_jira(
        monkeypatch,
        error=AtlaWireError("HTTP 401: authentication rejected."),
    )

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    assert packet["ticket"] is not None
    assert packet["ticket"]["verified"] is False
    assert "HTTP 401" in (packet["ticket"]["error"] or "")
    assert packet["checks"]["heuristic"] is True
    assert "unverified" in pr_review.render_markdown(packet)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jira_base_url": JIRA_BASE}, "supplied together"),
        ({"jira_token": JIRA_TOKEN}, "supplied together"),
        (
            {"jira_base_url": "http://jira.example.invalid", "jira_token": JIRA_TOKEN},
            "base URL",
        ),
        (
            {"jira_base_url": JIRA_BASE, "jira_token": "bad token"},
            "bearer token",
        ),
    ],
    ids=["base-only", "token-only", "bad-base", "bad-token"],
)
def test_invalid_jira_pair_is_rejected_before_bitbucket(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("Bitbucket adapter ran before Jira validation")

    for name in (
        "get_pull_request",
        "list_pull_request_commits",
        "list_pull_request_files",
        "get_pull_request_diff",
    ):
        monkeypatch.setattr(bitbucket, name, forbidden)
    arguments: dict[str, object] = {
        "base_url": BASE,
        "repo": REPO,
        "pr_id": PR_ID,
        "token": TOKEN,
    }
    arguments.update(overrides)

    with pytest.raises(AtlaWireError, match=message):
        pr_review.collect_pr_review(**cast(Any, arguments))


def test_no_ticket_does_not_require_or_call_jira(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(monkeypatch)
    jira_calls = stub_jira(monkeypatch)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    assert packet["ticket"] is None
    assert jira_calls == []


@pytest.mark.parametrize(
    ("from_branch", "commit_message", "title", "expected"),
    [
        ("feature/UTF-8", "DEMO-2 change", "DEMO-3", "DEMO-2"),
        ("feature/DEMO-1", "DEMO-2 change", "DEMO-3", "DEMO-1"),
        ("feature/none", "DEMO-2 change", "DEMO-3", "DEMO-2"),
        ("feature/none", "plain", "DEMO-3", "DEMO-3"),
    ],
    ids=["denylist", "branch", "commit", "title"],
)
def test_ticket_detection_priority_and_denylist(
    monkeypatch: pytest.MonkeyPatch,
    from_branch: str,
    commit_message: str,
    title: str,
    expected: str,
) -> None:
    stub_collect(
        monkeypatch,
        info=pr_body(
            title=title,
            fromRef={"displayId": from_branch, "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        commits=[commit_row(message=commit_message)],
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["ticket"] is not None
    assert packet["ticket"]["key"] == expected


def test_browser_links_use_the_correct_side_and_encode_the_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/a b#c.txt"
    diff = {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 1,
                        "sourceSpan": 1,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "REMOVED", "lines": [{"line": "old"}]},
                            {"type": "ADDED", "lines": [{"line": "new"}]},
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={
                "displayId": "feature",
                "latestCommit": FROM_HASH,
                "repository": {
                    "project": {"key": "FORK"},
                    "slug": "source-repo",
                },
            },
            toRef={
                "displayId": "main",
                "latestCommit": TO_HASH,
                "repository": {
                    "project": {"key": "DEMO"},
                    "slug": "widgets",
                },
            },
        ),
        files=[file_row(path)],
        diff=diff,
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    links = packet["files"][0]["links"]
    assert links["before"] == (
        f"{BASE}/projects/DEMO/repos/widgets/browse/src/a%20b%23c.txt"
        f"?at={TO_HASH}"
    )
    assert links["after"] == (
        f"{BASE}/projects/FORK/repos/source-repo/browse/src/a%20b%23c.txt"
        f"?at={FROM_HASH}"
    )
    assert links["diff"] == (
        f"{BASE}/projects/DEMO/repos/widgets/pull-requests/7/diff"
        "#src/a%20b%23c.txt"
    )
    assert "{pr}" not in json.dumps(packet)


def test_heuristic_checks_identify_tests_symbols_and_red_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        files=java_files(),
        diff=java_diff(),
    )
    reads = stub_repository_files(monkeypatch, java_sources())

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    checks = packet["checks"]
    assert checks["heuristic"] is True
    assert checks["test_files"] == 1
    assert checks["test_names"] == ["src/test/java/demo/WidgetTest.java"]
    assert checks["java_files"] == 2
    assert checks["methods_touched"] == 1
    assert checks["methods_without_javadoc"] == 1
    assert checks["types_without_javadoc"] == 1
    assert checks["analysis_complete"] is True
    assert [flag["rule"] for flag in checks["red_flags"]] == [
        "TODO/FIXME",
        "System.out.print",
    ]
    assert checks["red_flags"][0]["line"] == 3
    assert checks["red_flags"][0]["file"] == "src/main/java/demo/Widget.java"
    assert any(
        symbol["name"] == "run"
        and symbol["kind"] == "method"
        and symbol["status"] == "modified"
        for symbol in checks["symbols"]
    )
    assert all(call["token"] == TOKEN for call in reads)
    assert all(call["path"] == "src/main/java/demo/Widget.java" for call in reads)
    assert {call["at"] for call in reads} == {FROM_HASH, TO_HASH}


def test_heuristic_source_failure_is_visible_and_not_invented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        files=java_files(),
        diff=java_diff(),
    )
    stub_repository_files(
        monkeypatch,
        java_sources(),
        failing={("src/main/java/demo/Widget.java", FROM_HASH)},
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    checks = packet["checks"]
    assert checks["analysis_complete"] is False
    assert checks["unavailable_files"]
    assert checks["symbols"] == []
    assert packet["profile"]["partial"] is True
    assert any(
        "unavailable" in reason.lower()
        for reason in packet["profile"]["partial_reasons"]
    )
    assert "incomplete" in pr_review.render_markdown(packet)


def test_abstract_declaration_is_not_stretched_to_end_of_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/main/java/demo/Base.java"
    source = "\n".join(
        [
            "abstract class Base {",
            "    abstract void run();",
            "    void other() {",
            "        work();",
            "    }",
            "}",
            "",
        ]
    )
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 6,
                        "segments": [
                            {
                                "type": "ADDED",
                                "lines": [
                                    {"line": "abstract class Base {"},
                                    {"line": "    abstract void run();"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )
    stub_repository_files(monkeypatch, {(path, FROM_HASH): source})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    symbol = next(
        item
        for item in packet["checks"]["symbols"]
        if item["name"] == "run" and item["kind"] == "method"
    )
    assert symbol["lines_after"] == 1
    assert packet["files"][0]["links"]["before"] == ""
    assert packet["files"][0]["links"]["after"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/test/java/demo/A.java", True),
        ("src/it/demo/A.kt", True),
        ("tests/helpers.py", True),
        ("src/main/java/demo/ATest.java", True),
        ("src/main/kotlin/demo/Spec.kt", True),
        ("src/main/java/demo/App.java", False),
        ("docs/contest.txt", False),
    ],
)
def test_test_file_identification(path: str, expected: bool) -> None:
    assert pr_review.is_test_path(path) is expected


def test_markdown_reports_ticket_links_heuristics_and_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=java_files(),
        diff=java_diff(),
    )
    stub_jira(monkeypatch)
    stub_repository_files(monkeypatch, java_sources())

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )
    markdown = pr_review.render_markdown(packet)

    assert "## Ticket `DEMO-42`" in markdown
    assert "Do the thing" in markdown
    assert "Heuristic checks" in markdown
    assert "heuristic" in markdown
    assert "TODO/FIXME" in markdown
    assert "overview" in markdown
    assert "<details><summary>diff</summary>" in markdown
    assert "WidgetTest.java" in markdown


def test_ticket_description_falls_back_to_fenced_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = jira_issue()
    issue["renderedFields"] = {}
    fields = issue["fields"]
    assert isinstance(fields, dict)
    fields["description"] = "<b>raw</b>"
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
    )
    stub_jira(monkeypatch, issue=issue)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    ticket = packet["ticket"]
    assert ticket is not None
    assert ticket["description"].startswith("```text")
    assert "<b>raw</b>" in ticket["description"]
    assert not ticket["description_truncated"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://bb.example/projects/DEMO/repos/widgets/pull-requests/7/overview",
            ("DEMO/widgets", 7),
        ),
        ("/projects/~user/repos/my.repo/pull-requests/12", ("~user/my.repo", 12)),
    ],
)
def test_pull_request_link_parsing_matches_the_server_shape(
    value: str, expected: tuple[str, int]
) -> None:
    assert pr_review.parse_pr_link(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "https://bb.example/DEMO/widgets/7", "/projects/DEMO/repos/x/pull-requests/x"],
)
def test_invalid_pull_request_link_is_rejected(value: str) -> None:
    with pytest.raises(AtlaWireError, match="pull-requests"):
        pr_review.parse_pr_link(value)


def test_profile_partial_is_false_only_without_known_omissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["profile"]["partial"] is False
    assert packet["profile"]["partial_reasons"] == []
    assert packet["checks"]["analysis_complete"] is True
    # A clean status is not a snapshot or diff completeness claim.
    assert packet["diff"]["proven_complete"] is False
    assert any(
        "not a proof" in item for item in packet["profile"]["limitations"]
    )


def test_unverified_ticket_makes_the_profile_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch)

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    assert packet["profile"]["partial"] is True
    assert any(
        "DEMO-42" in reason and "unverified" in reason
        for reason in packet["profile"]["partial_reasons"]
    )


def test_markdown_uses_safe_code_fences_for_hostile_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/we`ird](https://evil.invalid)<b>.java"
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {
                                "type": "ADDED",
                                "lines": [{"line": "class A {}"}],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )
    stub_repository_files(monkeypatch, {(path, FROM_HASH): "class A {}\n"})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    markdown = pr_review.render_markdown(packet)

    assert packet["checks"]["undocumented_types"]
    row = next(
        line
        for line in markdown.splitlines()
        if line.startswith("|") and "src/we" in line
    )
    cells = table_cells(row)
    assert len(cells) == 6
    assert cells[0] == f" ``{path}`` "
    rendered, outside = split_code_spans(
        unescape_table_pipes(cells[0].strip())
    )
    assert rendered == path
    assert outside == ""
    # The undocumented-type bullet remains a robust code span.
    assert f"``{path}:1 A``" in markdown


def test_long_rendered_ticket_description_keeps_a_closing_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_code = "x" * 4000
    issue = jira_issue()
    issue["fields"] = {
        "summary": "Long code",
        "status": {"name": "Open"},
        "issuetype": {"name": "Task"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Bob"},
        "reporter": {"displayName": "Alice"},
        "description": "",
    }
    issue["renderedFields"] = {
        "description": f"<pre>{long_code}</pre><p>after code</p>"
    }
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch, issue=issue)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    ticket = packet["ticket"]
    assert ticket is not None
    assert ticket["description_truncated"] is True
    lines = ticket["description"].splitlines()
    assert lines
    fence = lines[0].split("text", 1)[0]
    assert fence.startswith("```")
    assert lines[-1] == fence
    markdown = pr_review.render_markdown(packet)
    assert "## Ticket `DEMO-42`" in markdown
    assert "# `DEMO/widgets`#7" in markdown
    assert "## Commits" in markdown
    assert "## Heuristic checks" in markdown


def test_markdown_discloses_partial_reasons_and_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = [
        commit_row(index, message="m" * 20_000)
        for index in range(1, pr_review.COMMIT_LIMIT + 2)
    ]
    stub_collect(
        monkeypatch,
        info=pr_body(description="d" * 100_000),
        commits=commits,
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    markdown = pr_review.render_markdown(packet)

    assert "## Completeness" in markdown
    assert "The packet is partial" in markdown
    for reason in packet["profile"]["partial_reasons"]:
        assert reason in markdown
    assert "Author description was truncated." in markdown
    assert "Commit list was truncated." in markdown
    assert "_(message truncated)_" in markdown


def test_line_comments_keep_coordinates_and_javadoc_comes_from_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/main/java/demo/Documented.java"
    source = "\n".join(
        [
            "class Commented {",
            "    // legacy line comment",
            "    public void run() {",
            "        TODO fix;",
            "    }",
            "}",
            "/** Documented. */",
            "class Documented {",
            "    /** Runs. */",
            "    public void run() {",
            "        work();",
            "    }",
            "}",
            "// no doc",
            "class Undocumented {",
            "    public void run() {",
            "        work();",
            "    }",
            "}",
            "",
        ]
    )
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": line,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "ADDED", "lines": [{"line": text}]}
                        ],
                    }
                    for line, text in (
                        (4, "        TODO fix;"),
                        (11, "        work();"),
                        (17, "        work();"),
                    )
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )
    stub_repository_files(monkeypatch, {(path, FROM_HASH): source})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    symbols = packet["checks"]["symbols"]
    documented = next(
        item
        for item in symbols
        if item["kind"] == "type" and item["name"] == "Documented"
    )
    undocumented = next(
        item
        for item in symbols
        if item["kind"] == "type" and item["name"] == "Undocumented"
    )
    commented = next(
        item
        for item in symbols
        if item["kind"] == "type" and item["name"] == "Commented"
    )
    assert documented["javadoc"] is True
    assert undocumented["javadoc"] is False
    assert commented["javadoc"] is False
    run_symbols = [
        item
        for item in symbols
        if item["kind"] == "method" and item["name"] == "run"
    ]
    assert {item["line"] for item in run_symbols} == {3, 10, 16}
    documented_run = next(item for item in run_symbols if item["line"] == 10)
    assert documented_run["javadoc"] is True
    assert all(
        item["javadoc"] is False
        for item in run_symbols
        if item["line"] != 10
    )


def test_rename_uses_old_path_for_old_side_and_new_path_for_new_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = "src/old/Widget.java"
    new = "src/new/Widget.java"
    before = "\n".join(
        ["class Widget {", "    void run() {", "        old();", "    }", "}"]
    )
    after = "\n".join(
        ["class Widget {", "    void run() {", "        new();", "    }", "}"]
    )
    diff = {
        "diffs": [
            {
                "source": {"toString": old},
                "destination": {"toString": new},
                "hunks": [
                    {
                        "sourceLine": 2,
                        "sourceSpan": 2,
                        "destinationLine": 2,
                        "destinationSpan": 2,
                        "segments": [
                            {
                                "type": "CONTEXT",
                                "lines": [{"line": "    void run() {"}],
                            },
                            {
                                "type": "REMOVED",
                                "lines": [{"line": "        old();"}],
                            },
                            {
                                "type": "ADDED",
                                "lines": [{"line": "        new();"}],
                            },
                            {
                                "type": "CONTEXT",
                                "lines": [{"line": "    }"}],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={
                "displayId": "feature",
                "latestCommit": FROM_HASH,
                "repository": {"project": {"key": "FORK"}, "slug": "source"},
            },
            toRef={
                "displayId": "main",
                "latestCommit": TO_HASH,
                "repository": {"project": {"key": "DEMO"}, "slug": "widgets"},
            },
        ),
        files=[file_row(new)],
        diff=diff,
    )
    reads = stub_repository_files(
        monkeypatch,
        {(old, TO_HASH): before, (new, FROM_HASH): after},
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    links = packet["files"][0]["links"]
    assert links["before"] == (
        f"{BASE}/projects/DEMO/repos/widgets/browse/{old}?at={TO_HASH}"
    )
    assert links["after"] == (
        f"{BASE}/projects/FORK/repos/source/browse/{new}?at={FROM_HASH}"
    )
    assert {(call["path"], call["at"]) for call in reads} == {
        (old, TO_HASH),
        (new, FROM_HASH),
    }
    assert all((call["path"], call["at"]) != (new, TO_HASH) for call in reads)


def test_heuristic_cap_bounds_distinct_attempts_including_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [f"src/main/java/demo/A{index}.java" for index in range(51)]
    files = [file_row(path) for path in paths]
    diff = {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "ADDED", "lines": [{"line": "class A {}"}]}
                        ],
                    }
                ],
            }
            for path in paths
        ]
    }
    stub_collect(monkeypatch, files=files, diff=diff)
    reads = stub_repository_files(monkeypatch, {})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)

    distinct = {(call["repo"], call["path"]) for call in reads}
    assert len(distinct) == pr_review.HEURISTIC_FILE_LIMIT
    assert all(not path.endswith("A50.java") for _, path in distinct)
    assert len(reads) <= 2 * pr_review.HEURISTIC_FILE_LIMIT
    assert packet["checks"]["analysis_limited"] is True
    assert packet["checks"]["files_not_analyzed"]
    assert packet["profile"]["partial"] is True
    assert any(
        "cap" in reason for reason in packet["profile"]["partial_reasons"]
    )


def test_entity_split_jira_token_is_rejected_without_partial_packet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = jira_issue()
    issue["renderedFields"] = {
        "description": "<p>fixture-only-jira-re&#118;iew-token</p>"
    }
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch, issue=issue)

    with pytest.raises(AtlaWireError, match="echo a credential") as error:
        pr_review.collect_pr_review(
            BASE,
            REPO,
            PR_ID,
            token=TOKEN,
            jira_base_url=JIRA_BASE,
            jira_token=JIRA_TOKEN,
        )

    assert JIRA_TOKEN not in str(error.value)
    assert TOKEN not in str(error.value)


def test_ordinary_jira_description_is_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = jira_issue()
    issue["renderedFields"] = {
        "description": "<p>ordinary review notes</p>"
    }
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch, issue=issue)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    assert packet["ticket"]["description"] == "ordinary review notes"


def test_concatenated_packet_fragments_are_rejected() -> None:
    with pytest.raises(AtlaWireError, match="echo a credential"):
        pr_review.reject_credential_echo(
            {
                "first": "fixture-only-jira-re",
                "second": "view-token",
            },
            tokens=(JIRA_TOKEN,),
        )


def test_entity_split_base64_jira_token_is_rejected_by_shared_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.b64encode(JIRA_TOKEN.encode()).decode()
    midpoint = len(encoded) // 2
    wire = (
        encoded[:midpoint]
        + f"&#{ord(encoded[midpoint])};"
        + encoded[midpoint + 1 :]
    )
    assert JIRA_TOKEN not in wire
    issue = jira_issue()
    issue["renderedFields"] = {"description": f"<p>{wire}</p>"}
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch, issue=issue)

    with pytest.raises(AtlaWireError) as error:
        pr_review.collect_pr_review(
            BASE,
            REPO,
            PR_ID,
            token=TOKEN,
            jira_base_url=JIRA_BASE,
            jira_token=JIRA_TOKEN,
        )

    assert "token" in str(error.value).lower()
    assert JIRA_TOKEN not in str(error.value)
    assert TOKEN not in str(error.value)


def test_entity_split_benign_base64_is_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benign = base64.b64encode(b"ordinary review notes").decode()
    midpoint = len(benign) // 2
    wire = (
        benign[:midpoint]
        + f"&#{ord(benign[midpoint])};"
        + benign[midpoint + 1 :]
    )
    assert JIRA_TOKEN not in wire
    issue = jira_issue()
    issue["renderedFields"] = {"description": f"<p>{wire}</p>"}
    stub_collect(
        monkeypatch,
        info=pr_body(
            fromRef={"displayId": "feature/DEMO-42", "latestCommit": FROM_HASH},
            toRef={"displayId": "main", "latestCommit": TO_HASH},
        ),
        files=[file_row("src/App.txt")],
        diff=diff_body(),
    )
    stub_jira(monkeypatch, issue=issue)

    packet = pr_review.collect_pr_review(
        BASE,
        REPO,
        PR_ID,
        token=TOKEN,
        jira_base_url=JIRA_BASE,
        jira_token=JIRA_TOKEN,
    )

    assert packet["ticket"]["description"] == benign


def table_cells(line: str) -> list[str]:
    """Split like cmark-gfm's ``escaped_char`` table scanner.

    Backslash pairs are themselves escaped characters. A pipe is cell content
    only when its immediately preceding backslash run has odd length; an even
    run leaves the pipe as a separator.
    """
    assert line.startswith("|") and line.endswith("|")
    cells: list[str] = []
    current: list[str] = []
    backslashes = 0
    for char in line[1:-1]:
        if char == "|" and backslashes % 2 == 0:
            cells.append("".join(current))
            current = []
            backslashes = 0
            continue
        current.append(char)
        backslashes = backslashes + 1 if char == "\\" else 0
    cells.append("".join(current))
    return cells


def test_file_table_escapes_pipes_and_keeps_six_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/A|[forged](x).java"
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "ADDED", "lines": [{"line": "class A {}"}]}
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )
    stub_repository_files(monkeypatch, {(path, FROM_HASH): "class A {}\n"})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    markdown = pr_review.render_markdown(packet)

    header = next(
        line for line in markdown.splitlines() if line.startswith("| file |")
    )
    assert len(table_cells(header)) == 6
    row = next(
        line
        for line in markdown.splitlines()
        if line.startswith("|") and "src/A" in line
    )
    cells = table_cells(row)
    assert len(cells) == 6
    expected_cell = r" `src/A`\|`[forged](x).java` "
    assert cells[0] == expected_cell
    rendered, outside = split_code_spans(
        unescape_table_pipes(cells[0].strip())
    )
    assert rendered == "src/A|[forged](x).java"
    assert set(outside) <= {"|"}
    assert "[forged](x)" not in "".join(cells[1:])


def test_undocumented_type_label_uses_backtick_and_html_safe_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "src/A`<b>[forged](x).java"
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "ADDED", "lines": [{"line": "class A {}"}]}
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )
    stub_repository_files(monkeypatch, {(path, FROM_HASH): "class A {}\n"})

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    markdown = pr_review.render_markdown(packet)

    label = packet["checks"]["undocumented_types"][0]
    expected = f"``{label}``"
    line = next(
        item
        for item in markdown.splitlines()
        if item.startswith("  - without description:")
    )
    before, _, after = line.partition(expected)
    assert expected in line
    assert "[forged](x)" not in before + after


TABLE_TEXT_CASES = [
    (r"A\B.txt", r" `A\B.txt` "),
    (r"A\|B.txt", r" `A\`\|`B.txt` "),
    (r"A\|[forged](x).txt", r" `A\`\|`[forged](x).txt` "),
    (
        "A`<b>[forged](x).txt",
        " ``A`<b>[forged](x).txt`` ",
    ),
    ("www.example.com/A.txt", " `www.example.com/A.txt` "),
    ("http://example.com/A.txt", " `http://example.com/A.txt` "),
    ("https://example.com/A.txt", " `https://example.com/A.txt` "),
    ("user@example.com", " `user@example.com` "),
    ("src/A | B.txt", " ` src/A  `\\|`  B.txt ` "),
    ("src/A | | B.txt", " ` src/A  `\\|` `\\|`  B.txt ` "),
    (
        "src/A ` | `B`.txt",
        " `` src/A `  ``\\|``  `B`.txt `` ",
    ),
    ("A| |B", " `A`\\|` `\\|`B` "),
    ("src/A  B.java", " `src/A  B.java` "),
    (" src/A.java ", " `  src/A.java  ` "),
    (
        "src/A  |  B.java",
        " ` src/A   `\\|`   B.java ` ",
    ),
    ("A|`www.example.com", " `A`\\|`` `www.example.com `` "),
    ("A|<html>`", " `A`\\|`` <html>` `` "),
    ("A|```", " `A`\\|```` ``` ```` "),
    ("A| \u00a0 |B.txt", " `A`\\|`  \u00a0  `\\|`B.txt` "),
    ("A||B", " `A`\\|\\|`B` "),
]


def unescape_table_pipes(cell: str) -> str:
    """Model cmark-gfm's ``unescape_pipes`` in one already-split cell."""
    result: list[str] = []
    index = 0
    while index < len(cell):
        char = cell[index]
        if char == "\\" and index + 1 < len(cell) and cell[index + 1] == "|":
            result.append("|")
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def split_code_spans(cell: str) -> tuple[str, str]:
    """Return displayed code content and text left outside code spans."""
    rendered: list[str] = []
    outside: list[str] = []
    index = 0
    while index < len(cell):
        if cell[index] != "`":
            rendered.append(cell[index])
            outside.append(cell[index])
            index += 1
            continue
        run = 0
        while index + run < len(cell) and cell[index + run] == "`":
            run += 1
        search = index + run
        close = -1
        while search < len(cell):
            if cell[search] != "`":
                search += 1
                continue
            other = 0
            while search + other < len(cell) and cell[search + other] == "`":
                other += 1
            if other == run:
                close = search
                break
            search += other
        if close < 0:
            rendered.append(cell[index:])
            outside.append(cell[index:])
            break
        content = cell[index + run : close]
        if (
            content.startswith(" ")
            and content.endswith(" ")
            and content.strip(" ")
        ):
            content = content[1:-1]
        rendered.append(content)
        index = close + run
    return "".join(rendered), "".join(outside)


@pytest.mark.parametrize(
    ("path", "expected_cell"),
    TABLE_TEXT_CASES,
    ids=[
        "plain-slash",
        "slash-pipe",
        "slash-pipe-link",
        "backtick-html",
        "www",
        "http",
        "https",
        "email",
        "space-pipe",
        "space-pipe-space",
        "backtick-space-pipe",
        "empty-space-pipe",
        "repeated-space",
        "edge-space",
        "repeated-space-pipe",
        "leading-backtick-www",
        "trailing-backtick-html",
        "only-backticks",
        "nbsp-edge-spaces",
        "empty-consecutive-pipes",
    ],
)
def test_table_text_preserves_original_backslashes_and_six_cells(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expected_cell: str,
) -> None:
    diff = {
        "diffs": [
            {
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 0,
                        "sourceSpan": 0,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {"type": "ADDED", "lines": [{"line": "note"}]}
                        ],
                    }
                ],
            }
        ]
    }
    stub_collect(
        monkeypatch,
        files=[file_row(path, change_type="ADD")],
        diff=diff,
    )

    packet = pr_review.collect_pr_review(BASE, REPO, PR_ID, token=TOKEN)
    markdown = pr_review.render_markdown(packet)
    lines = markdown.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith("| file |")
    )
    row = lines[start + 2]
    cells = table_cells(row)

    assert len(cells) == 6
    assert cells[0] == expected_cell
    # Table scanning/unescaping leaves code spans plus literal pipes. All
    # filename text is inside code spans, so no autolink or HTML is active.
    processed = unescape_table_pipes(cells[0].strip())
    rendered, outside = split_code_spans(processed)
    assert rendered == path
    assert set(outside) <= {"|"}
    assert "[forged](x)" not in "".join(cells[1:])


def test_table_controls_are_visible_and_do_not_break_structure() -> None:
    path = "A\tB.java\nC"
    cell = " " + pr_review._table_text(path) + " "
    row = "|" + cell + "| x |"
    cells = table_cells(row)
    rendered, outside = split_code_spans(
        unescape_table_pipes(cells[0].strip())
    )

    assert len(cells) == 2
    assert "\t" not in cell
    assert "\n" not in cell
    assert "\\t" in cell
    assert "\\n" in cell
    assert "\t" not in rendered
    assert "\n" not in rendered
    assert rendered == "A\\tB.java\\nC"
    assert outside == ""

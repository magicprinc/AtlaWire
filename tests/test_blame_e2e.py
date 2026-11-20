"""Installed-CLI and projection checks for Bitbucket file blame."""

import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError
from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-blame-token"
JIRA_TOKEN = "wrong-product-jira-blame"
CONFLUENCE_TOKEN = "wrong-product-confluence-blame"
CONTEXT = "/scm/bitbucket"
RAW = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets"
PATH = "папка/dir name/a#b?c%d.txt"
ENCODED = "%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/dir%20name/a%23b%3Fc%25d.txt"
REF = "feature/x+y"
HASH = "a" * 40
FALLBACK_ID = "b" * 40
PREVIOUS_DAY_ID = "c" * 40
LAST_ID = "d" * 40
UNUSED_ID = "f" * 40


def environment(origin: str) -> dict[str, str]:
    """Override all six product fields so only the blame route can succeed."""
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
    }


def base_arguments(origin: str) -> list[str]:
    return [
        "--base-url",
        f"{origin}{CONTEXT}/",
        "--allow-http-loopback",
        "--token-from-env",
    ]


def blame_rows() -> list[object]:
    """Return rows exercising hash priority, missing metadata, and old dates."""
    return [
        {
            "author": {"name": "Ada", "emailAddress": "ada@example.invalid"},
            "authorTimestamp": 1527228363490,
            "commitHash": HASH,
            "id": UNUSED_ID,
        },
        {"author": None, "authorTimestamp": 0, "id": FALLBACK_ID},
        {
            "author": {"name": "Bob"},
            "authorTimestamp": -1000,
            "commitHash": None,
            "id": PREVIOUS_DAY_ID,
        },
        {
            "author": {"name": "Cleo", "emailAddress": "cleo@example.invalid"},
            "authorTimestamp": 59999,
            "commitHash": "",
            "id": LAST_ID,
        },
    ]


EXPECTED_ROWS = [
    {
        "line": 1,
        "author": "Ada",
        "email": "ada@example.invalid",
        "date": "2018-05-25",
        "commit": HASH,
    },
    {
        "line": 2,
        "author": None,
        "email": None,
        "date": "1970-01-01",
        "commit": FALLBACK_ID,
    },
    {
        "line": 3,
        "author": "Bob",
        "email": None,
        "date": "1969-12-31",
        "commit": PREVIOUS_DAY_ID,
    },
    {
        "line": 4,
        "author": "Cleo",
        "email": "cleo@example.invalid",
        "date": "1970-01-01",
        "commit": LAST_ID,
    },
]


def expected_request(*, with_ref: bool) -> list[Request]:
    query = {"blame": ["true"], "noContent": ["true"]}
    if with_ref:
        query["at"] = [REF]
    return [("GET", f"{RAW}/browse/{ENCODED}", query, f"Bearer {TOKEN}")]


def run_blame(
    *arguments: str, body: object
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None]]:
    """Run the installed CLI against one JSON body and capture its GETs."""
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            send_json(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["blame", "DEMO/widgets", PATH, *arguments, *base_arguments(origin)],
            environment(origin),
        )
    return result, seen, accepts


def test_installed_blame_prints_legacy_tsv_without_email() -> None:
    result, seen, accepts = run_blame("--at", REF, body=blame_rows())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 4 row(s)\n"
        "line\tauthor\tdate\tcommit\n"
        f"1\tAda\t2018-05-25\t{HASH}\n"
        f"2\t\t1970-01-01\t{FALLBACK_ID}\n"
        f"3\tBob\t1969-12-31\t{PREVIOUS_DAY_ID}\n"
        f"4\tCleo\t1970-01-01\t{LAST_ID}\n"
    )
    assert "example.invalid" not in result.stdout
    assert seen == expected_request(with_ref=True)
    assert accepts == ["application/json"]
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN):
        assert detail not in result.stdout
        assert detail not in result.stderr


def test_installed_blame_json_has_exactly_the_projected_fields() -> None:
    result, seen, accepts = run_blame("--at", REF, "--json", body=blame_rows())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED_ROWS
    assert all(
        set(row) == {"line", "author", "email", "date", "commit"}
        for row in json.loads(result.stdout)
    )
    assert seen == expected_request(with_ref=True)
    assert accepts == ["application/json"]


def test_a_malformed_late_row_leaves_no_partial_stdout_and_hides_data() -> None:
    sentinel = "BLAME-LATE-SENTINEL"
    body = [blame_rows()[0], {"author": sentinel, "authorTimestamp": 0}]

    result, seen, accepts = run_blame(body=body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "blame row" in result.stderr
    assert sentinel not in result.stderr
    assert seen == expected_request(with_ref=False)
    assert accepts == ["application/json"]


def test_a_paged_file_content_envelope_is_rejected_rather_than_parsed() -> None:
    sentinel = "BLAME-ENVELOPE-SENTINEL"
    body = {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "start": 0,
        "lines": [{"text": sentinel}],
    }

    result, seen, accepts = run_blame(body=body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "JSON array" in result.stderr
    assert sentinel not in result.stderr
    assert seen == expected_request(with_ref=False)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("repo", "path", "options", "expected"),
    [
        ("DEMO/widgets", "../secret", (), "file path"),
        ("DEMO/widgets", "a.txt", ("--at", "line\nbreak"), "revision"),
        ("DEMO", "a.txt", (), "repository as PROJECT/slug"),
    ],
    ids=["path", "ref", "repo"],
)
def test_invalid_operands_are_rejected_before_any_request(
    repo: str, path: str, options: tuple[str, ...], expected: str
) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 200, [])

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["blame", repo, path, *options, *base_arguments(origin)],
            environment(origin),
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected in result.stderr
    assert seen == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (0, "1970-01-01"),
        (-1000, "1969-12-31"),
        (59999, "1970-01-01"),
        (86400000, "1970-01-02"),
    ],
    ids=["absent", "epoch", "pre-epoch", "last-millisecond", "next-day"],
)
def test_blame_date_is_utc_and_preserves_zero_and_pre_epoch(
    value: int | None, expected: str | None
) -> None:
    assert bitbucket._blame_date(value) == expected


@pytest.mark.parametrize("value", [True, False, 1.5, "0", [0], 10**18, -(10**18)])
def test_blame_date_rejects_bad_timestamps_without_echoing_the_value(
    value: object,
) -> None:
    with pytest.raises(AtlaWireError, match="author timestamp") as error:
        bitbucket._blame_date(value)

    assert str(value) not in str(error.value)


def test_blame_commit_does_not_consume_an_unused_fallback() -> None:
    assert bitbucket._blame_commit({"commitHash": HASH, "id": 7}) == HASH
    assert bitbucket._blame_commit({"commitHash": "", "id": FALLBACK_ID}) == (
        FALLBACK_ID
    )
    assert bitbucket._blame_commit({"commitHash": None, "id": None}) is None
    assert bitbucket._blame_commit({}) is None


@pytest.mark.parametrize(
    "value",
    [
        {"commitHash": 7},
        {"commitHash": "", "id": 7},
        {"commitHash": "bad\ud800commit"},
    ],
    ids=["hash-type", "id-type", "surrogate"],
)
def test_blame_commit_rejects_wrong_consumed_types(value: dict[str, object]) -> None:
    with pytest.raises(AtlaWireError, match="blame"):
        bitbucket._blame_commit(value)


def test_blame_author_omits_absent_fields_and_rejects_bad_consumed_types() -> None:
    assert bitbucket._blame_author(None) == (None, None)
    assert bitbucket._blame_author({"name": "Ada"}) == ("Ada", None)
    for value in (
        {"name": 7},
        {"emailAddress": 7},
        {"name": "bad\ud800author"},
    ):
        with pytest.raises(AtlaWireError, match="author"):
            bitbucket._blame_author(value)

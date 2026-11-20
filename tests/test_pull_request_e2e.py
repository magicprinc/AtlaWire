import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-pull-request-only"
JIRA_TOKEN = "wrong-product-jira"
CONFLUENCE_TOKEN = "wrong-product-confluence"
ID_MARKER = "PR-ID-MARKER"
CONTEXT = "/scm/bitbucket"
PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/1"
SENTINEL = "PR-PAYLOAD-SENTINEL"
EXPECTED = ("GET", PATH, {}, f"Bearer {TOKEN}")


def payload(decoy: str) -> dict[str, object]:
    return {
        "id": 1,
        "version": 3,
        "title": "Talking Nerdy — α",
        "description": None,
        "state": "OPEN",
        "open": True,
        "closed": False,
        "createdDate": 1359075920,
        "fromRef": {
            "id": "refs/heads/feature-ABC-123",
            "repository": {
                "slug": "fork-of-widgets",
                "name": None,
                "project": {"key": "OPS"},
            },
        },
        "toRef": {
            "id": "refs/heads/main",
            "repository": {
                "slug": "widgets",
                "name": None,
                "project": {"key": "DEMO"},
            },
        },
        "author": {"user": {"name": "tom", "displayName": "Tom — α", "active": True}},
        "extension": {"trace": ["τ", None, 1.5]},
        "links": {"self": [{"href": decoy}]},
    }


def response_for(scenario: str, decoy: str) -> tuple[int, object]:
    if scenario == "not-found":
        return 404, {"errors": [{"message": SENTINEL, "token": TOKEN}], "x": SENTINEL}
    body = payload(decoy)
    if scenario == "boolean-id":
        body["id"] = True
        body["sentinel"] = SENTINEL
    elif scenario == "string-id":
        body["id"] = "1"
    elif scenario == "wrong-id":
        body["id"] = 2
    return 200, body


def run_pr(
    scenario: str, *arguments: str, pr_id: str = "1"
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str],
    list[str | None],
    list[str],
    str,
]:
    seen: list[Request] = []
    raw_paths: list[str] = []
    accepts: list[str | None] = []
    intruder: list[str] = []

    class Intruder(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            intruder.append(self.path)
            send_json(self, 200, {"id": 1, "title": "DECOY", "state": "OPEN"})

    with serving(Intruder) as decoy_server:
        decoy = f"http://127.0.0.1:{decoy_server.server_port}/redirect-target"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                seen.append(request_record(self))
                raw_paths.append(self.path)
                accepts.append(self.headers.get("Accept"))
                if scenario == "redirect":
                    self.send_response(302)
                    self.send_header("Location", decoy)
                    self.end_headers()
                    return
                status, body = response_for(scenario, decoy)
                send_json(self, status, body)

        with serving(Handler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = run_installed(
                [
                    "pr",
                    "DEMO/widgets",
                    pr_id,
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
    return result, seen, raw_paths, accepts, intruder, decoy


@pytest.mark.parametrize("arguments", [(), ("show",)], ids=["omitted", "show"])
def test_pr_prints_the_server_object_verbatim_after_one_expected_get(
    arguments: tuple[str, ...],
) -> None:
    result, seen, raw_paths, accepts, intruder, decoy = run_pr("ok", *arguments)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    decoded = json.loads(result.stdout)
    assert decoded == payload(decoy)
    assert type(decoded["id"]) is int
    assert decoded["id"] == 1
    assert decoded["description"] is None
    assert decoded["open"] is True
    assert decoded["fromRef"]["repository"]["project"]["key"] == "OPS"
    assert seen == [EXPECTED]
    assert raw_paths == [PATH]
    assert accepts == ["application/json"]
    assert intruder == []


@pytest.mark.parametrize(
    ("scenario", "expected_error"),
    [
        ("boolean-id", "Invalid pull request"),
        ("string-id", "Invalid pull request"),
        ("wrong-id", "Invalid pull request"),
        ("not-found", "HTTP 404"),
        ("redirect", "redirect"),
    ],
)
def test_pr_failures_are_sanitized_and_never_retried_or_followed(
    scenario: str, expected_error: str
) -> None:
    result, seen, raw_paths, accepts, intruder, _decoy = run_pr(scenario)

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected_error in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL, "redirect-target"):
        assert detail not in result.stderr
    assert seen == [EXPECTED]
    assert raw_paths == [PATH]
    assert accepts == ["application/json"]
    assert intruder == []


def test_third_argument_is_only_the_literal_show() -> None:
    result, seen, _raw, _accepts, _intruder, _decoy = run_pr("ok", "bogus")

    assert result.returncode == 2
    assert result.stdout == ""
    assert '"show"' in result.stderr
    assert seen == []


def test_malformed_id_fails_before_any_request_without_echo() -> None:
    result, seen, raw_paths, _accepts, intruder, _decoy = run_pr("ok", pr_id=ID_MARKER)

    assert result.returncode == 1
    assert result.stdout == ""
    assert ID_MARKER not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == []
    assert raw_paths == []
    assert intruder == []

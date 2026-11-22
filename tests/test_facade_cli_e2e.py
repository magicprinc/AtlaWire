"""Loopback end-to-end tests for the public AtlaWire facade.

The installed library and its real HTTP client are exercised against a local
server. Only saved-credential resolution is replaced, with synthetic values, so
no real credential file and no external network are involved.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler

import pytest

import atlawire.facade as facade
from atlawire.credentials import SavedCredentials
from atlawire.facade import AtlaWire
from atlawire.http import AtlaWireError
from tests._loopback import Request, request_record, send_bytes, send_json, serving

TOKEN = "synthetic-facade-loopback-token-8b1"
SENTINEL = "FACADE-LOOPBACK-SENTINEL"
CONTEXTS = {
    "bitbucket": "/bitbucket",
    "confluence": "/confluence",
    "jira": "/jira",
}


@contextmanager
def loopback(
    payload: object = None,
    *,
    status: int = 200,
    body: bytes | None = None,
    content_type: str = "application/json",
) -> Iterator[tuple[str, list[Request]]]:
    """Serve one fixed response and record every request that arrives."""
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self) -> None:
            seen.append(request_record(self))
            if body is not None:
                send_bytes(self, status, body, content_type=content_type)
            else:
                send_json(self, status, payload)

        do_GET = respond
        do_POST = respond

    with serving(Handler) as server:
        yield f"http://127.0.0.1:{server.server_port}", seen


def install(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    *,
    available: tuple[str, ...] = ("bitbucket", "confluence", "jira"),
) -> list[tuple[str, bool]]:
    """Replace saved credentials with synthetic loopback pairs per product."""
    calls: list[tuple[str, bool]] = []

    def resolver(
        product: str,
        *,
        supplied_base_url: str | None,
        allow_http_loopback: bool,
    ) -> SavedCredentials:
        calls.append((product, allow_http_loopback))
        assert supplied_base_url is None
        if product not in available or not allow_http_loopback:
            raise AtlaWireError(
                f"Saved BBK credentials are unavailable for {product}."
            )
        return SavedCredentials(
            base_url=f"{origin}{CONTEXTS[product]}", token=TOKEN
        )

    monkeypatch.setattr(facade, "resolve_saved_credentials", resolver)
    return calls


def test_jira_get_issue_returns_the_upstream_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"key": "ABC-123", "fields": {"summary": "Loopback"}}

    with loopback(payload) as (origin, seen):
        install(monkeypatch, origin)
        envelope = AtlaWire(allow_http_loopback=True).jira.get_issue("ABC-123")

    assert envelope == {"ok": True, "product": "jira", "data": payload}
    assert seen == [
        (
            "GET",
            "/jira/rest/api/2/issue/ABC-123",
            {},
            f"Bearer {TOKEN}",
        )
    ]


def test_confluence_get_page_returns_the_upstream_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"id": "4242", "title": "Loopback page"}

    with loopback(payload) as (origin, seen):
        install(monkeypatch, origin)
        envelope = AtlaWire(allow_http_loopback=True).confluence.get_page(4242)

    assert envelope == {"ok": True, "product": "confluence", "data": payload}
    assert seen == [
        (
            "GET",
            "/confluence/rest/api/content/4242",
            {},
            f"Bearer {TOKEN}",
        )
    ]


def test_bitbucket_get_repository_returns_the_upstream_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"slug": "my-repo", "project": {"key": "PROJ"}}

    with loopback(payload) as (origin, seen):
        install(monkeypatch, origin)
        envelope = AtlaWire(allow_http_loopback=True).bitbucket.get_repository(
            "PROJ", "my-repo"
        )

    assert envelope == {"ok": True, "product": "bitbucket", "data": payload}
    assert seen == [
        (
            "GET",
            "/bitbucket/rest/api/1.0/projects/PROJ/repos/my-repo",
            {},
            f"Bearer {TOKEN}",
        )
    ]


def test_search_queries_are_encoded_into_fixed_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jql = 'project = OPS AND text ~ "café & tea"'
    cql = 'type = page and title ~ "a+b & c"'

    with loopback({"issues": [], "startAt": 0, "total": 0}) as (jira_origin, jira_seen):
        install(monkeypatch, jira_origin)
        jira_envelope = AtlaWire(allow_http_loopback=True).jira.search(jql, limit=3)

    with loopback({"results": [], "size": 0}) as (
        confluence_origin,
        confluence_seen,
    ):
        install(monkeypatch, confluence_origin)
        confluence_envelope = AtlaWire(allow_http_loopback=True).confluence.search(
            cql, limit=5
        )

    assert jira_envelope["ok"] is True
    assert confluence_envelope["ok"] is True
    assert jira_seen == [
        (
            "GET",
            "/jira/rest/api/2/search",
            {"jql": [jql], "maxResults": ["3"]},
            f"Bearer {TOKEN}",
        )
    ]
    assert confluence_seen == [
        (
            "GET",
            "/confluence/rest/api/content/search",
            {"cql": [cql], "limit": ["5"]},
            f"Bearer {TOKEN}",
        )
    ]


def test_list_endpoints_return_one_page_without_traversal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jira_projects = [{"key": "PROJ"}, {"key": "OPS"}]
    spaces = {"results": [{"key": "DOC"}], "size": 1, "limit": 25}
    bitbucket_projects = {
        "values": [{"key": "PROJ"}],
        "size": 1,
        "limit": 1,
        "isLastPage": False,
        "nextPageStart": 1,
    }

    with loopback(jira_projects) as (origin, seen):
        install(monkeypatch, origin)
        jira_envelope = AtlaWire(allow_http_loopback=True).jira.list_projects()
    assert jira_envelope == {"ok": True, "product": "jira", "data": jira_projects}
    assert seen == [("GET", "/jira/rest/api/2/project", {}, f"Bearer {TOKEN}")]

    with loopback(spaces) as (origin, seen):
        install(monkeypatch, origin)
        confluence_envelope = AtlaWire(
            allow_http_loopback=True
        ).confluence.list_spaces(limit=7)
    assert confluence_envelope == {
        "ok": True,
        "product": "confluence",
        "data": spaces,
    }
    assert seen == [
        (
            "GET",
            "/confluence/rest/api/space",
            {"limit": ["7"]},
            f"Bearer {TOKEN}",
        )
    ]

    with loopback(bitbucket_projects) as (origin, seen):
        install(monkeypatch, origin)
        bitbucket_envelope = AtlaWire(
            allow_http_loopback=True
        ).bitbucket.list_projects(limit=1)
    assert bitbucket_envelope == {
        "ok": True,
        "product": "bitbucket",
        "data": bitbucket_projects,
    }
    assert seen == [
        (
            "GET",
            "/bitbucket/rest/api/1.0/projects",
            {"limit": ["1"]},
            f"Bearer {TOKEN}",
        )
    ]


def test_upstream_error_keeps_status_body_and_redacts_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = json.dumps({"message": SENTINEL, "echo": TOKEN}).encode()

    with loopback(None, status=401, body=upstream) as (origin, seen):
        install(monkeypatch, origin)
        envelope = AtlaWire(allow_http_loopback=True).jira.get_issue("ABC-123")

    assert envelope["ok"] is False
    assert envelope["product"] == "jira"
    reported = envelope["error"]
    assert reported["status"] == 401
    assert reported["code"] == "http_401"
    assert reported["path"] == "/rest/api/2/issue/ABC-123"
    assert reported["body"] == (
        '{"message": "FACADE-LOOPBACK-SENTINEL", "echo": "[REDACTED]"}'
    )
    assert reported["body_json"] == {"message": SENTINEL, "echo": "[REDACTED]"}
    assert reported["body_truncated"] is False
    rendered = json.dumps(envelope)
    assert TOKEN not in rendered
    assert "Authorization" not in rendered
    assert len(seen) == 1


def test_missing_product_credentials_fail_only_that_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spaces = {"results": [{"key": "DOC"}], "size": 1}

    with loopback(spaces) as (origin, seen):
        calls = install(monkeypatch, origin, available=("confluence",))
        wire = AtlaWire(allow_http_loopback=True)
        failed = wire.jira.list_projects()
        succeeded = wire.confluence.list_spaces()

    assert failed["ok"] is False
    assert failed["product"] == "jira"
    assert failed["error"]["code"] == "credentials_error"
    assert failed["error"]["status"] is None
    assert succeeded == {"ok": True, "product": "confluence", "data": spaces}
    assert calls == [("jira", True), ("confluence", True)]
    assert seen == [
        (
            "GET",
            "/confluence/rest/api/space",
            {"limit": ["25"]},
            f"Bearer {TOKEN}",
        )
    ]
    assert TOKEN not in json.dumps(failed)


def test_loopback_http_requires_the_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [{"key": "PROJ"}]

    with loopback(payload) as (origin, seen):
        install(monkeypatch, origin)
        refused = AtlaWire().jira.list_projects()
        allowed = AtlaWire(allow_http_loopback=True).jira.list_projects()

    assert refused["ok"] is False
    assert refused["error"]["code"] == "credentials_error"
    assert allowed == {"ok": True, "product": "jira", "data": payload}
    assert len(seen) == 1


def test_write_and_unlisted_operations_never_reach_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("credentials must not be resolved for a rejection")

    monkeypatch.setattr(facade, "resolve_saved_credentials", forbidden)

    with loopback({"ok": True}) as (_, seen):
        wire = AtlaWire(allow_http_loopback=True)
        envelopes = [
            wire.call("jira.delete_issue", key="ABC-123"),
            wire.call("bitbucket.create_repository", project="PROJ", slug="new"),
            wire.call(
                "jira.get_issue",
                key="ABC-123",
                path="/rest/api/2/admin",
            ),
            wire.call(
                "jira.get_issue",
                key="ABC-123",
                method="POST",
            ),
            wire.call("publish_page"),
            wire.call(42),
        ]

    for envelope in envelopes:
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "validation_error"
        assert envelope["error"]["status"] is None
    assert seen == []
    assert "ABC-123" not in json.dumps(envelopes)

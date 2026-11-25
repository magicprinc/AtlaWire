"""Pagination must not forget what an earlier page already proved.

Confluence documents `totalSize` on a page, but may omit it later. A reader that
keeps only the current page's value can return a short listing as complete after
an earlier page said rows remained. The metadata readers solve this with a
retained total; the typed space-content reader did not.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket, bitbucket_attachment, bitbucket_search, confluence, jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-pagination-token"
SPACE_PATH = "/rest/api/content/space/KEY/content/page"


@pytest.fixture
def server():
    state = {"bodies": []}
    calls: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            calls.append(parse_qs(urlsplit(self.path).query, keep_blank_values=True))
            index = min(len(calls) - 1, len(state["bodies"]) - 1)
            body = state["bodies"][index]
            payload = (
                body
                if isinstance(body, bytes)
                else __import__("json").dumps(body).encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, calls, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _page(rows: list[dict[str, object]], **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "results": rows,
        "start": extra.pop("start", 0),
        "limit": extra.pop("limit", 100),
        "size": len(rows),
        "_links": extra.pop("_links", {}),
    }
    body.update(extra)
    return body


def test_space_content_keeps_an_earlier_total_when_a_later_page_omits_it(server):
    state, calls, base = server
    state["bodies"] = [
        _page(
            [{"id": "1", "type": "page", "title": "A"}],
            start=0,
            totalSize=2,
            _links={
                "next": "/rest/api/content/space/KEY/content/page?start=1&limit=100"
            },
        ),
        _page([], start=1),
    ]

    with pytest.raises(AtlaWireError, match="empty page before all matches"):
        confluence.list_space_content(
            base, "KEY", token=TOKEN, type="page", limit=10, allow_http_loopback=True
        )

    assert len(calls) >= 2


def test_space_content_reports_complete_when_the_server_agrees(server):
    state, _, base = server
    state["bodies"] = [_page([{"id": "1", "type": "page"}], start=0, totalSize=1)]

    rows = confluence.list_space_content(
        base, "KEY", token=TOKEN, type="page", limit=10, allow_http_loopback=True
    )

    assert rows["truncated"] is False
    assert len(rows["rows"]) == 1


def test_a_text_max_pages_is_a_validation_error_not_a_type_error():
    with pytest.raises(AtlaWireError):
        bitbucket.list_repositories(
            "https://example.invalid",
            "PRJ",
            token=TOKEN,
            max_pages="5",  # type: ignore[arg-type]
        )


def test_a_boolean_max_pages_is_a_validation_error():
    with pytest.raises(AtlaWireError):
        bitbucket.list_repositories(
            "https://example.invalid", "PRJ", token=TOKEN, max_pages=True
        )


@pytest.mark.parametrize("bad", [None, 5, b"x", ["a"]])
def test_a_non_string_jql_is_a_validation_error(bad):
    with pytest.raises(AtlaWireError):
        jira.search_issues_with_metadata(
            "https://example.invalid",
            bad,
            token=TOKEN,
            limit=1,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("bad", [None, 5, b"x", ["a"]])
def test_a_non_string_cql_is_a_validation_error(bad):
    with pytest.raises(AtlaWireError):
        confluence.search_cql_with_metadata(
            "https://example.invalid",
            bad,
            token=TOKEN,
            limit=1,  # type: ignore[arg-type]
        )


SPLIT_CASES = [
    "PRJ/slug",
    "PRJ/",
    "/slug",
    "PRJ/a/b",
    "PRJ/.",
    "PRJ/..",
    "",
    None,
    5,
    "PRJ/slug ",
]


@pytest.mark.parametrize("value", SPLIT_CASES)
def test_the_three_repository_validators_agree(value):
    """Three copies of one rule; they must not drift apart."""
    validators = (
        bitbucket._split_repo,
        bitbucket_search._split_repo,
        bitbucket_attachment._split_repo,
    )
    verdicts = []
    for validate in validators:
        try:
            validate(value)  # type: ignore[arg-type]
        except AtlaWireError:
            verdicts.append("rejected")
        except (AttributeError, TypeError) as exc:
            verdicts.append(f"crashed:{type(exc).__name__}")
        else:
            verdicts.append("accepted")

    names = [validator.__module__ for validator in validators]
    assert len(set(verdicts)) == 1, (
        f"{value!r}: {dict(zip(names, verdicts, strict=True))}"
    )

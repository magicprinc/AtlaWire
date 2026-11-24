"""Black-box contracts for the read-only Jira 8.22 sub-resource reads.

Every scenario drives the public ``atlawire.jira`` function against a loopback
server on ``127.0.0.1:0``; assertions come from the recorded request
(path, query, headers) and from the returned, fully projected value, so a raw
response or a wrong route fails the test. No test reads an internal counter,
monkeypatches a guard, opens a real network connection or depends on time.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-subresource-token"
BODY_MARKER = "synthetic-only-response-body"


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 closes the connection after each response, so the server never
    # blocks reading a next request from a client that already gave up.
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        server = self.server
        server.calls.append(
            (
                self.command,
                self.path,
                self.headers.get("Authorization"),
                self.headers.get("Accept"),
            )
        )
        status, value = server.responses[
            min(len(server.calls) - 1, len(server.responses) - 1)
        ]
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError, ConnectionResetError:
            # The client closes the connection on an error status before reading
            # the body, so a reset here is expected and not a test failure.
            pass

    def finish(self):
        try:
            super().finish()
        except BrokenPipeError, ConnectionResetError:
            pass
        finally:
            self.server.closed.set()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.calls = []
    httpd.responses = []
    httpd.closed = threading.Event()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def assert_call(call, path, query):
    method, target, authorization, accept = call
    parsed = urlsplit(target)
    assert (method, parsed.path, parse_qs(parsed.query)) == ("GET", path, query)
    assert authorization == "Bearer " + TOKEN
    assert accept == "application/json"


def test_votes_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "self": "ignored",
                "votes": 1,
                "hasVoted": True,
                "voters": [
                    {
                        "self": "ignored",
                        "name": "alice",
                        "displayName": "Alice A",
                        "active": True,
                    }
                ],
                "unknown": {"nested": [1, None]},
            },
        )
    ]
    result = jira.get_issue_votes(
        base,
        "https://untrusted.example/browse/EX-1",
        token=TOKEN,
        allow_http_loopback=True,
    )
    assert result == {
        "voters": [{"name": "alice", "displayName": "Alice A"}],
        "hasVoted": True,
        "watchCount": None,
    }
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/votes", {})
    assert httpd.closed.wait(2)


def test_votes_missing_optional_fields_are_none(server):
    httpd, base = server
    httpd.responses = [(200, {"voters": [{"name": "bob"}]})]
    assert jira.get_issue_votes(
        base, "EX-2", token=TOKEN, allow_http_loopback=True
    ) == {
        "voters": [{"name": "bob", "displayName": None}],
        "hasVoted": None,
        "watchCount": None,
    }
    assert len(httpd.calls) == 1


def test_votes_projects_watch_count_only_when_server_reports_it(server):
    httpd, base = server
    httpd.responses = [(200, {"voters": [], "hasVoted": False, "watchCount": 4})]
    assert jira.get_issue_votes(
        base, "EX-3", token=TOKEN, allow_http_loopback=True
    ) == {
        "voters": [],
        "hasVoted": False,
        "watchCount": 4,
    }


def test_watchers_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "self": "ignored",
                "isWatching": True,
                "watchCount": 2,
                "watchers": [
                    {
                        "self": "ignored",
                        "name": "carol",
                        "displayName": "Carol C",
                        "emailAddress": "hidden@example",
                        "active": True,
                    },
                    {"name": "dave"},
                ],
            },
        )
    ]
    result = jira.get_issue_watchers(
        base, "EX-1", token=TOKEN, allow_http_loopback=True
    )
    assert result == {
        "watchers": [
            {"name": "carol", "displayName": "Carol C"},
            {"name": "dave", "displayName": None},
        ],
        "watchCount": 2,
        "isWatching": True,
    }
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/watchers", {})
    assert httpd.closed.wait(2)


def test_watchers_missing_optional_fields_are_none(server):
    httpd, base = server
    httpd.responses = [(200, {"watchers": []})]
    assert jira.get_issue_watchers(
        base, "EX-1", token=TOKEN, allow_http_loopback=True
    ) == {
        "watchers": [],
        "watchCount": None,
        "isWatching": None,
    }


def test_subtasks_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            [
                {
                    "id": "1",
                    "key": "EX-2",
                    "self": "ignored",
                    "fields": {
                        "summary": "child",
                        "status": {"name": "Open", "unknown": 1},
                        "issuetype": {"name": "Sub-task", "subtask": True},
                        "priority": {"name": "Minor"},
                    },
                },
                {"id": "2", "key": "EX-3", "self": "ignored"},
            ],
        )
    ]
    result = jira.list_issue_subtasks(
        base, "EX-1", token=TOKEN, allow_http_loopback=True
    )
    assert result == [
        {"key": "EX-2", "summary": "child", "type": "Sub-task", "status": "Open"},
        {"key": "EX-3", "summary": None, "type": None, "status": None},
    ]
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/subtask", {})
    assert httpd.closed.wait(2)


def test_subtasks_reject_bad_entry_without_partial_list(server):
    httpd, base = server
    httpd.responses = [
        (200, [{"key": "EX-2", "fields": {"summary": "ok"}}, {"fields": {}}])
    ]
    with pytest.raises(AtlaWireError):
        jira.list_issue_subtasks(base, "EX-1", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1


def test_comment_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "self": "ignored",
                "id": "42",
                "author": {"name": "alice", "displayName": "Alice A"},
                "updateAuthor": {"name": "bob"},
                "body": "wiki body",
                "created": "2026-05-19T11:58:06.033+0300",
                "updated": "2026-05-19T11:58:06.033+0300",
                "unknown": "ignored",
            },
        )
    ]
    result = jira.get_issue_comment(
        base, "EX-1", 42, token=TOKEN, allow_http_loopback=True
    )
    assert result == {
        "id": "42",
        "author": "alice",
        "body": "wiki body",
        "created": "2026-05-19T11:58:06.033+0300",
        "updated": "2026-05-19T11:58:06.033+0300",
    }
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/comment/42", {})
    assert httpd.closed.wait(2)


def test_comment_accepts_text_id_and_missing_fields_are_none(server):
    httpd, base = server
    httpd.responses = [(200, {"id": "42"})]
    assert jira.get_issue_comment(
        base, "EX-1", "42", token=TOKEN, allow_http_loopback=True
    ) == {
        "id": "42",
        "author": None,
        "body": None,
        "created": None,
        "updated": None,
    }
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/comment/42", {})


def test_worklog_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "self": "ignored",
                "id": "34003",
                "author": {"name": "maxim", "displayName": "Maxim B"},
                "updateAuthor": {"name": "maxim"},
                "comment": "done",
                "started": "2026-10-30T10:30:00.000+0300",
                "created": "2026-10-30T12:09:45.991+0300",
                "timeSpent": "1m",
                "timeSpentSeconds": 60,
                "issueId": "58652",
            },
        )
    ]
    result = jira.get_issue_worklog(
        base, "EX-1", "34003", token=TOKEN, allow_http_loopback=True
    )
    assert result == {
        "id": "34003",
        "author": "maxim",
        "started": "2026-10-30T10:30:00.000+0300",
        "seconds": 60,
        "comment": "done",
    }
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/worklog/34003", {})
    assert httpd.closed.wait(2)


def test_worklog_missing_optional_fields_are_none(server):
    httpd, base = server
    httpd.responses = [(200, {"id": "34003"})]
    assert jira.get_issue_worklog(
        base, "EX-1", 34003, token=TOKEN, allow_http_loopback=True
    ) == {
        "id": "34003",
        "author": None,
        "started": None,
        "seconds": None,
        "comment": None,
    }


def test_properties_projection_keeps_only_names(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "keys": [
                    {"self": "ignored", "key": "p.one"},
                    {"self": "ignored", "key": "p.two"},
                ],
                "unknown": 1,
            },
        )
    ]
    result = jira.get_issue_properties(
        base, "EX-1", token=TOKEN, allow_http_loopback=True
    )
    assert result == {"keys": ["p.one", "p.two"]}
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/properties", {})
    assert httpd.closed.wait(2)


def test_properties_empty_response_is_empty_keys(server):
    httpd, base = server
    httpd.responses = [(200, {"keys": []})]
    assert jira.get_issue_properties(
        base, "EX-1", token=TOKEN, allow_http_loopback=True
    ) == {"keys": []}


def test_property_projection_returns_value_unchanged(server):
    httpd, base = server
    value = {"baseline_start": "1779062400000", "nested": [None, 1]}
    httpd.responses = [(200, {"key": "p.one", "value": value})]
    result = jira.get_issue_property(
        base, "EX-1", "p.one", token=TOKEN, allow_http_loopback=True
    )
    assert result == {"key": "p.one", "value": value}
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issue/EX-1/properties/p.one", {})
    assert httpd.closed.wait(2)


def test_property_key_is_one_encoded_path_segment(server):
    httpd, base = server
    httpd.responses = [(200, {"key": "weird key+plus", "value": None})]
    result = jira.get_issue_property(
        base, "EX-1", "weird key+plus", token=TOKEN, allow_http_loopback=True
    )
    assert result == {"key": "weird key+plus", "value": None}
    parsed = urlsplit(httpd.calls[0][1])
    assert parsed.path == ("/rest/api/2/issue/EX-1/properties/weird%20key%2Bplus")
    assert unquote(parsed.path) == "/rest/api/2/issue/EX-1/properties/weird key+plus"
    assert parse_qs(parsed.query) == {}


def test_issue_link_projection_and_wire_path(server):
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "id": "52461",
                "self": "ignored",
                "type": {
                    "id": "10003",
                    "name": "Blocks",
                    "inward": "blocks",
                    "outward": "is blocked by",
                },
                "inwardIssue": {"id": "53865", "key": "EX-2", "self": "ignored"},
                "outwardIssue": {"id": "53864", "key": "EX-1", "self": "ignored"},
            },
        )
    ]
    result = jira.get_issue_link(base, 52461, token=TOKEN, allow_http_loopback=True)
    assert result == {
        "id": "52461",
        "type": "Blocks",
        "inwardIssue": "EX-2",
        "outwardIssue": "EX-1",
    }
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/issueLink/52461", {})
    assert httpd.closed.wait(2)


def test_issue_link_missing_sides_are_none(server):
    httpd, base = server
    httpd.responses = [(200, {"id": "7"})]
    assert jira.get_issue_link(base, "7", token=TOKEN, allow_http_loopback=True) == {
        "id": "7",
        "type": None,
        "inwardIssue": None,
        "outwardIssue": None,
    }


@pytest.mark.parametrize("value", ["abc", "0", "01", "-1", 0, True, 1.5, None])
def test_invalid_comment_id_never_reaches_the_network(server, value):
    httpd, base = server
    with pytest.raises(AtlaWireError) as error:
        jira.get_issue_comment(
            base, "EX-1", value, token=TOKEN, allow_http_loopback=True
        )
    assert str(error.value) == "Expected a Jira comment as a positive integer ID."
    assert TOKEN not in str(error.value)
    assert httpd.calls == []


@pytest.mark.parametrize(
    "kind,bad",
    [
        ("worklog", "abc"),
        ("worklog", 0),
        ("worklog", "01"),
        ("link", -1),
        ("link", True),
        ("link", None),
    ],
)
def test_invalid_worklog_and_link_ids_never_reach_the_network(server, kind, bad):
    httpd, base = server
    if kind == "worklog":
        call = lambda value: jira.get_issue_worklog(
            base, "EX-1", value, token=TOKEN, allow_http_loopback=True
        )
        expected = "Expected a Jira worklog as a positive integer ID."
    else:
        call = lambda value: jira.get_issue_link(
            base, value, token=TOKEN, allow_http_loopback=True
        )
        expected = "Expected a Jira issue link as a positive integer ID."
    with pytest.raises(AtlaWireError) as error:
        call(bad)
    assert str(error.value) == expected
    assert httpd.calls == []


@pytest.mark.parametrize(
    "key", ["", "   ", "..", "a/b", "a\\b", "x" * 256, "..%2F..%2Fadmin"]
)
def test_invalid_property_key_never_reaches_the_network(server, key):
    httpd, base = server
    with pytest.raises(AtlaWireError):
        jira.get_issue_property(
            base, "EX-1", key, token=TOKEN, allow_http_loopback=True
        )
    assert httpd.calls == []


CALLS = (
    (
        "votes",
        lambda base: jira.get_issue_votes(
            base, "EX-1", token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "watchers",
        lambda base: jira.get_issue_watchers(
            base, "EX-1", token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "subtasks",
        lambda base: jira.list_issue_subtasks(
            base, "EX-1", token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "comment",
        lambda base: jira.get_issue_comment(
            base, "EX-1", 42, token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "worklog",
        lambda base: jira.get_issue_worklog(
            base, "EX-1", 42, token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "properties",
        lambda base: jira.get_issue_properties(
            base, "EX-1", token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "property",
        lambda base: jira.get_issue_property(
            base, "EX-1", "p.one", token=TOKEN, allow_http_loopback=True
        ),
    ),
    (
        "link",
        lambda base: jira.get_issue_link(
            base, 42, token=TOKEN, allow_http_loopback=True
        ),
    ),
)


@pytest.mark.parametrize("name,call", CALLS, ids=[name for name, _ in CALLS])
def test_http_404_is_sanitized_and_not_retried(server, name, call):
    httpd, base = server
    httpd.responses = [(404, {"errorMessages": [BODY_MARKER, TOKEN]})]
    with pytest.raises(AtlaWireError) as error:
        call(base)
    assert error.value.category == "http"
    assert error.value.http_status == 404
    assert str(error.value) == "HTTP 404: request failed."
    text = "".join(traceback.format_exception(error.value))
    assert TOKEN not in text and BODY_MARKER not in text
    assert len(httpd.calls) == 1
    assert httpd.closed.wait(2)


@pytest.mark.parametrize("name,call", CALLS, ids=[name for name, _ in CALLS])
def test_successful_payload_echoing_token_is_rejected(server, name, call):
    httpd, base = server
    httpd.responses = [(200, {"echo": [TOKEN]})]
    with pytest.raises(AtlaWireError) as error:
        call(base)
    assert str(error.value) == "The response contained the session bearer token."
    text = "".join(traceback.format_exception(error.value))
    assert TOKEN not in text
    assert len(httpd.calls) == 1

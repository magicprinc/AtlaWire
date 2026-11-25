"""Black-box behaviour tests for ``atlawire.jira.titles``.

Contract: the ``titles`` docstring in ``atlawire/jira.py`` (lines 398-440) and
the original it mirrors, ``bbk/jira.py:309``. Unique keys are read in
input-ordered batches of 50; each batch is one ``key in (...)`` JQL GET with
``fields=summary`` and ``maxResults`` equal to the batch size. Issues the
search does not return are omitted, an empty key list sends nothing, and keys
are validated before any session exists. Expected values below are literals
taken from that contract, not from production helpers.

No production function is patched: the tests point the public ``base_url`` and
``token`` arguments at a local HTTP server on an ephemeral 127.0.0.1 port.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-titles"
SENTINEL = "synthetic-response-sentinel-titles"
SEARCH_PATH = "/rest/api/2/search"


def summary_of(key):
    return f"Summary of {key}"


def envelope(keys):
    """Search envelope whose issues deliberately arrive in reverse order.

    Reversing proves that the returned mapping follows the input key order
    rather than the order of the ``issues`` array (contract: input order).
    """
    issues = [
        {"key": key, "fields": {"summary": summary_of(key)}} for key in reversed(keys)
    ]
    return {"issues": issues}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "query": parse_qs(urlsplit(self.path).query),
                }
            )
            index = min(len(self.server.calls) - 1, len(self.server.responses) - 1)
            status, value = self.server.responses[index]
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.responses = [(200, {"issues": []})]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join(timeout=5)
    httpd.server_close()
    assert not thread.is_alive()


def test_120_unique_keys_use_three_ordered_batches(server):
    httpd, base = server
    # 120 distinct keys plus one duplicate input = 121 list entries. Per the
    # contract the duplicate collapses in input order, so the batches are
    # exactly 50/50/20 and cost exactly three GETs (jira.py:398; bbk:309).
    keys = [f"SPEC-{number}" for number in range(1, 121)]
    requested = [*keys[:60], keys[5], *keys[60:]]
    assert len(requested) == 121
    assert len(set(requested)) == 120
    missing = keys[110]
    batches = [keys[:50], keys[50:100], keys[100:]]
    httpd.responses = [
        (200, envelope([key for key in batch if key != missing])) for batch in batches
    ]

    result = jira.titles(base, requested, token=TOKEN, allow_http_loopback=True)

    assert len(httpd.calls) == 3
    expected_queries = [
        {
            "jql": ["key in (" + ",".join(batch) + ")"],
            "fields": ["summary"],
            "maxResults": [str(size)],
        }
        for batch, size in zip(batches, (50, 50, 20), strict=True)
    ]
    assert [call["query"] for call in httpd.calls] == expected_queries
    for call in httpd.calls:
        assert call["method"] == "GET"
        assert urlsplit(call["path"]).path == SEARCH_PATH
        assert call["authorization"] == "Bearer " + TOKEN
    assert [call["query"]["maxResults"][0] for call in httpd.calls] == [
        "50",
        "50",
        "20",
    ]

    expected_keys = [key for key in keys if key != missing]
    assert result == {key: summary_of(key) for key in expected_keys}
    assert list(result) == expected_keys
    assert missing not in result
    assert len(result) == 119


def test_49_keys_use_one_request(server):
    httpd, base = server
    keys = [f"SPEC-{number}" for number in range(1, 50)]
    httpd.responses = [(200, envelope(keys))]

    result = jira.titles(base, keys, token=TOKEN, allow_http_loopback=True)

    assert len(httpd.calls) == 1
    call = httpd.calls[0]
    assert call["method"] == "GET"
    assert urlsplit(call["path"]).path == SEARCH_PATH
    assert call["authorization"] == "Bearer " + TOKEN
    assert call["query"] == {
        "jql": ["key in (" + ",".join(keys) + ")"],
        "fields": ["summary"],
        "maxResults": ["49"],
    }
    assert result == {key: summary_of(key) for key in keys}
    assert list(result) == keys


def test_empty_key_list_sends_no_request(server):
    httpd, base = server

    assert jira.titles(base, [], token=TOKEN, allow_http_loopback=True) == {}

    assert httpd.calls == []


def test_second_batch_http_error_is_sanitized_and_not_retried(server, capsys, caplog):
    httpd, base = server
    keys = [f"SPEC-{number}" for number in range(1, 61)]
    httpd.responses = [
        (200, envelope(keys[:50])),
        (500, {"errorMessages": [SENTINEL, TOKEN]}),
    ]

    with pytest.raises(AtlaWireError) as raised:
        jira.titles(base, keys, token=TOKEN, allow_http_loopback=True)

    error = raised.value
    # Failure classification is structured, the diagnostic is generic, and
    # neither the body nor the credential leaks (atlawire/http.py status
    # policy; the same sanitization contract as bbk:309's JQL reads).
    assert error.category == "http"
    assert error.http_status == 500
    assert "HTTP 500" in str(error)
    captured = capsys.readouterr()
    text = (
        "".join(traceback.format_exception(error))
        + captured.out
        + captured.err
        + caplog.text
    )
    assert SENTINEL not in text
    assert TOKEN not in text
    assert len(httpd.calls) == 2


@pytest.mark.parametrize(
    "keys",
    [
        ["SPEC-1", 42],
        ["SPEC-1", "spec-2"],
        ["SPEC-1", "SPEC-"],
        "SPEC-1",
    ],
    ids=["non-string-key", "lowercase-key", "no-number-key", "not-a-list"],
)
def test_invalid_input_never_reaches_the_network(server, keys):
    httpd, base = server

    # The list and every key are validated before a session is created
    # (jira.py:398), so no request may be sent for invalid input.
    with pytest.raises(AtlaWireError):
        jira.titles(base, keys, token=TOKEN, allow_http_loopback=True)

    assert httpd.calls == []

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-batch-token"
SECRET_BODY = "synthetic-batch-error-body"
SHA = "a" * 40
PR = {
    "id": 42,
    "title": "A title",
    "state": "OPEN",
    "fromRef": {
        "latestCommit": SHA,
        "repository": {"project": {"key": "FORK"}, "slug": "copy"},
    },
    "toRef": {
        "latestCommit": "b" * 40,
        "repository": {"project": {"key": "DEST"}, "slug": "target"},
    },
    "extra": {"nested": [1, None]},
}
MERGE = {
    "canMerge": False,
    "conflicted": True,
    "vetoes": [{"summary": "reason"}],
    "extra": [1],
}
TAG = {
    "id": "refs/tags/release/v1",
    "displayId": "release/v1",
    "latestCommit": SHA,
    "extra": {"x": 1},
}
COMMIT = {
    "id": SHA,
    "message": "message\nsecond line",
    "author": {"name": "Ada"},
    "parents": [{"id": "b" * 40}],
    "extra": [1],
}
TEXT = "first line\nsecond: café\n"
CASES = ["pr", "merge", "tag", "commit", "repo_file", "pr_file"]


@pytest.fixture
def server(request):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self):
            try:
                super().handle()
            except ConnectionResetError, ConnectionAbortedError:
                pass

        def finish(self):
            try:
                super().finish()
            finally:
                with self.server.connection_condition:
                    self.server.closed_connections.add(self.client_address)
                    self.server.connection_condition.notify_all()

        def do_GET(self):
            with self.server.connection_condition:
                self.server.request_connections.add(self.client_address)
            self.server.calls.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            failure = self.server.status != 200 and (
                not self.server.fail_raw or "/raw/" in self.path
            )
            if failure:
                message = SECRET_BODY + (TOKEN if self.server.echo_token else "")
                body = json.dumps({"errors": [{"message": message}]}).encode()
                status = self.server.status
            elif "/raw/" in self.path:
                body, status = TEXT.encode(), 200
            else:
                body, status = json.dumps(self.server.payload).encode(), 200
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
                if not failure and "/raw/" in self.path
                else "application/json",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.connection_condition = threading.Condition()
    httpd.request_connections = set()
    httpd.closed_connections = set()
    httpd.status = 200
    httpd.fail_raw = False
    httpd.echo_token = False
    httpd.payload = PR
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def close():
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()

    request.addfinalizer(close)
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def invoke(case, base):
    options = {"token": TOKEN, "allow_http_loopback": True}
    if case == "pr":
        return bitbucket.get_pull_request(base, "PROJ/repo", 42, **options)
    if case == "merge":
        return bitbucket.get_pull_request_merge_status(base, "PROJ/repo", 42, **options)
    if case == "tag":
        return bitbucket.get_tag(base, "PROJ/repo", "release/v1", **options)
    if case == "commit":
        return bitbucket.get_commit(base, "PROJ/repo", "aaaaaaa", **options)
    if case == "repo_file":
        return bitbucket.get_repository_file(
            base, "PROJ/repo", "dir/a file.txt", at="refs/heads/main", **options
        )
    return bitbucket.get_pull_request_file(
        base, "PROJ/repo", 42, "dir/a file.txt", **options
    )


def configure(httpd, case):
    httpd.payload = {
        "pr": PR,
        "merge": MERGE,
        "tag": TAG,
        "commit": COMMIT,
        "repo_file": PR,
        "pr_file": PR,
    }[case]


@pytest.mark.parametrize("case", CASES)
def test_wire_route_query_and_bearer(server, case):
    httpd, base = server
    configure(httpd, case)
    invoke(case, base)
    root = "/rest/api/1.0/projects/PROJ/repos/repo"
    targets = {
        "pr": [root + "/pull-requests/42"],
        "merge": [root + "/pull-requests/42/merge"],
        "tag": [root + "/tags/release/v1"],
        "commit": [root + "/commits/aaaaaaa"],
        "repo_file": [root + "/raw/dir/a%20file.txt?at=refs%2Fheads%2Fmain"],
        "pr_file": [
            root + "/pull-requests/42",
            "/rest/api/1.0/projects/FORK/repos/copy/raw/dir/a%20file.txt?at=" + SHA,
        ],
    }
    assert httpd.calls == [
        ("GET", target, "Bearer " + TOKEN) for target in targets[case]
    ]


@pytest.mark.parametrize("case", CASES)
def test_result_preserves_server_fields_or_text(server, case):
    httpd, base = server
    configure(httpd, case)
    expected = {
        "pr": PR,
        "merge": MERGE,
        "tag": TAG,
        "commit": COMMIT,
        "repo_file": TEXT,
        "pr_file": TEXT,
    }
    assert invoke(case, base) == expected[case]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_http_errors_are_typed_and_sanitized(server, case, status, capsys, caplog):
    httpd, base = server
    configure(httpd, case)
    httpd.status = status
    httpd.fail_raw = case == "pr_file"
    with pytest.raises(AtlaWireError) as caught:
        invoke(case, base)
    assert caught.value.category == "http"
    assert caught.value.http_status == status
    captured = capsys.readouterr()
    text = (
        str(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + captured.out
        + captured.err
        + caplog.text
    )
    assert TOKEN not in text
    assert SECRET_BODY not in text
    assert len(httpd.calls) == (2 if case == "pr_file" else 1)


@pytest.mark.parametrize("case", CASES)
def test_http_error_echo_of_token_is_sanitized_and_keeps_status(
    server, case, capsys, caplog
):
    httpd, base = server
    configure(httpd, case)
    httpd.status = 401
    httpd.fail_raw = case == "pr_file"
    httpd.echo_token = True
    with pytest.raises(AtlaWireError) as caught:
        invoke(case, base)
    captured = capsys.readouterr()
    text = (
        str(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + captured.out
        + captured.err
        + caplog.text
    )
    assert TOKEN not in text
    assert SECRET_BODY not in text
    assert caught.value.category == "http"
    assert caught.value.http_status == 401
    assert len(httpd.calls) == (2 if case == "pr_file" else 1)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("status", [200, 401])
def test_connection_closes_after_success_and_error(server, case, status):
    httpd, base = server
    configure(httpd, case)
    httpd.status = status
    httpd.fail_raw = case == "pr_file"
    if status == 200:
        invoke(case, base)
    else:
        with pytest.raises(AtlaWireError) as caught:
            invoke(case, base)
        assert caught.value.category == "http"
        assert caught.value.http_status == status
    assert len(httpd.calls) == (2 if case == "pr_file" else 1)
    with httpd.connection_condition:
        assert httpd.connection_condition.wait_for(
            lambda: (
                bool(httpd.request_connections)
                and httpd.request_connections <= httpd.closed_connections
            ),
            timeout=3,
        ), "client left an HTTP connection open"

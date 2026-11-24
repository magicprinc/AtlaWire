"""Cross-repository search against a loopback Bitbucket with two repositories."""

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from atlawire.http import AtlaWireError
from atlawire.repo_search import search_repositories

TOKEN = "synthetic-repo-search-token"
SHA = "a" * 40
PREFIX = "/rest/api/1.0/projects/PRJ/repos"

FILES = {
    "alpha": {"src/A.java": "class Alpha {\n  int needle;\n}\n"},
    "beta": {"src/B.java": "// nothing\n", "src/C.java": "int needle = 1;\n"},
}


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class _State:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_raw: str | None = None
        self.archive_override: bytes | None = None


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_POST(self):
            state.calls.append(f"POST {urlsplit(self.path).path}")
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            body = json.dumps(
                {
                    "code": {
                        "isLastPage": True,
                        "values": [
                            {
                                "file": "src/A.java",
                                "repository": {
                                    "project": {"key": "PRJ"},
                                    "slug": "alpha",
                                },
                                "hitCount": 1,
                                "hitContexts": [
                                    [{"line": 2, "text": "int <em>needle</em>;"}]
                                ],
                            }
                        ],
                    }
                }
            ).encode()
            self._send("application/json", body)

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            state.calls.append(path)
            slug = self._slug(path)
            if path == PREFIX:
                self._json(
                    {
                        "values": [{"slug": name, "name": name} for name in FILES],
                        "isLastPage": True,
                        "start": 0,
                        "size": len(FILES),
                        "limit": 100,
                    }
                )
            elif path == f"{PREFIX}/{slug}/branches/default":
                self._json({"latestCommit": SHA, "id": "main"})
            elif path == f"{PREFIX}/{slug}/files":
                self._json(
                    {
                        "values": list(FILES[slug]),
                        "isLastPage": True,
                        "start": 0,
                        "size": len(FILES[slug]),
                        "limit": 100,
                    }
                )
            elif path == f"{PREFIX}/{slug}/archive":
                entries = state.archive_override or dict(FILES[slug])
                self._send("application/zip", _zip(entries))
            elif path.startswith(f"{PREFIX}/{slug}/raw/"):
                name = path.split("/raw/", 1)[1]
                if state.fail_raw == slug:
                    self.send_error(500)
                    return
                self._send("text/plain", FILES[slug][name].encode())
            else:
                self.send_error(404)

        def _slug(self, path):
            tail = path[len(PREFIX) + 1 :]
            return tail.split("/", 1)[0]

        def _json(self, value):
            self._send("application/json", json.dumps(value).encode())

        def _send(self, content_type, body):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _search(base, **kwargs):
    return search_repositories(
        base,
        "needle",
        token=TOKEN,
        project="PRJ",
        engine="bytes",
        allow_http_loopback=True,
        **kwargs,
    )


def test_bytes_engine_finds_matches_across_repositories(server):
    _state, base = server

    result = _search(base)

    assert result["status"] == "complete"
    assert result["complete"] is True
    assert sorted(
        (row["repo"], row["path"], row["line"]) for row in result["rows"]
    ) == [
        ("PRJ/alpha", "src/A.java", 2),
        ("PRJ/beta", "src/C.java", 1),
    ]
    assert result["repositories_scanned"] == 2
    assert result["files_eligible"] == 3


def test_archive_fetch_uses_one_request_per_repository(server):
    state, base = server
    files_calls = len(_search(base)["rows"])

    state.calls.clear()
    archived = _search(base, fetch="archive")

    assert files_calls == 2
    assert [call for call in state.calls if call.endswith("/archive")] == [
        f"{PREFIX}/alpha/archive",
        f"{PREFIX}/beta/archive",
    ]
    assert [row["path"] for row in archived["rows"]] == ["src/A.java", "src/C.java"]


def test_archive_rejects_an_unsafe_entry_name(server):
    state, base = server
    state.archive_override = {"../escape.txt": "needle"}

    with pytest.raises(AtlaWireError, match="unsafe entry"):
        _search(base, fetch="archive")


def test_repository_budget_caps_the_walk_and_reports_it(server):
    _state, base = server

    result = _search(base, max_repos=1)

    assert result["repositories_scanned"] == 1
    assert result["repositories_total"] == 2
    assert result["truncated"] is True
    assert result["complete"] is False


def test_workers_merge_in_repository_order(server):
    _state, base = server

    sequential = _search(base, workers=1)
    parallel = _search(base, workers=2)

    assert [row["repo"] for row in parallel["rows"]] == [
        row["repo"] for row in sequential["rows"]
    ]


def test_a_later_read_failure_returns_no_partial_rows(server):
    state, base = server
    state.fail_raw = "beta"

    with pytest.raises(AtlaWireError):
        _search(base)


def test_index_engine_makes_one_search_request(server):
    state, base = server

    result = search_repositories(
        base,
        "needle",
        token=TOKEN,
        project="PRJ",
        engine="index",
        allow_http_loopback=True,
    )

    assert [call for call in state.calls if call.startswith("POST ")] == [
        "POST /rest/search/latest/search"
    ]
    assert result["engine"] == "index"
    assert result["rows"][0]["path"] == "src/A.java"
    assert result["rows"][0]["line"] == 2


def test_auto_uses_index_for_a_literal_and_bytes_for_a_regex(server):
    _state, base = server

    literal = search_repositories(
        base, "needle", token=TOKEN, project="PRJ", allow_http_loopback=True
    )
    regex = search_repositories(
        base, "needle.*", token=TOKEN, project="PRJ", allow_http_loopback=True
    )

    assert literal["engine"] == "index"
    assert regex["engine"] == "bytes"


def test_index_engine_rejects_archive_fetch(server):
    _state, base = server

    with pytest.raises(AtlaWireError, match="archive fetch"):
        search_repositories(
            base,
            "needle",
            token=TOKEN,
            project="PRJ",
            engine="index",
            fetch="archive",
            allow_http_loopback=True,
        )

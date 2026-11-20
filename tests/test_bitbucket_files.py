"""Focused library checks for repository and pull request file reads."""

import gzip
import json
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler
from typing import ClassVar, Self, cast

import pytest
import requests

from atlawire import bitbucket, http
from atlawire.http import AtlaWireError
from tests._loopback import Request, request_record, send_bytes, serving

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
PR_ID = "7"
SHA_NEW = "a" * 40
SHA_OLD = "b" * 40
PR_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/{PR_ID}"


def forbid_session(token: str) -> object:
    raise AssertionError("session created before validation")


def pull_request() -> dict[str, object]:
    return {
        "id": 7,
        "title": "Talking Nerdy",
        "state": "OPEN",
        "fromRef": {
            "displayId": "fork-display",
            "latestCommit": SHA_NEW,
            "repository": {"slug": "source", "project": {"key": "FORK"}},
        },
        "toRef": {
            "displayId": "target-display",
            "latestCommit": SHA_OLD,
            "repository": {"slug": "target", "project": {"key": "DEST"}},
        },
        "links": {"self": [{"href": "https://untrusted.invalid/elsewhere"}]},
    }


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute",
        "trailing/",
        "empty//segment",
        ".",
        "..",
        "./file",
        "dir/.",
        "dir/..",
        "../secret",
        "dir/../secret",
        "/../secret",
        "back\\slash",
        "line\nbreak",
        "carriage\rreturn",
        "tab\there",
        "nul\x00byte",
        "del\x7fbyte",
        "c1\x85byte",
        "surrogate\ud800byte",
        "literal%20escape",
        "literal%2Eescape",
        "%2e%2e/file",
    ],
    ids=[
        "empty",
        "leading-slash",
        "trailing-slash",
        "empty-segment",
        "dot",
        "dot-dot",
        "dot-prefix",
        "inner-dot",
        "inner-dot-dot",
        "parent",
        "inner-parent",
        "leading-parent",
        "backslash",
        "lf",
        "cr",
        "tab",
        "nul",
        "del",
        "c1",
        "surrogate",
        "percent-20",
        "percent-2e",
        "encoded-dot-dot",
    ],
)
def test_unsafe_paths_are_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="file path") as error:
        bitbucket.get_repository_file(BASE, REPO, path, token=TOKEN)

    if len(path) > 1:
        assert path not in str(error.value)


@pytest.mark.parametrize(
    ("path", "encoded"),
    [
        (
            "папка/a b#?%.txt",
            "%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/a%20b%23%3F%25.txt",
        ),
        ("dir/100%.txt", "dir/100%25.txt"),
        ("dir/naïve !.txt", "dir/na%C3%AFve%20%21.txt"),
        ("dir/.../file..", "dir/.../file.."),
    ],
    ids=[
        "unicode-space-hash-query-percent",
        "literal-percent",
        "unicode",
        "dots-in-name",
    ],
)
def test_safe_paths_are_encoded_exactly_once(
    monkeypatch: pytest.MonkeyPatch, path: str, encoded: str
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_get_text(session: object, url: str, *, params: dict[str, str]) -> str:
        calls.append((url, dict(params)))
        return "contents"

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_text", fake_get_text)

    assert bitbucket.get_repository_file(BASE, REPO, path, token=TOKEN) == "contents"
    assert calls == [
        (
            f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/raw/{encoded}",
            {"at": "master"},
        )
    ]


@pytest.mark.parametrize(
    "at",
    [
        "",
        "line\nbreak",
        "carriage\rreturn",
        "nul\x00byte",
        "del\x7fbyte",
        "surrogate\ud800",
    ],
    ids=["empty", "lf", "cr", "nul", "del", "surrogate"],
)
def test_unsafe_revisions_are_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="revision"):
        bitbucket.get_repository_file(BASE, REPO, "file.txt", token=TOKEN, at=at)


def test_revision_is_sent_only_as_a_query_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_get_text(session: object, url: str, *, params: dict[str, str]) -> str:
        calls.append((url, dict(params)))
        return "contents"

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_text", fake_get_text)

    bitbucket.get_repository_file(
        BASE, REPO, "file.txt", token=TOKEN, at="feature/x+y z"
    )

    assert calls == [
        (
            f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/raw/file.txt",
            {"at": "feature/x+y z"},
        )
    ]


@pytest.mark.parametrize("side", ["", "NEW", "base", "fromRef"])
def test_invalid_side_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="side"):
        bitbucket.get_pull_request_file(
            BASE, REPO, PR_ID, "file.txt", token=TOKEN, side=side
        )


def test_invalid_pr_path_is_rejected_before_the_pull_request_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="file path"):
        bitbucket.get_pull_request_file(BASE, REPO, PR_ID, "../secret", token=TOKEN)


def test_repository_file_streams_exact_text_with_crlf_and_bom() -> None:
    body = b"\xef\xbb\xbffirst  \r\nsecond\t\r\nlast"
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            send_bytes(self, 200, body)

    with serving(Handler) as server:
        result = bitbucket.get_repository_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            "file.txt",
            token=TOKEN,
            allow_http_loopback=True,
        )

    assert result == "\ufefffirst  \r\nsecond\t\r\nlast"
    assert seen == [
        (
            "GET",
            f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/raw/file.txt",
            {"at": ["master"]},
            f"Bearer {TOKEN}",
        )
    ]
    assert accepts == ["text/plain"]


def pr_handler(
    value: object, seen: list[Request], accepts: list[str | None]
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            if len(seen) > 1:
                send_bytes(self, 200, b"raw contents")
                return
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


@pytest.mark.parametrize(
    ("side", "project", "slug", "commit"),
    [("new", "FORK", "source", SHA_NEW), ("old", "DEST", "target", SHA_OLD)],
)
def test_pr_file_uses_only_the_selected_ref_repository_and_commit(
    side: str, project: str, slug: str, commit: str
) -> None:
    seen: list[Request] = []
    accepts: list[str | None] = []

    with serving(pr_handler(pull_request(), seen, accepts)) as server:
        result = bitbucket.get_pull_request_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            PR_ID,
            "src/a b#?.txt",
            token=TOKEN,
            side=side,
            allow_http_loopback=True,
        )

    assert result == "raw contents"
    assert seen == [
        ("GET", PR_PATH, {}, f"Bearer {TOKEN}"),
        (
            "GET",
            (
                f"{CONTEXT}/rest/api/1.0/projects/{project}/repos/{slug}"
                "/raw/src/a%20b%23%3F.txt"
            ),
            {"at": [commit]},
            f"Bearer {TOKEN}",
        ),
    ]
    assert accepts == ["application/json", "text/plain"]


def bad_pr(level: str) -> dict[str, object]:
    value = pull_request()
    from_ref = cast(dict[str, object], value["fromRef"])
    repository = cast(dict[str, object], from_ref["repository"])
    if level == "missing-commit":
        del from_ref["latestCommit"]
    elif level == "short-commit":
        from_ref["latestCommit"] = "a" * 39
    elif level == "display-only":
        from_ref["latestCommit"] = ""
        from_ref["displayId"] = SHA_NEW
    elif level == "missing-project":
        del repository["project"]
    elif level == "missing-slug":
        del repository["slug"]
    elif level == "unsafe-key":
        repository["project"] = {"key": "../FORK"}
    elif level == "unsafe-slug":
        repository["slug"] = "../source"
    else:
        raise AssertionError(level)
    return value


@pytest.mark.parametrize(
    "level",
    [
        "missing-commit",
        "short-commit",
        "display-only",
        "missing-project",
        "missing-slug",
        "unsafe-key",
        "unsafe-slug",
    ],
)
def test_invalid_selected_metadata_fails_after_the_json_get_without_raw_get(
    level: str,
) -> None:
    seen: list[Request] = []
    accepts: list[str | None] = []

    with (
        serving(pr_handler(bad_pr(level), seen, accepts)) as server,
        pytest.raises(AtlaWireError, match="metadata") as error,
    ):
        bitbucket.get_pull_request_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            PR_ID,
            "file.txt",
            token=TOKEN,
            allow_http_loopback=True,
        )

    assert seen == [("GET", PR_PATH, {}, f"Bearer {TOKEN}")]
    assert accepts == ["application/json"]
    assert SHA_NEW not in str(error.value)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"first\nsecond\n", "first\nsecond\n"),
        (b"first\nsecond", "first\nsecond"),
        (b"first\r\nsecond\r\n", "first\r\nsecond\r\n"),
    ],
    ids=["lf-trailing", "lf-no-trailing", "crlf"],
)
def test_repository_file_preserves_lf_and_crlf_bytes_exactly(
    body: bytes, expected: str
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, body)

    with serving(Handler) as server:
        result = bitbucket.get_repository_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            "file.txt",
            token=TOKEN,
            allow_http_loopback=True,
        )

    assert result == expected


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        (b"ok", "application/json", "text/plain"),
        (b"\xff", "text/plain", "UTF-8"),
        (b"carriage\rreturn", "text/plain", "control"),
        (b"escape\x1b[31m", "text/plain", "control"),
        ("bidi\u202eoverride".encode(), "text/plain", "control"),
    ],
    ids=["non-text", "invalid-utf8", "bare-cr", "c0", "bidi"],
)
def test_repository_file_rejects_unpromised_text_without_a_result(
    body: bytes, content_type: str, expected: str
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, body, content_type=content_type)

    with (
        serving(Handler) as server,
        pytest.raises(AtlaWireError, match=expected),
    ):
        bitbucket.get_repository_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            "file.txt",
            token=TOKEN,
            allow_http_loopback=True,
        )


@pytest.mark.parametrize(
    ("size", "accepted"),
    [(1024 * 1024, True), (1024 * 1024 + 1, False)],
    ids=["exactly-one-mib", "one-byte-over"],
)
def test_repository_file_enforces_the_decoded_size_limit(
    size: int, accepted: bool
) -> None:
    body = gzip.compress(b"a" * size)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, body, content_encoding="gzip")

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        if accepted:
            result = bitbucket.get_repository_file(
                base, REPO, "file.txt", token=TOKEN, allow_http_loopback=True
            )
            assert result == "a" * size
        else:
            with pytest.raises(AtlaWireError, match="1 MiB"):
                bitbucket.get_repository_file(
                    base, REPO, "file.txt", token=TOKEN, allow_http_loopback=True
                )


def test_a_late_short_body_fails_without_returning_partial_text() -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, b"short", declared_length=50)

    with (
        serving(Handler) as server,
        pytest.raises(AtlaWireError, match="Request failed"),
    ):
        bitbucket.get_repository_file(
            f"http://127.0.0.1:{server.server_port}{CONTEXT}",
            REPO,
            "file.txt",
            token=TOKEN,
            allow_http_loopback=True,
        )


def test_transport_closes_the_response_after_a_read_error() -> None:
    class Response:
        status_code: ClassVar[int] = 200
        headers: ClassVar[dict[str, str]] = {"Content-Type": "text/plain"}
        closed = False

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            self.closed = True

        def iter_content(self, chunk_size: int) -> object:
            def chunks() -> object:
                yield b"partial"
                raise requests.ConnectionError("late failure")

            return chunks()

    class Session:
        response = Response()

        def get(self, *args: object, **kwargs: object) -> Response:
            return self.response

    session = Session()
    with pytest.raises(AtlaWireError, match="Request failed"):
        http.get_text(
            cast(requests.Session, session),
            "https://example.invalid/raw",
            params={"at": "master"},
        )

    assert session.response.closed

"""Loopback Bitbucket fixture shared by repository grep tests."""

import gzip
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlsplit

from tests._loopback import (
    Request,
    request_record,
    send_bytes,
    send_json,
)

CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
RAW_BASE = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets"

type Page = dict[str, object]
type RawResponse = tuple[bytes, str | None, str | None]


class Backend:
    """Mutable HTTP state for one loopback Bitbucket server."""

    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.branch_rows: list[Page] = []
        self.later_branch_rows: list[Page] | None = None
        self.branch_reads = 0
        self.default_branch: Page | None = None
        self.default_reads = 0
        self.commit_ids: set[str] = set()
        self.paths: list[str] = []
        self.file_pages: list[Page | int] | None = None
        self.file_reads = 0
        self.tags: dict[str, Page] = {}
        self.tag_reads = 0
        self.contents: dict[str, RawResponse] = {}
        self.failures: dict[str, int] = {}


def branch_row(name: str, commit: str, *, default: bool = False) -> Page:
    """Build one branch projection accepted by the branch adapter."""
    return {
        "displayId": name,
        "id": f"refs/heads/{name}",
        "latestCommit": commit,
        "isDefault": default,
    }


def raw_default_branch(commit: str | None) -> Page:
    """Build one raw default-branch response with ``latestCommit``."""
    return {
        "displayId": "main",
        "id": "refs/heads/main",
        "latestCommit": commit,
        "isDefault": True,
    }


def tag_row(
    name: str,
    commit: str | None,
    *,
    identifier: str | None = None,
    display_id: str | None = None,
) -> Page:
    """Build one tag object with overridable documented identity fields."""
    return {
        "id": name if identifier is None else identifier,
        "displayId": f"refs/tags/{name}" if display_id is None else display_id,
        "type": "TAG",
        "latestCommit": commit,
        "latestChangeset": commit,
        "hash": "",
    }


def text(body: str) -> RawResponse:
    """Build an eligible UTF-8 text response."""
    return body.encode("utf-8"), "text/plain; charset=utf-8", None


def binary(body: bytes = b"\x00\x01\x02binary") -> RawResponse:
    """Build a body the raw adapter refuses as non-text."""
    return body, "application/octet-stream", None


def oversize() -> RawResponse:
    """Build a gzip body whose decoded size exceeds the 1 MiB text cap."""
    return gzip.compress(b"a" * (1024 * 1024 + 1)), "text/plain", "gzip"


def handler_for(backend: Backend) -> type[BaseHTTPRequestHandler]:
    """Return a handler class bound to one mutable backend."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            backend.requests.append(request_record(self))
            path = urlsplit(self.path).path
            if path == f"{RAW_BASE}/branches/default":
                self._default_branch()
            elif path == f"{RAW_BASE}/branches":
                self._branches()
            elif path.startswith(f"{RAW_BASE}/tags/"):
                self._tag(unquote(path.split("/tags/", 1)[1]))
            elif path.startswith(f"{RAW_BASE}/commits/"):
                self._commit(path.rsplit("/", 1)[-1])
            elif path == f"{RAW_BASE}/files":
                self._files()
            elif path.startswith(f"{RAW_BASE}/raw/"):
                self._raw(unquote(path.split("/raw/", 1)[1]))
            else:
                send_json(self, 404, {"message": "unknown route"})

        def _default_branch(self) -> None:
            backend.default_reads += 1
            if backend.default_branch is None:
                send_bytes(self, 204, b"", content_type=None)
                return
            send_json(self, 200, backend.default_branch)

        def _branches(self) -> None:
            backend.branch_reads += 1
            rows = backend.branch_rows
            if backend.branch_reads > 1 and backend.later_branch_rows is not None:
                rows = backend.later_branch_rows
            send_json(self, 200, {"values": rows, "isLastPage": True})

        def _commit(self, identifier: str) -> None:
            known = {value.lower() for value in backend.commit_ids}
            if identifier.lower() not in known:
                send_json(self, 404, {"message": "missing commit"})
                return
            send_json(self, 200, {"id": identifier})

        def _tag(self, name: str) -> None:
            backend.tag_reads += 1
            tag = backend.tags.get(name)
            if tag is None:
                send_json(self, 404, {"message": "missing tag"})
                return
            send_json(self, 200, tag)

        def _files(self) -> None:
            backend.file_reads += 1
            if backend.file_pages is None:
                send_json(
                    self,
                    200,
                    {"values": backend.paths, "isLastPage": True},
                )
                return
            index = backend.file_reads - 1
            if index >= len(backend.file_pages):
                send_json(self, 500, {"message": "extra file page"})
                return
            page = backend.file_pages[index]
            if isinstance(page, int):
                send_json(self, page, {"message": "file page failed"})
                return
            send_json(self, 200, page)

        def _raw(self, name: str) -> None:
            status = backend.failures.get(name)
            if status is not None:
                send_json(self, status, {"message": "read failed"})
                return
            response = backend.contents.get(name)
            if response is None:
                send_json(self, 404, {"message": "missing file"})
                return
            body, content_type, content_encoding = response
            send_bytes(
                self,
                200,
                body,
                content_type=content_type,
                content_encoding=content_encoding,
            )

    return Handler


def origin(server: HTTPServer) -> str:
    """Return the loopback origin for one running server."""
    return f"http://127.0.0.1:{server.server_port}"


def environment(origin_url: str, token: str) -> dict[str, str]:
    """Build an environment where only the requested Bitbucket URL is valid."""
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin_url}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": token,
        "ATLAWIRE_JIRA_URL": f"{origin_url}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": "wrong-product-jira-grep",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin_url}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-confluence-grep",
    }


def base_arguments(origin_url: str) -> list[str]:
    """Return the per-command Bitbucket selectors used by the installed CLI."""
    return [
        "--base-url",
        f"{origin_url}{CONTEXT}/",
        "--allow-http-loopback",
        "--token-from-env",
    ]

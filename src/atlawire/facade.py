"""Public facade for stable, read-only Atlassian operations.

The facade owns the product namespaces, argument validation, fixed request
paths, and the success/error envelopes. It never exposes the underlying library
client, an arbitrary URL, an HTTP method, or an auth header, so a caller cannot
turn one of the listed operations into a different request.

Every method performs exactly one upstream request and returns either
``{"ok": True, "product": ..., "data": ...}`` or
``{"ok": False, "product": ..., "error": {...}}``. Expected failures are values,
not exceptions: an invalid argument or an unavailable saved credential returns
an envelope and sends no request.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

from atlawire.credentials import resolve_saved_credentials
from atlawire.http import AtlaWireError
from atlawire.sdk import SdkRequestError, get_json

__all__ = ["AtlaWire"]

_BODY_LIMIT = 8 * 1024
_LIMIT_MIN = 1
_LIMIT_MAX = 1000
_REDACT = "[REDACTED]"
_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,31}-[0-9]{1,10}")
_CONTENT_ID = re.compile(r"[0-9]{1,20}")
_PROJECT_KEY = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9_]{0,63}|~[A-Za-z0-9][A-Za-z0-9_.-]{0,63})"
)
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_PULL_REQUEST_ID = re.compile(r"[0-9]{1,12}")
_FORBIDDEN_TEXT = re.compile(
    r"[\x00-\x1f\x7f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ud800-\udfff]"
)
_MAX_QUERY = 8192


class _Validation(Exception):
    """A request-independent argument error with a safe message."""


@dataclass(frozen=True, slots=True)
class _Operation:
    """One named operation: product, required parameters, defaults, and shape."""

    product: str
    required: tuple[str, ...]
    defaults: Mapping[str, object]
    build: Callable[[Mapping[str, object]], tuple[str, dict[str, str | int]]]

    @property
    def declared(self) -> frozenset[str]:
        return frozenset(self.required) | frozenset(self.defaults)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise _Validation(message)
    return value


def _query(value: object, name: str) -> str:
    text = _text(value, f"Expected a non-empty {name} query.")
    if not text.strip():
        raise _Validation(f"Expected a non-empty {name} query.")
    if len(text) > _MAX_QUERY or _FORBIDDEN_TEXT.search(text):
        raise _Validation(f"Unsupported characters in the {name} query.")
    return text


def _segment(value: object, pattern: re.Pattern[str], message: str) -> str:
    text = _text(value, message)
    if pattern.fullmatch(text) is None or ".." in text:
        raise _Validation(message)
    return text


def _limit(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not _LIMIT_MIN <= value <= _LIMIT_MAX
    ):
        raise _Validation(
            f"The limit must be an integer between {_LIMIT_MIN} and {_LIMIT_MAX}."
        )
    return value


def _quoted(value: str) -> str:
    """Quote one complete path segment so it cannot change the route."""
    return quote(value, safe="")


def _issue_key(value: object) -> str:
    return _segment(
        value, _ISSUE_KEY, "Expected a Jira issue key such as ABC-123."
    )


def _content_id(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        value = str(value)
    return _segment(
        value, _CONTENT_ID, "Expected a numeric Confluence content id."
    )


def _project_key(value: object) -> str:
    return _segment(value, _PROJECT_KEY, "Expected a Bitbucket project key.")


def _repository_slug(value: object) -> str:
    return _segment(
        value, _REPOSITORY_SLUG, "Expected a Bitbucket repository slug."
    )


def _pull_request_id(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        value = str(value)
    return _segment(
        value, _PULL_REQUEST_ID, "Expected a numeric Bitbucket pull request id."
    )


def _jira_issue(params: Mapping[str, object]) -> tuple[str, dict[str, str | int]]:
    key = _issue_key(params["key"])
    return f"/rest/api/2/issue/{_quoted(key)}", {}


def _jira_search(params: Mapping[str, object]) -> tuple[str, dict[str, str | int]]:
    jql = _query(params["jql"], "JQL")
    limit = _limit(params["limit"])
    return "/rest/api/2/search", {"jql": jql, "maxResults": limit}


def _jira_projects(params: Mapping[str, object]) -> tuple[str, dict[str, str | int]]:
    return "/rest/api/2/project", {}


def _confluence_page(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    content_id = _content_id(params["content_id"])
    return f"/rest/api/content/{_quoted(content_id)}", {}


def _confluence_search(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    cql = _query(params["cql"], "CQL")
    limit = _limit(params["limit"])
    return "/rest/api/content/search", {"cql": cql, "limit": limit}


def _confluence_spaces(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    return "/rest/api/space", {"limit": _limit(params["limit"])}


def _bitbucket_repository(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    project = _project_key(params["project"])
    slug = _repository_slug(params["slug"])
    return (
        "/rest/api/1.0/projects/"
        f"{_quoted(project)}/repos/{_quoted(slug)}",
        {},
    )


def _bitbucket_projects(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    return "/rest/api/1.0/projects", {"limit": _limit(params["limit"])}


def _bitbucket_pull_request(
    params: Mapping[str, object],
) -> tuple[str, dict[str, str | int]]:
    project = _project_key(params["project"])
    slug = _repository_slug(params["slug"])
    pr_id = _pull_request_id(params["pr_id"])
    return (
        "/rest/api/1.0/projects/"
        f"{_quoted(project)}/repos/{_quoted(slug)}/pull-requests/{_quoted(pr_id)}",
        {},
    )


_OPERATIONS: dict[str, _Operation] = {
    "jira.get_issue": _Operation("jira", ("key",), {}, _jira_issue),
    "jira.search": _Operation("jira", ("jql",), {"limit": 50}, _jira_search),
    "jira.list_projects": _Operation("jira", (), {}, _jira_projects),
    "confluence.get_page": _Operation(
        "confluence", ("content_id",), {}, _confluence_page
    ),
    "confluence.search": _Operation(
        "confluence", ("cql",), {"limit": 25}, _confluence_search
    ),
    "confluence.list_spaces": _Operation(
        "confluence", (), {"limit": 25}, _confluence_spaces
    ),
    "bitbucket.get_repository": _Operation(
        "bitbucket", ("project", "slug"), {}, _bitbucket_repository
    ),
    "bitbucket.list_projects": _Operation(
        "bitbucket", (), {"limit": 25}, _bitbucket_projects
    ),
    "bitbucket.get_pull_request": _Operation(
        "bitbucket", ("project", "slug", "pr_id"), {}, _bitbucket_pull_request
    ),
}

# A bare method name is accepted only when exactly one product defines it.
_UNIQUE_ALIASES = {
    "get_issue": "jira.get_issue",
    "get_page": "confluence.get_page",
    "list_spaces": "confluence.list_spaces",
    "get_repository": "bitbucket.get_repository",
    "get_pull_request": "bitbucket.get_pull_request",
}
_AMBIGUOUS_NAMES = frozenset({"search", "list_projects"})


def _product_of(operation: object) -> str | None:
    if isinstance(operation, str):
        product, separator, _ = operation.partition(".")
        if separator and product in {"jira", "confluence", "bitbucket"}:
            return product
    return None


def _error(
    product: str | None,
    *,
    status: int | None,
    code: str,
    message: str,
    path: str | None,
    body: str | None = None,
    body_json: object = None,
    body_truncated: bool = False,
) -> dict[str, object]:
    return {
        "ok": False,
        "product": product,
        "error": {
            "status": status,
            "code": code,
            "message": message,
            "path": path,
            "body": body,
            "body_json": body_json,
            "body_truncated": body_truncated,
        },
    }


def _validation(product: str | None, message: str) -> dict[str, object]:
    return _error(
        product,
        status=None,
        code="validation_error",
        message=message,
        path=None,
    )


def _redact_text(value: str, token: str) -> str:
    return value.replace(token, _REDACT) if token else value


def _scrub(value: object, token: str) -> object:
    """Replace the bearer token in every parsed JSON scalar and key.

    The traversal is iterative so a legally deep upstream document cannot turn
    the error path into a recursion failure.
    """
    if not token:
        return value
    if isinstance(value, str):
        return value.replace(token, _REDACT)
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, item in list(node.items()):
                if isinstance(item, str):
                    item = item.replace(token, _REDACT)
                else:
                    stack.append(item)
                if isinstance(key, str) and token in key:
                    del node[key]
                    key = key.replace(token, _REDACT)
                node[key] = item
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, str):
                    node[index] = item.replace(token, _REDACT)
                else:
                    stack.append(item)
    return value


def _request_error(
    product: str, exc: SdkRequestError, token: str
) -> dict[str, object]:
    body: str | None = None
    body_json: object = None
    truncated = False
    if exc.body is not None:
        redacted = _redact_text(exc.body, token)
        if len(redacted) > _BODY_LIMIT:
            redacted = redacted[:_BODY_LIMIT]
            truncated = True
        body = redacted
        try:
            parsed = json.loads(redacted)
        except (ValueError, RecursionError):
            parsed = None
        else:
            body_json = _scrub(parsed, token)
    return _error(
        product,
        status=exc.status,
        code=exc.code,
        message=_redact_text(exc.message, token),
        path=exc.path,
        body=body,
        body_json=body_json,
        body_truncated=truncated,
    )


class _Namespace:
    """Base for the three product namespaces; it holds only the facade."""

    __slots__ = ("_facade",)

    def __init__(self, facade: "AtlaWire") -> None:
        self._facade = facade


class _Jira(_Namespace):
    __slots__ = ()

    def get_issue(self, key: str) -> dict[str, object]:
        """Return one Jira issue."""
        return self._facade.call("jira.get_issue", key=key)

    def search(self, jql: str, limit: int = 50) -> dict[str, object]:
        """Return one page of Jira issues matching ``jql``."""
        return self._facade.call("jira.search", jql=jql, limit=limit)

    def list_projects(self) -> dict[str, object]:
        """Return the Jira project list."""
        return self._facade.call("jira.list_projects")


class _Confluence(_Namespace):
    __slots__ = ()

    def get_page(self, content_id: str | int) -> dict[str, object]:
        """Return one Confluence page."""
        return self._facade.call("confluence.get_page", content_id=content_id)

    def search(self, cql: str, limit: int = 25) -> dict[str, object]:
        """Return one page of Confluence content matching ``cql``."""
        return self._facade.call("confluence.search", cql=cql, limit=limit)

    def list_spaces(self, limit: int = 25) -> dict[str, object]:
        """Return one page of Confluence spaces."""
        return self._facade.call("confluence.list_spaces", limit=limit)


class _Bitbucket(_Namespace):
    __slots__ = ()

    def get_repository(self, project: str, slug: str) -> dict[str, object]:
        """Return one Bitbucket repository."""
        return self._facade.call(
            "bitbucket.get_repository", project=project, slug=slug
        )

    def list_projects(self, limit: int = 25) -> dict[str, object]:
        """Return one page of Bitbucket projects."""
        return self._facade.call("bitbucket.list_projects", limit=limit)

    def get_pull_request(
        self, project: str, slug: str, pr_id: str | int
    ) -> dict[str, object]:
        """Return one Bitbucket pull request."""
        return self._facade.call(
            "bitbucket.get_pull_request", project=project, slug=slug, pr_id=pr_id
        )


class AtlaWire:
    """Read-only entry point for the supported Jira, Confluence, and Bitbucket reads.

    Product namespaces are created on first access. Each call resolves only that
    product's saved BBK credentials, so a missing entry for one product never
    affects the other two.
    """

    __slots__ = ("_allow_http_loopback", "_namespaces")

    def __init__(self, allow_http_loopback: bool = False) -> None:
        self._allow_http_loopback = bool(allow_http_loopback)
        self._namespaces: dict[str, _Namespace] = {}

    def _namespace(self, product: str) -> _Namespace:
        namespace = self._namespaces.get(product)
        if namespace is None:
            namespace = {
                "jira": _Jira,
                "confluence": _Confluence,
                "bitbucket": _Bitbucket,
            }[product](self)
            self._namespaces[product] = namespace
        return namespace

    @property
    def jira(self) -> _Jira:
        return cast(_Jira, self._namespace("jira"))

    @property
    def confluence(self) -> _Confluence:
        return cast(_Confluence, self._namespace("confluence"))

    @property
    def bitbucket(self) -> _Bitbucket:
        return cast(_Bitbucket, self._namespace("bitbucket"))

    def call(self, operation: str, **params: object) -> dict[str, object]:
        """Run exactly one named operation with its declared parameters.

        ``operation`` is ``"<product>.<method>"`` for one of the nine listed
        namespaces' methods, or a bare method name that only one product
        defines. Ambiguous bare names must be qualified. Unknown names, missing
        or extra parameters, and unsafe identifiers return a
        ``validation_error`` envelope without resolving credentials or sending
        a request.
        """
        name = operation
        if isinstance(name, str) and name in _UNIQUE_ALIASES:
            name = _UNIQUE_ALIASES[name]
        if isinstance(name, str) and name in _AMBIGUOUS_NAMES:
            return _validation(
                None, f"Ambiguous operation; use {name} with a product prefix."
            )
        spec = _OPERATIONS.get(name) if isinstance(name, str) else None
        product = _product_of(name)
        if spec is None:
            return _validation(product, "Unknown operation.")
        if not set(spec.required) <= set(params) or not set(params) <= spec.declared:
            expected = ", ".join(spec.required)
            optional = ", ".join(sorted(spec.defaults))
            message = f"Expected these parameters: {expected or 'none'}."
            if optional:
                message += f" Optional: {optional}."
            return _validation(spec.product, message)
        try:
            path, query = spec.build({**spec.defaults, **params})
        except _Validation as exc:
            return _validation(spec.product, str(exc))
        return self._send(spec.product, path, query)

    def _send(
        self, product: str, path: str, query: Mapping[str, str | int]
    ) -> dict[str, object]:
        try:
            saved = resolve_saved_credentials(
                product,
                supplied_base_url=None,
                allow_http_loopback=self._allow_http_loopback,
            )
        except AtlaWireError as exc:
            return _error(
                product,
                status=None,
                code="credentials_error",
                message=str(exc),
                path=None,
            )
        try:
            data = get_json(
                product,
                saved.base_url,
                path,
                token=saved.token,
                params=query or None,
                allow_http_loopback=self._allow_http_loopback,
            )
        except SdkRequestError as exc:
            return _request_error(product, exc, saved.token)
        except AtlaWireError as exc:
            return _error(
                product,
                status=None,
                code="request_error",
                message=_redact_text(str(exc), saved.token),
                path=path,
            )
        return {"ok": True, "product": product, "data": data}

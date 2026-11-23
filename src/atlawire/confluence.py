"""Read operations for self-hosted Confluence.

These adapters issue one fixed GET per call, return the server JSON object
unchanged, and never follow returned links. They follow the Confluence 6.6.0
documentation; the live version and exact response shapes are not verified.
"""

import json
import re
from collections.abc import Callable, Mapping
from hashlib import sha256
from typing import TypedDict
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)

_PAGE_EXPAND = "body.storage,version,space,ancestors"
_HISTORY_PATH = "/rest/api/content/{id}/history"
_PAGE_VERSION_EXPAND = "body.storage,version"
_PAGE_VERSION_STATUS = "historical"
_CHILD_PATH = "/rest/api/content/{id}/child/page"
_CHILD_EXPAND = "version"
_ATTACHMENT_PATH = "/rest/api/content/{id}/child/attachment"
_COMMENT_PATH = "/rest/api/content/{id}/child/comment"
_COMMENT_EXPAND = "body.storage"
_COMMENT_DEPTH_ALL = "all"
_LABEL_PATH = "/rest/api/content/{id}/label"
_SEARCH_PATH = "/rest/api/search"
_SPACE_PATH = "/rest/api/space"
_SPACE_CONTENT_PATH = "/rest/api/space/{key}/content"
_SPACE_CONTENT_TYPE_PATH = "/rest/api/space/{key}/content/{type}"
_CONTENT_EXPAND = "version"
# One explicit page; the server may cap the limit. Defaults follow Confluence
# 6.6.0 documentation.
PAGE_START_MIN = 0
PAGE_LIMIT_MIN = 1
PAGE_LIMIT_MAX = 1000
ATTACHMENT_LIMIT_DEFAULT = 50
COMMENT_LIMIT_DEFAULT = 25
LABEL_LIMIT_DEFAULT = 200
CQL_LIMIT_MIN = 0
CQL_LIMIT_MAX = 1000
CQL_LIMIT_DEFAULT = 25
SPACE_LIMIT_MIN = 0
SPACE_LIMIT_MAX = 1000
SPACE_LIMIT_DEFAULT = 100
CHILD_LIMIT_MIN = 0
CHILD_LIMIT_MAX = 1000
CHILD_LIMIT_DEFAULT = 100
_PAGE_ID = re.compile(r"[1-9][0-9]*")
# A Confluence space key is one path segment; reject dots-only and separators.
_SPACE_KEY = re.compile(r"[A-Za-z0-9_~][A-Za-z0-9_.~\-]*")
# The registry documents the content type as one path segment as well, but the
# public argument additionally rejects dots-only values that could traverse it.
_CONTENT_TYPE = re.compile(r"[A-Za-z0-9_~][A-Za-z0-9_.~\-]*")
_RAW_ASCII_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_UNSAFE_WEBUI = re.compile(
    r"[\x00-\x20\x7f-\x9f\\\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069]"
)
_INVALID_ID = (
    "Expected a numeric Confluence page ID or a page link "
    "with one pageId query parameter."
)
_INVALID_PAGE = (
    "Expected a Confluence page with a matching id, type, title, and storage body."
)
_INVALID_PAGE_VERSION = "Expected the requested Confluence page version."
_INVALID_VERSION_ARGUMENT = "The page version must be a positive integer."
_INVALID_RESULT = "Invalid Confluence content metadata in search results."
_INVALID_SPACE = "Invalid Confluence space metadata in spaces results."
_INVALID_SPACE_KEY = "Expected a Confluence space key."
_INVALID_CONTENT_TYPE = "Expected a Confluence content type."
_INVALID_SPACE_CONTENT = "Invalid Confluence space content metadata."
_INVALID_CHILD = "Invalid Confluence child page metadata in children results."


class ContentRow(TypedDict):
    """A short content row shared by the CQL text and JSON output."""

    id: str | int | None
    space: str | None
    type: str | None
    title: str | None
    url: str | None


class SpaceRow(TypedDict):
    """A short space row shared by the spaces text and JSON output."""

    key: str | None
    name: str | None
    type: str | None


class SpaceDetail(TypedDict):
    """A single space projected for the text and JSON output."""

    key: str | None
    name: str | None
    type: str | None
    status: str | None
    url: str | None


class ContentSummary(TypedDict):
    """One content row projected from the space content listing."""

    id: str | int | None
    title: str | None
    type: str | None
    version: int | None
    url: str | None


class ContentRows(TypedDict):
    """A bounded content listing plus the server's own truncation signal."""

    rows: list[ContentSummary]
    truncated: bool


class ChildRow(TypedDict):
    """A short direct-child row shared by the children text and JSON output."""

    id: str | int | None
    title: str | None
    version: int | None


def page_id(value: str | int) -> str:
    """Return the canonical decimal page ID from a numeric ID or a page link.

    A link is only a source of the ID: its host, path, and other query
    parameters are ignored so a pasted URL never redirects the request.
    """
    if isinstance(value, bool):
        raise AtlaWireError(_INVALID_ID)
    if isinstance(value, int):
        if value <= 0:
            raise AtlaWireError(_INVALID_ID)
        return str(value)
    # urlsplit silently drops TAB/LF/CR and leading C0/space, so reject raw
    # ASCII whitespace and controls before parsing instead of normalizing them.
    if _RAW_ASCII_CONTROL.search(value):
        raise AtlaWireError(_INVALID_ID)
    if _PAGE_ID.fullmatch(value):
        return value
    try:
        url = urlsplit(value)
        host = url.hostname
    except ValueError:
        raise AtlaWireError(_INVALID_ID) from None
    if url.scheme not in {"http", "https"} or not host:
        raise AtlaWireError(_INVALID_ID)
    # Keep blank values so a repeated or empty pageId cannot silently pass.
    ids = parse_qs(url.query, keep_blank_values=True).get("pageId", [])
    if len(ids) != 1 or not _PAGE_ID.fullmatch(ids[0]):
        raise AtlaWireError(_INVALID_ID)
    return ids[0]


def get_page(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the Confluence page JSON from the configured instance.

    The server payload is returned unchanged; only its identity, type, title,
    and ``body.storage.value`` are validated. The configured base URL is always
    the request destination, even when a page link is supplied.
    """
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        page = get_json_object(
            session,
            f"{base}/rest/api/content/{requested_id}",
            params={"expand": _PAGE_EXPAND},
        )
    return _validated_page(page, requested_id)


def get_page_web_url(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> str:
    """Return a browser URL for a Confluence page.

    Reads the page through [get_page][atlawire.confluence.get_page] and appends
    a validated context-relative ``_links.webui`` path to the configured base
    URL. Missing, malformed, absolute, or otherwise unsafe links are ignored in
    favour of ``/pages/viewpage.action?pageId=<id>``. The supplied token is
    never included, and returned links are never followed.
    """
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    page = get_page(
        base,
        requested_id,
        token=token,
        allow_http_loopback=allow_http_loopback,
    )
    path = _safe_webui_path(page)
    if path is None:
        path = f"/pages/viewpage.action?pageId={requested_id}"
    return f"{base}{path}"


def _safe_webui_path(page: dict[str, object]) -> str | None:
    """Return a safe context-relative web UI path, or ``None``."""
    links = page.get("_links")
    if links is None:
        return None
    if not isinstance(links, dict):
        return None
    webui = links.get("webui")
    if not isinstance(webui, str):
        return None
    return _validated_webui_path(webui)


def _validated_webui_path(value: str) -> str | None:
    """Reject absolute, control-bearing, backslash, or traversal paths."""
    if (
        not value.startswith("/")
        or value.startswith("//")
        or not _valid_utf8(value)
        or _UNSAFE_WEBUI.search(value)
    ):
        return None
    try:
        split = urlsplit(value)
    except ValueError:
        return None
    if split.scheme or split.netloc:
        return None
    candidate = value
    # Follows no link, but percent-decoded ``..`` and separators could still
    # change the meaning of a path a browser or proxy later normalizes.
    for _ in range(4):
        if _UNSAFE_WEBUI.search(candidate):
            return None
        decoded = unquote(candidate)
        if _UNSAFE_WEBUI.search(decoded):
            return None
        if not decoded.startswith("/") or decoded.startswith("//"):
            return None
        path = decoded.split("#", 1)[0].split("?", 1)[0]
        if any(
            segment == "." or segment.startswith("..")
            for segment in path.split("/")
        ):
            return None
        if decoded == candidate:
            return value
        candidate = decoded
    return None


def _validated_page(page: dict[str, object], requested_id: str) -> dict[str, object]:
    returned_id = page.get("id")
    if isinstance(returned_id, bool):
        raise AtlaWireError(_INVALID_PAGE)
    if isinstance(returned_id, int):
        if returned_id <= 0 or str(returned_id) != requested_id:
            raise AtlaWireError(_INVALID_PAGE)
    elif not isinstance(returned_id, str) or returned_id != requested_id:
        raise AtlaWireError(_INVALID_PAGE)
    if page.get("type") != "page" or not isinstance(page.get("title"), str):
        raise AtlaWireError(_INVALID_PAGE)
    body = page.get("body")
    if not isinstance(body, dict):
        raise AtlaWireError(_INVALID_PAGE)
    storage = body.get("storage")
    if not isinstance(storage, dict) or not isinstance(storage.get("value"), str):
        raise AtlaWireError(_INVALID_PAGE)
    return page


def get_page_history(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the raw history object for a Confluence page.

    Makes one fixed GET to ``/rest/api/content/{id}/history`` with no query
    parameters. The object is returned unchanged and links are never followed.
    This is not a complete version list: Confluence 6.6.0 documents only a
    history representation, not a full field set or all versions.
    """
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        return get_json_object(
            session,
            f"{base}{_HISTORY_PATH.format(id=requested_id)}",
            params={},
        )


def get_page_version(
    base_url: str,
    page_id_or_url: str | int,
    version: int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one explicit historical page version.

    Sends one GET to ``/rest/api/content/{id}`` with ``status=historical``,
    ``version=N``, and ``expand=body.storage,version``. Confluence 6.6.0
    documents these parameters individually but not this exact combination;
    the historical status is the value Atlassian's history payload uses for
    version content links. The raw page object is returned unchanged after its
    id, page shape, and ``version.number`` are validated. Links are never
    followed, and live version support is unverified.
    """
    _validate_requested_version(version)
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        page = get_json_object(
            session,
            f"{base}/rest/api/content/{requested_id}",
            params={
                "status": _PAGE_VERSION_STATUS,
                "version": version,
                "expand": _PAGE_VERSION_EXPAND,
            },
        )
    return _validated_page_version(page, requested_id, version)


def _validated_page_version(
    page: dict[str, object], requested_id: str, requested_version: int
) -> dict[str, object]:
    """Validate the documented page identity and requested version number."""
    _validated_page(page, requested_id)
    page_version = page.get("version")
    if not isinstance(page_version, dict):
        raise AtlaWireError(_INVALID_PAGE_VERSION)
    number = page_version.get("number")
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or number != requested_version
    ):
        raise AtlaWireError(_INVALID_PAGE_VERSION)
    return page


def _validate_requested_version(version: int) -> None:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise AtlaWireError(_INVALID_VERSION_ARGUMENT)


def search_cql(
    base_url: str,
    query: str,
    *,
    token: str,
    limit: int = CQL_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[ContentRow]:
    """Return up to ``limit`` short content rows in Confluence search order.

    The configured base URL is always the request destination; a continuation
    link only supplies the next offset. Pagination stops when the limit is
    reached or an empty page proves exhaustion, and any error discards rows
    already read instead of returning a partial result. A zero limit returns
    no rows and creates no session, matching the legacy behavior.
    """
    if not query.strip():
        raise AtlaWireError("Expected a non-empty CQL query.")
    _validate_limit(limit, CQL_LIMIT_MIN, CQL_LIMIT_MAX)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if limit == 0:
        return []
    with bearer_session(token) as session:
        return _read_rows(
            session,
            f"{base}{_SEARCH_PATH}",
            {"cql": query},
            limit,
            label="search",
            empty_hint="narrow the query or retry.",
            project=_content_row,
            identity=_content_identity,
        )


def list_spaces(
    base_url: str,
    *,
    token: str,
    limit: int = SPACE_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[SpaceRow]:
    """Return up to ``limit`` spaces in Confluence order.

    Only ``start`` and ``limit`` are sent to the configured instance's space
    endpoint. Pagination stops when the limit is reached or an empty page proves
    exhaustion, and any error discards rows already read instead of returning a
    partial result. A zero limit returns no rows and creates no session.
    """
    _validate_limit(limit, SPACE_LIMIT_MIN, SPACE_LIMIT_MAX)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if limit == 0:
        return []
    with bearer_session(token) as session:
        return _read_rows(
            session,
            f"{base}{_SPACE_PATH}",
            {},
            limit,
            label="space",
            empty_hint="retry the request.",
            project=_space_row,
            identity=_space_identity,
        )


def get_space(
    base_url: str,
    space_key: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> SpaceDetail:
    """Return one space projected to its five stable fields.

    Only the configured instance's space endpoint is read. A response whose
    ``key`` differs from the requested key is rejected instead of being
    returned as that space, and unknown server fields are dropped. ``status``
    and ``url`` stay optional because the server returns them only when it has
    them.
    """
    requested_key = _validated_space_key(space_key)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        value = get_json_object(
            session,
            f"{base}{_SPACE_PATH}/{requested_key}",
            params={},
        )
    return _space_detail(value, requested_key)


def list_space_content(
    base_url: str,
    space_key: str,
    *,
    token: str,
    type: str | None = None,
    limit: int = SPACE_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> ContentRows:
    """Return up to ``limit`` space content rows in a deterministic order.

    Without ``type`` the server's per-type map is read and the rows are ordered
    pages, blog posts, then other types alphabetically; with ``type`` only that
    endpoint is read. A full budget is never an error: ``truncated`` reports
    whether the server still had rows. Only the configured instance is read.
    A zero limit returns an empty listing and creates no session.
    """
    requested_key = _validated_space_key(space_key)
    requested_type = None if type is None else _validated_content_type(type)
    _validate_limit(limit, SPACE_LIMIT_MIN, SPACE_LIMIT_MAX)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if limit == 0:
        return ContentRows(rows=[], truncated=False)
    with bearer_session(token) as session:
        if requested_type is None:
            return _read_all_space_content(session, base, requested_key, limit)
        return _read_typed_space_content(
            session, base, requested_key, requested_type, limit
        )


def list_children(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    limit: int = CHILD_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[ChildRow]:
    """Return up to ``limit`` direct child pages in Confluence order.

    Only the configured instance is read; a page link supplies nothing but the
    parent ID. The request asks for the fixed ``version`` expansion plus the
    ``start`` and ``limit`` offsets. Pagination stops when the limit is reached
    or an empty page proves exhaustion, and any error discards rows already read
    instead of returning a partial result. A zero limit returns no rows and
    creates no session, but the base URL and parent are still validated.
    """
    _validate_limit(limit, CHILD_LIMIT_MIN, CHILD_LIMIT_MAX)
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if limit == 0:
        return []
    with bearer_session(token) as session:
        return _read_rows(
            session,
            f"{base}{_CHILD_PATH.format(id=requested_id)}",
            {"expand": _CHILD_EXPAND},
            limit,
            label="child page",
            empty_hint="retry the request.",
            project=_child_row,
            identity=_child_identity,
        )


def get_page_attachments(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    start: int = PAGE_START_MIN,
    limit: int = ATTACHMENT_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one bounded page of attachment metadata.

    Sends only ``start`` and ``limit`` to the configured instance. The raw JSON
    object, including pagination metadata and unknown fields, is returned
    unchanged; continuation links are never followed. The 6.6.0 docs show a flat
    object, but fields are not guaranteed across Confluence versions.
    """
    return _read_content_page(
        base_url,
        page_id_or_url,
        token=token,
        path=_ATTACHMENT_PATH,
        fixed_params={},
        start=start,
        limit=limit,
        allow_http_loopback=allow_http_loopback,
    )


def get_page_comments(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    start: int = PAGE_START_MIN,
    limit: int = COMMENT_LIMIT_DEFAULT,
    include_replies: bool = True,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one bounded page of comment metadata.

    Sends ``start``, ``limit``, ``expand=body.storage``, and by default
    ``depth=all`` so replies and storage bodies are requested. Set
    ``include_replies=False`` to omit ``depth`` and use the documented root-only
    default. The raw JSON object is returned unchanged and links are never
    followed; one page may still be incomplete. The 6.6.0 docs show a
    content-type-keyed map, but no response shape is assumed.
    """
    _validate_include_replies(include_replies)
    fixed_params = {"expand": _COMMENT_EXPAND}
    if include_replies:
        fixed_params["depth"] = _COMMENT_DEPTH_ALL
    return _read_content_page(
        base_url,
        page_id_or_url,
        token=token,
        path=_COMMENT_PATH,
        fixed_params=fixed_params,
        start=start,
        limit=limit,
        allow_http_loopback=allow_http_loopback,
    )


def get_page_labels(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    start: int = PAGE_START_MIN,
    limit: int = LABEL_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one bounded page of labels.

    Sends only ``start`` and ``limit`` to the configured instance. The raw JSON
    object is returned unchanged and links are never followed. The 6.6.0 docs
    publish no response schema, so no field or pagination shape is assumed.
    """
    return _read_content_page(
        base_url,
        page_id_or_url,
        token=token,
        path=_LABEL_PATH,
        fixed_params={},
        start=start,
        limit=limit,
        allow_http_loopback=allow_http_loopback,
    )


def _read_content_page(
    base_url: str,
    page_id_or_url: str | int,
    *,
    token: str,
    path: str,
    fixed_params: Mapping[str, str],
    start: int,
    limit: int,
    allow_http_loopback: bool,
) -> dict[str, object]:
    """Read exactly one bounded page from one fixed content subresource."""
    _validate_start(start)
    _validate_limit(limit, PAGE_LIMIT_MIN, PAGE_LIMIT_MAX)
    requested_id = page_id(page_id_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        return get_json_object(
            session,
            f"{base}{path.format(id=requested_id)}",
            params={**fixed_params, "start": start, "limit": limit},
        )


def _validate_include_replies(include_replies: bool) -> None:
    if not isinstance(include_replies, bool):
        raise AtlaWireError("The include_replies option must be a boolean.")


def _validate_start(start: int) -> None:
    if not isinstance(start, int) or isinstance(start, bool) or start < PAGE_START_MIN:
        raise AtlaWireError(
            f"The pagination start must be an integer of at least {PAGE_START_MIN}."
        )


def _validate_limit(limit: int, minimum: int, maximum: int) -> None:
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not minimum <= limit <= maximum
    ):
        raise AtlaWireError(f"The row limit must be between {minimum} and {maximum}.")


def _read_rows[RowT](
    session: requests.Session,
    url: str,
    params: Mapping[str, str],
    limit: int,
    *,
    label: str,
    empty_hint: str,
    project: Callable[[dict[str, object]], RowT],
    identity: Callable[[dict[str, object]], str | None],
) -> list[RowT]:
    rows: list[RowT] = []
    seen_ids: set[str] = set()
    seen_fallback_pages: set[bytes] = set()
    known_total: int | None = None
    while len(rows) < limit:
        requested = limit - len(rows)
        page = get_json_object(
            session,
            url,
            params={**params, "start": len(rows), "limit": requested},
        )
        results, total = _page(page, len(rows), requested, label)
        if total is not None:
            # The endpoint may omit totalSize on a later page, but an earlier
            # usable total is retained and a different value is a contradiction.
            if known_total is not None and total != known_total:
                raise AtlaWireError(
                    f"Confluence {label} totalSize changed between pages."
                )
            known_total = total
        if known_total is not None and len(rows) + len(results) > known_total:
            raise AtlaWireError(f"Inconsistent Confluence {label} pagination metadata.")
        if not results:
            if known_total is not None and known_total > len(rows):
                raise AtlaWireError(
                    f"Confluence {label} returned an empty page before all "
                    f"matches; {empty_hint}"
                )
            return rows
        _check_repeated_rows(results, identity, seen_ids, seen_fallback_pages, label)
        # A server cap may shorten a page; the next offset uses the actual rows.
        rows.extend(project(result) for result in results)
    return rows


def _check_repeated_rows(
    results: list[dict[str, object]],
    identity: Callable[[dict[str, object]], str | None],
    seen_ids: set[str],
    seen_fallback_pages: set[bytes],
    label: str,
) -> None:
    has_anonymous = False
    for result in results:
        stable = identity(result)
        if stable is None:
            has_anonymous = True
        elif stable in seen_ids:
            raise AtlaWireError(f"Confluence {label} returned a repeated result.")
        else:
            seen_ids.add(stable)
    if not has_anonymous:
        return
    # Matching visible fields alone do not identify an anonymous row; keep the
    # whole-page fallback without retaining copies of earlier raw page bodies.
    try:
        canonical = json.dumps(
            results, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
    except RecursionError:
        raise AtlaWireError(
            f"Confluence {label} results are nested too deeply."
        ) from None
    fingerprint = sha256(canonical.encode("ascii")).digest()
    if fingerprint in seen_fallback_pages:
        raise AtlaWireError(f"Confluence {label} returned a repeated page.")
    seen_fallback_pages.add(fingerprint)


def _stable_id(value: object) -> str | None:
    """Return a normalized nonempty string or integer ID, else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    return None


def _content_identity(result: dict[str, object]) -> str | None:
    """Identify one search result by its nonempty nested ``content.id``.

    The nested content ID is the only evidence used here; a result without it
    falls back to raw equality so unrelated entity types never share an ID
    namespace.
    """
    content = result.get("content")
    if not isinstance(content, dict):
        return None
    stable_id = _stable_id(content.get("id"))
    if stable_id is None:
        return None
    return "content-id:" + stable_id


def _space_identity(result: dict[str, object]) -> str | None:
    """Identify one space by its nonempty top-level ``key``, else raw equality."""
    key = result.get("key")
    if not isinstance(key, str) or not key:
        return None
    return "space-key:" + key


def _child_identity(result: dict[str, object]) -> str | None:
    """Identify one child page by its nonempty top-level ``id``, else raw equality."""
    stable_id = _stable_id(result.get("id"))
    if stable_id is None:
        return None
    return "child-id:" + stable_id


def _page(
    page: dict[str, object], offset: int, requested: int, label: str
) -> tuple[list[dict[str, object]], int | None]:
    if "start" in page:
        reported_start = page["start"]
        if (
            not isinstance(reported_start, int)
            or isinstance(reported_start, bool)
            or reported_start != offset
        ):
            raise AtlaWireError(
                f"Expected Confluence {label} start to match the requested offset."
            )
    results = page.get("results")
    if not isinstance(results, list) or any(
        not isinstance(result, dict) for result in results
    ):
        raise AtlaWireError(f"Expected a Confluence {label} results array of objects.")
    if len(results) > requested:
        raise AtlaWireError(f"Confluence {label} returned more results than requested.")
    if "size" in page:
        reported_size = page["size"]
        if (
            not isinstance(reported_size, int)
            or isinstance(reported_size, bool)
            or reported_size != len(results)
        ):
            raise AtlaWireError(
                f"Expected Confluence {label} size to match the returned results."
            )
    total = page.get("totalSize")
    if total is not None and (
        not isinstance(total, int) or isinstance(total, bool) or total < 0
    ):
        raise AtlaWireError(f"Invalid Confluence {label} totalSize.")
    if total is not None and total < offset + len(results):
        raise AtlaWireError(f"Inconsistent Confluence {label} pagination metadata.")
    links = page.get("_links", {})
    if not isinstance(links, dict):
        raise AtlaWireError(f"Invalid Confluence {label} links.")
    # Validate a continuation only when another page would be requested, so a
    # link left over at the exact limit stays untouched.
    if len(results) < requested and "next" in links:
        _check_next(links["next"], len(results), offset, label)
    return results, total


def _check_next(link: object, count: int, offset: int, label: str) -> None:
    if not isinstance(link, str):
        raise AtlaWireError(f"Invalid Confluence {label} continuation link.")
    # urlsplit removes raw C0/space controls, so reject them before parsing
    # instead of letting a padded hint pass as a canonical offset.
    if _RAW_ASCII_CONTROL.search(link):
        raise AtlaWireError(f"Invalid Confluence {label} continuation link.")
    if count == 0:
        raise AtlaWireError(f"Confluence {label} cannot continue after an empty page.")
    try:
        offsets = parse_qs(urlsplit(link).query, keep_blank_values=True).get(
            "start", []
        )
    except ValueError:
        raise AtlaWireError(f"Invalid Confluence {label} continuation link.") from None
    if offsets != [str(offset + count)]:
        raise AtlaWireError(f"Invalid Confluence {label} continuation offset.")


def _page_has_next(page: dict[str, object]) -> bool:
    """Return whether the server reported a next page through ``_links.next``."""
    links = page.get("_links")
    return isinstance(links, dict) and "next" in links


def _page_has_more(page: dict[str, object], total: int | None, count: int) -> bool:
    """Return whether rows remain after the ``count`` already collected."""
    if total is not None:
        return total > count
    return _page_has_next(page)


def _valid_utf8(value: str) -> bool:
    """Return whether output text can be encoded as strict UTF-8."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validated_space_key(value: str) -> str:
    """Return one path-safe space key, or raise before any request is made."""
    if not isinstance(value, str) or _SPACE_KEY.fullmatch(value) is None:
        raise AtlaWireError(_INVALID_SPACE_KEY)
    return value


def _space_row(value: object) -> SpaceRow:
    if not isinstance(value, dict):
        raise AtlaWireError(_INVALID_SPACE)
    return SpaceRow(
        key=_space_text(value, "key"),
        name=_space_text(value, "name"),
        type=_space_text(value, "type"),
    )


def _space_text(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not _valid_utf8(value):
        raise AtlaWireError(_INVALID_SPACE)
    return value


def _space_detail(value: dict[str, object], requested_key: str) -> SpaceDetail:
    """Project one space, rejecting a response for a different space key."""
    key = _space_text(value, "key")
    if key is None or key != requested_key:
        raise AtlaWireError(_INVALID_SPACE)
    return SpaceDetail(
        key=key,
        name=_space_text(value, "name"),
        type=_space_text(value, "type"),
        status=_space_text(value, "status"),
        url=_webui(value),
    )


def _validated_content_type(value: str) -> str:
    """Return one path-safe content type, or raise before any request is made."""
    if not isinstance(value, str) or _CONTENT_TYPE.fullmatch(value) is None:
        raise AtlaWireError(_INVALID_CONTENT_TYPE)
    return value


def _space_content_order(content_type: str) -> int:
    """Order space content buckets deterministically: pages, blog posts, rest."""
    if content_type == "page":
        return 0
    if content_type == "blogpost":
        return 1
    return 2


def _summary_id(item: dict[str, object]) -> str | int | None:
    """Read the optional content id of one space content row."""
    value = item.get("id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise AtlaWireError(_INVALID_RESULT)
    if isinstance(value, str) and not _valid_utf8(value):
        raise AtlaWireError(_INVALID_RESULT)
    return value


def _summary_version(item: dict[str, object]) -> int | None:
    """Read the optional version number of one space content row."""
    version = item.get("version")
    if version is None:
        return None
    if not isinstance(version, dict):
        raise AtlaWireError(_INVALID_RESULT)
    number = version.get("number")
    if number is None:
        return None
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        raise AtlaWireError(_INVALID_RESULT)
    return number


def _content_summary(value: object) -> ContentSummary:
    """Project one space content row, dropping unknown server fields."""
    if not isinstance(value, dict):
        raise AtlaWireError(_INVALID_RESULT)
    return ContentSummary(
        id=_summary_id(value),
        title=_string(value, "title"),
        type=_string(value, "type"),
        version=_summary_version(value),
        url=_webui(value),
    )


def _content_summary_identity(result: dict[str, object]) -> str | None:
    """Identify one content row by its nonempty id, else fall back to raw equality."""
    stable_id = _stable_id(result.get("id"))
    if stable_id is None:
        return None
    return "content-id:" + stable_id


def _bucket_has_rows(
    bucket: tuple[str, list[dict[str, object]], bool],
) -> bool:
    """Return whether a bucket still holds unread rows or a next page."""
    return bool(bucket[1]) or bucket[2]


def _space_content_buckets(
    page: dict[str, object], requested: int
) -> list[tuple[str, list[dict[str, object]], bool]]:
    """Split the per-type space content map into validated ordered buckets."""
    buckets: list[tuple[str, list[dict[str, object]], bool]] = []
    for name, value in page.items():
        if name.startswith("_"):
            continue
        if _CONTENT_TYPE.fullmatch(name) is None or not isinstance(value, dict):
            raise AtlaWireError(_INVALID_SPACE_CONTENT)
        results, total = _page(value, 0, requested, "space content")
        links = value.get("_links")
        if not isinstance(links, dict):
            raise AtlaWireError(_INVALID_SPACE_CONTENT)
        buckets.append((name, results, _page_has_more(value, total, len(results))))
    buckets.sort(key=lambda bucket: (_space_content_order(bucket[0]), bucket[0]))
    return buckets


def _append_content_rows(
    results: list[dict[str, object]],
    rows: list[ContentSummary],
    seen_ids: set[str],
    seen_fallback_pages: set[bytes],
) -> None:
    """Validate one page of content rows for repeats, then append its projection."""
    _check_repeated_rows(
        results,
        _content_summary_identity,
        seen_ids,
        seen_fallback_pages,
        "space content",
    )
    rows.extend(_content_summary(result) for result in results)


def _read_typed_space_content(
    session: requests.Session,
    base: str,
    space_key: str,
    content_type: str,
    limit: int,
) -> ContentRows:
    """Read one content type by explicit offset and report truncation."""
    rows: list[ContentSummary] = []
    seen_ids: set[str] = set()
    seen_fallback_pages: set[bytes] = set()
    offset = 0
    url = f"{base}{_SPACE_CONTENT_TYPE_PATH.format(key=space_key, type=content_type)}"
    while len(rows) < limit:
        requested = limit - len(rows)
        page = get_json_object(
            session,
            url,
            params={"expand": _CONTENT_EXPAND, "start": offset, "limit": requested},
        )
        results, total = _page(page, offset, requested, "space content")
        if not results:
            if total is not None and total > offset:
                raise AtlaWireError(
                    "Confluence space content returned an empty page before all matches."
                )
            return ContentRows(rows=rows, truncated=False)
        _append_content_rows(results, rows, seen_ids, seen_fallback_pages)
        offset += len(results)
        if len(rows) >= limit:
            return ContentRows(rows=rows, truncated=_page_has_more(page, total, offset))
        if not _page_has_next(page):
            return ContentRows(rows=rows, truncated=_page_has_more(page, total, offset))
    return ContentRows(rows=rows, truncated=False)


def _read_all_space_content(
    session: requests.Session, base: str, space_key: str, limit: int
) -> ContentRows:
    """Read the per-type space content map and fill up to ``limit`` rows."""
    page = get_json_object(
        session,
        f"{base}{_SPACE_CONTENT_PATH.format(key=space_key)}",
        params={"expand": _CONTENT_EXPAND, "start": 0, "limit": limit},
    )
    buckets = _space_content_buckets(page, limit)
    rows: list[ContentSummary] = []
    seen_ids: set[str] = set()
    seen_fallback_pages: set[bytes] = set()
    for index, (content_type, first, has_next) in enumerate(buckets):
        if len(rows) >= limit:
            return ContentRows(
                rows=rows,
                truncated=any(_bucket_has_rows(bucket) for bucket in buckets[index:]),
            )
        take = first[: limit - len(rows)]
        _append_content_rows(take, rows, seen_ids, seen_fallback_pages)
        if len(take) < len(first):
            return ContentRows(rows=rows, truncated=True)
        if len(rows) >= limit:
            return ContentRows(
                rows=rows,
                truncated=has_next
                or any(_bucket_has_rows(bucket) for bucket in buckets[index + 1 :]),
            )
        offset = len(first)
        while has_next:
            requested = limit - len(rows)
            if requested <= 0:
                return ContentRows(rows=rows, truncated=True)
            continuation = get_json_object(
                session,
                f"{base}{_SPACE_CONTENT_TYPE_PATH.format(key=space_key, type=content_type)}",
                params={"expand": _CONTENT_EXPAND, "start": offset, "limit": requested},
            )
            results, total = _page(continuation, offset, requested, "space content")
            if not results:
                if total is not None and total > offset:
                    raise AtlaWireError(
                        "Confluence space content returned an empty page before all matches."
                    )
                has_next = False
                break
            _append_content_rows(results, rows, seen_ids, seen_fallback_pages)
            offset += len(results)
            if len(rows) >= limit:
                return ContentRows(
                    rows=rows,
                    truncated=_page_has_more(continuation, total, offset),
                )
            has_next = _page_has_more(continuation, total, offset)
    return ContentRows(rows=rows, truncated=False)


def _child_row(value: object) -> ChildRow:
    if not isinstance(value, dict):
        raise AtlaWireError(_INVALID_CHILD)
    return ChildRow(
        id=_child_id(value),
        title=_child_text(value, "title"),
        version=_child_version(value),
    )


def _child_id(item: dict[str, object]) -> str | int | None:
    value = item.get("id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise AtlaWireError(_INVALID_CHILD)
    if isinstance(value, str) and not _valid_utf8(value):
        raise AtlaWireError(_INVALID_CHILD)
    return value


def _child_text(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not _valid_utf8(value):
        raise AtlaWireError(_INVALID_CHILD)
    return value


def _child_version(item: dict[str, object]) -> int | None:
    version = item.get("version")
    if version is None:
        return None
    if not isinstance(version, dict):
        raise AtlaWireError(_INVALID_CHILD)
    number = version.get("number")
    if number is None:
        return None
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        raise AtlaWireError(_INVALID_CHILD)
    return number


def _content_row(value: object) -> ContentRow:
    if not isinstance(value, dict):
        raise AtlaWireError(_INVALID_RESULT)
    content = value.get("content")
    if content is None:
        content = {}
    elif not isinstance(content, dict):
        raise AtlaWireError(_INVALID_RESULT)
    return ContentRow(
        id=_content_id(content, value),
        space=_space_key(content, value),
        type=_text_value(content, value, "type"),
        title=_text_value(content, value, "title"),
        url=_content_url(content, value),
    )


def _content_id(
    content: dict[str, object], item: dict[str, object]
) -> str | int | None:
    value = content.get("id")
    if value is None:
        value = item.get("id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise AtlaWireError(_INVALID_RESULT)
    if isinstance(value, str) and not _valid_utf8(value):
        raise AtlaWireError(_INVALID_RESULT)
    return value


def _text_value(
    content: dict[str, object], item: dict[str, object], key: str
) -> str | None:
    value = content.get(key)
    if value is None:
        return _string(item, key)
    if not isinstance(value, str) or not _valid_utf8(value):
        raise AtlaWireError(_INVALID_RESULT)
    return value


def _space_key(content: dict[str, object], item: dict[str, object]) -> str | None:
    for container in (content.get("space"), item.get("space")):
        if container is None:
            continue
        if not isinstance(container, dict):
            raise AtlaWireError(_INVALID_RESULT)
        key = container.get("key")
        if key is None:
            continue
        if not isinstance(key, str) or not _valid_utf8(key):
            raise AtlaWireError(_INVALID_RESULT)
        return key
    # The live server exposes the space key only through the nested
    # content._expandable.space; a flat search result carries its own
    # _expandable. Therefore read both sources, otherwise cql/find rows lose it.
    for expandable in (item.get("_expandable"), content.get("_expandable")):
        if expandable is None:
            continue
        if not isinstance(expandable, dict):
            raise AtlaWireError(_INVALID_RESULT)
        path = expandable.get("space")
        if path is None:
            continue
        if not isinstance(path, str) or not _valid_utf8(path):
            raise AtlaWireError(_INVALID_RESULT)
        return path.rsplit("/", 1)[-1] or None
    return None


def _content_url(content: dict[str, object], item: dict[str, object]) -> str | None:
    url = _webui(item)
    if url is None:
        url = _string(item, "url")
    if url is None:
        url = _webui(content)
    return url


def _webui(container: dict[str, object]) -> str | None:
    links = container.get("_links")
    if links is None:
        return None
    if not isinstance(links, dict):
        raise AtlaWireError(_INVALID_RESULT)
    return _string(links, "webui")


def _string(container: dict[str, object], key: str) -> str | None:
    value = container.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not _valid_utf8(value):
        raise AtlaWireError(_INVALID_RESULT)
    return value

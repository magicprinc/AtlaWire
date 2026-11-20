"""Read operations for self-hosted Confluence."""

import json
import re
from collections.abc import Callable, Mapping
from typing import TypedDict
from urllib.parse import parse_qs, urlsplit

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)

_PAGE_EXPAND = "body.storage,version,space,ancestors"
_CHILD_PATH = "/rest/api/content/{id}/child/page"
_CHILD_EXPAND = "version"
_SEARCH_PATH = "/rest/api/search"
_SPACE_PATH = "/rest/api/space"
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
_RAW_ASCII_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_INVALID_ID = (
    "Expected a numeric Confluence page ID or a page link "
    "with one pageId query parameter."
)
_INVALID_PAGE = (
    "Expected a Confluence page with a matching id, type, title, and storage body."
)
_INVALID_RESULT = "Invalid Confluence content metadata in search results."
_INVALID_SPACE = "Invalid Confluence space metadata in spaces results."
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
            identities=_content_identities,
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
            identities=_space_identities,
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
            identities=_child_identities,
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
    identities: Callable[[list[dict[str, object]]], list[str] | None],
) -> list[RowT]:
    rows: list[RowT] = []
    seen: set[str] = set()
    while len(rows) < limit:
        requested = limit - len(rows)
        page = get_json_object(
            session,
            url,
            params={**params, "start": len(rows), "limit": requested},
        )
        results, total = _page(page, len(rows), requested, label)
        if not results:
            # An empty page is the terminal signal of the count-based
            # endpoints; a total that still owes rows means the answer is broken.
            if total is not None and total > len(rows):
                raise AtlaWireError(
                    f"Confluence {label} returned an empty page before all matches; "
                    f"{empty_hint}"
                )
            return rows
        # The endpoint can cap a page or omit _links.next, so advance by what
        # was actually read rather than by a link or a claimed total.
        fingerprint = _page_fingerprint(results, identities)
        if fingerprint in seen:
            raise AtlaWireError(f"Confluence {label} returned a repeated page.")
        seen.add(fingerprint)
        rows.extend(project(result) for result in results)
    return rows


def _page_fingerprint(
    results: list[dict[str, object]],
    identities: Callable[[list[dict[str, object]]], list[str] | None],
) -> str:
    stable = identities(results)
    if stable is None:
        return _raw_fingerprint(results)
    return "ids:" + json.dumps(stable, ensure_ascii=True, separators=(",", ":"))


def _stable_id(value: object) -> str | None:
    """Return a normalized nonempty string or integer ID, else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    return None


def _content_identities(results: list[dict[str, object]]) -> list[str] | None:
    """Identify a result page by every row's nonempty nested ``content.id``.

    A repeated page may arrive with different presentation metadata, so a page
    whose rows all carry stable identities is compared by the ordered list.
    ``None`` asks for the raw-equality fallback when any identity is unavailable;
    distinct identities never collapse.
    """
    identities: list[str] = []
    for result in results:
        content = result.get("content")
        if not isinstance(content, dict):
            return None
        stable_id = _stable_id(content.get("id"))
        if stable_id is None:
            return None
        identities.append(stable_id)
    return identities


def _space_identities(results: list[dict[str, object]]) -> list[str] | None:
    """Identify a space page by every row's nonempty top-level ``key``.

    Keys are the space endpoint's stable identity. ``None`` asks for the
    raw-equality fallback, and equal names never merge distinct spaces.
    """
    identities: list[str] = []
    for result in results:
        key = result.get("key")
        if isinstance(key, str) and key:
            identities.append(key)
        else:
            return None
    return identities


def _child_identities(results: list[dict[str, object]]) -> list[str] | None:
    """Identify a child page by every row's nonempty top-level ``id``.

    ``id`` is the child endpoint's stable identity, so a repeated page is still
    detected when its title or version changes; string and integer forms of the
    same ID compare equal. ``None`` asks for the raw-equality fallback when any
    identity is unavailable, and equal titles never merge distinct children.
    """
    identities: list[str] = []
    for result in results:
        stable_id = _stable_id(result.get("id"))
        if stable_id is None:
            return None
        identities.append(stable_id)
    return identities


def _raw_fingerprint(results: list[dict[str, object]]) -> str:
    return "raw:" + json.dumps(
        results, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )


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
    if not isinstance(value, str):
        raise AtlaWireError(_INVALID_SPACE)
    return value


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
    return value


def _child_text(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
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
    return value


def _text_value(
    content: dict[str, object], item: dict[str, object], key: str
) -> str | None:
    value = content.get(key)
    if value is None:
        return _string(item, key)
    if not isinstance(value, str):
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
        if not isinstance(key, str):
            raise AtlaWireError(_INVALID_RESULT)
        return key
    expandable = item.get("_expandable")
    if expandable is None:
        return None
    if not isinstance(expandable, dict):
        raise AtlaWireError(_INVALID_RESULT)
    path = expandable.get("space")
    if path is None:
        return None
    if not isinstance(path, str):
        raise AtlaWireError(_INVALID_RESULT)
    return path.rsplit("/", 1)[-1] or None


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
    if not isinstance(value, str):
        raise AtlaWireError(_INVALID_RESULT)
    return value

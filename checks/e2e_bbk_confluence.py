"""E2E checks of BBK's Confluence and federated-search contracts via AtlaWire.

Run explicitly, against a real deployment, only with the opt-in switch::

    C:/Python315/python.exe -B -m pytest -q -p no:cacheprovider \
        checks/e2e_bbk_confluence.py          (with ATLAWIRE_E2E_LIVE=1)

Each BBK function under test is replaced by its AtlaWire counterpart, and the
saved BBK credentials file is read through AtlaWire's own loader, so no token or
base URL reaches a command line, a log, a failure message, or this source file.

The run is read-only by construction: only the GET-backed adapters
``list_spaces``, ``search_cql``, ``get_page``, ``list_children``, ``whoami``,
and ``federated_search`` are called, plus the pure ``render_page_markdown``. No
write, comment, page edit, schedule change, or message-send operation exists in
this module's import graph.

Discovered objects are never hardcoded: the first space that yields a page is
found with a narrow CQL query, and that page is accepted only after its storage,
version, space, and ancestors were validated. A 401, 403, or 429 response stops
the live run after the first failure, so no further request is attempted;
failures name a fixed check and AtlaWire's closed error category, never a URL,
token, response body, or server-supplied text.

Known AtlaWire coverage gaps are documented instead of asserted as passes:

* BBK ``whoami`` reports the Bitbucket server version; AtlaWire reports only
  that the authenticated dashboard read succeeded (``authenticated: true``).
* BBK ``selftest`` runs many probes (Bitbucket, Jira, Confluence, calendar,
  Kafka, NATS, Maven, ...); AtlaWire's ``selftest`` command is an alias of
  ``whoami`` and this module covers only the Confluence/find parts through the
  library.
* BBK ``page_md`` converts ``body.storage`` only; AtlaWire's
  ``render_page_markdown`` prepends the page title heading.
* BBK ``jira.resolve_user`` has no direct AtlaWire library equivalent.
* BBK ``find`` returns ``errors`` as a list of strings; AtlaWire returns a
  product-keyed error mapping, empty when every product answered.
"""

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from atlawire.confluence import (
    ChildRow,
    ContentRow,
    SpaceRow,
    get_page,
    list_children,
    list_spaces,
    search_cql,
)
from atlawire.confluence_markdown import render_page_markdown
from atlawire.credentials import load_saved_credentials
from atlawire.federated import ProductTarget, federated_search
from atlawire.http import AtlaWireError
from atlawire.identity import whoami

GATE_ENV = "ATLAWIRE_E2E_LIVE"
PRODUCTS = ("confluence", "jira", "bitbucket")
# Narrow, bounded discovery: no page id, space key, or search term is pinned.
SPACE_SCAN_LIMIT = 8
PAGE_SCAN_LIMIT = 5
CANDIDATE_PAGES = 6
CHILD_LIMIT = 10
FIND_LIMIT = 2
STOP_STATUSES = frozenset({401, 403, 429})
MATCH_EVIDENCE = frozenset({"highlight", "context-only", "none"})
_TERM_WORD = re.compile(r"[0-9A-Za-z\u0401\u0451\u0410-\u044f]{4,}")


def _enabled() -> bool:
    """Return whether the operator explicitly opted into a real-server run."""
    value = os.environ.get(GATE_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


pytestmark = pytest.mark.skipif(
    not _enabled(),
    reason=f"opt-in real-server run: set {GATE_ENV}=1",
)

_stop_reason: list[str] = []


def _require(condition: bool, message: str) -> None:
    """Fail with one fixed message; never echo server data or credentials."""
    if not condition:
        pytest.fail(message, pytrace=False)


def _live_call[T](
    check: str, function: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Run one read-only adapter call and map failures to sanitized categories."""
    if _stop_reason:
        pytest.skip(f"live run already stopped after {_stop_reason[0]}")
    try:
        return function(*args, **kwargs)
    except AtlaWireError as exc:
        status = getattr(exc, "http_status", None)
        category = getattr(exc, "category", None) or "unclassified"
        if status in STOP_STATUSES:
            _stop_reason.append(f"{check} (HTTP {status})")
            pytest.fail(
                f"LIVE-STOP: {check} was refused with HTTP {status}; "
                "no further live request is made",
                pytrace=False,
            )
        pytest.fail(f"{check} failed with category {category}", pytrace=False)


@pytest.fixture(scope="module")
def targets() -> dict[str, ProductTarget]:
    """Resolve all three saved BBK pairs through AtlaWire's own loader."""
    resolved: dict[str, ProductTarget] = {}
    for product in PRODUCTS:
        try:
            saved = load_saved_credentials(product, allow_http_loopback=False)
        except AtlaWireError as exc:
            category = getattr(exc, "category", None) or "unclassified"
            pytest.fail(
                f"saved BBK credentials are unusable for {product} ({category})",
                pytrace=False,
            )
        resolved[product] = ProductTarget(saved.base_url, saved.token)
    return resolved


@dataclass(frozen=True, slots=True)
class LivePage:
    """One discovered page with its validated direct children (possibly empty)."""

    space_key: str
    page_id: str
    page: dict[str, object]
    children: list[ChildRow]


def _assert_space_rows(rows: Sequence[SpaceRow]) -> None:
    """Check BBK's ``spaces`` row contract: [{key, name, type}]."""
    _require(bool(rows), "inconclusive: the instance returned no spaces")
    for row in rows:
        _require(
            set(row) == {"key", "name", "type"},
            "space row fields differ from BBK {key, name, type}",
        )
        _require(
            isinstance(row["key"], str) and bool(row["key"]),
            "space key must be non-empty text",
        )
        _require(
            row["name"] is None or isinstance(row["name"], str),
            "space name must be text or None",
        )
        _require(
            row["type"] is None or isinstance(row["type"], str),
            "space type must be text or None",
        )


def _assert_content_rows(rows: Sequence[ContentRow]) -> None:
    """Check BBK's ``search_cql`` row contract: [{id, title, space, type, url}]."""
    _require(bool(rows), "inconclusive: the narrow CQL query returned no pages")
    for row in rows:
        _require(
            set(row) == {"id", "title", "space", "type", "url"},
            "CQL row fields differ from BBK {id, title, space, type, url}",
        )
        identifier = row["id"]
        _require(
            not isinstance(identifier, bool)
            and isinstance(identifier, (str, int))
            and str(identifier) != "",
            "CQL row id must be non-empty text or an integer",
        )
        for field in ("space", "type", "title", "url"):
            _require(
                row[field] is None or isinstance(row[field], str),
                f"CQL row {field} must be text or None",
            )


def _assert_page(page: dict[str, object]) -> None:
    """Check BBK's ``page`` contract: identity, space, version, ancestors, storage."""
    _require(page.get("type") == "page", "page type must be 'page'")
    title = page.get("title")
    _require(
        isinstance(title, str) and bool(title.strip()),
        "page title must be non-empty text",
    )
    version = page.get("version")
    _require(isinstance(version, dict), "page version must be an object")
    number = version.get("number") if isinstance(version, dict) else None
    _require(
        isinstance(number, int) and not isinstance(number, bool) and number >= 1,
        "page version.number must be a positive integer",
    )
    space = page.get("space")
    _require(isinstance(space, dict), "page space must be an object")
    _require(
        isinstance(space.get("key"), str) if isinstance(space, dict) else False,
        "page space must expose a text key",
    )
    ancestors = page.get("ancestors")
    _require(isinstance(ancestors, list), "page ancestors must be a list")
    for ancestor in ancestors if isinstance(ancestors, list) else ():
        _require(
            isinstance(ancestor, dict) and isinstance(ancestor.get("id"), (str, int)),
            "page ancestor must expose an id",
        )
    body = page.get("body")
    _require(isinstance(body, dict), "page body must be an object")
    storage = body.get("storage") if isinstance(body, dict) else None
    _require(isinstance(storage, dict), "page body.storage must be an object")
    value = storage.get("value") if isinstance(storage, dict) else None
    _require(
        isinstance(value, str) and bool(value.strip()),
        "page body.storage.value must be non-empty storage XHTML",
    )


def _assert_child_rows(rows: Sequence[ChildRow]) -> None:
    """Check BBK's ``children`` row contract: [{id, title, version}]."""
    for row in rows:
        _require(
            set(row) == {"id", "title", "version"},
            "child row fields differ from BBK {id, title, version}",
        )
        identifier = row["id"]
        _require(
            not isinstance(identifier, bool)
            and isinstance(identifier, (str, int))
            and str(identifier) != "",
            "child id must be non-empty text or an integer",
        )
        _require(
            row["title"] is None or isinstance(row["title"], str),
            "child title must be text or None",
        )
        version = row["version"]
        _require(
            version is None
            or (
                isinstance(version, int)
                and not isinstance(version, bool)
                and version >= 0
            ),
            "child version must be a non-negative integer or None",
        )


def _page_identity(page: dict[str, object]) -> str:
    identifier = page.get("id")
    return "" if isinstance(identifier, bool) else str(identifier)


@pytest.fixture(scope="module")
def discovered(targets: dict[str, ProductTarget]) -> LivePage:
    """Find one real page with children using only narrow, bounded reads."""
    confluence = targets["confluence"]
    base, token = confluence.base_url, confluence.token
    spaces = _live_call(
        "Confluence spaces", list_spaces, base, token=token, limit=SPACE_SCAN_LIMIT
    )
    _assert_space_rows(spaces)
    fallback: LivePage | None = None
    inspected = 0
    for space in spaces:
        key = space["key"]
        if not isinstance(key, str) or not key:
            continue
        rows = _live_call(
            "Confluence CQL",
            search_cql,
            base,
            f'space = "{key}" and type = page',
            token=token,
            limit=PAGE_SCAN_LIMIT,
        )
        if not rows:
            continue
        _assert_content_rows(rows)
        for row in rows:
            if inspected >= CANDIDATE_PAGES:
                break
            candidate = row["id"]
            if isinstance(candidate, bool) or not isinstance(candidate, (str, int)):
                continue
            inspected += 1
            page = _live_call("Confluence page", get_page, base, candidate, token=token)
            _assert_page(page)
            page_id = _page_identity(page)
            _require(page_id != "", "the fetched page must carry its own id")
            children = _live_call(
                "Confluence children",
                list_children,
                base,
                page_id,
                token=token,
                limit=CHILD_LIMIT,
            )
            _assert_child_rows(children)
            found = LivePage(key, page_id, page, list(children))
            if fallback is None:
                fallback = found
            if children:
                return found
        if inspected >= CANDIDATE_PAGES:
            break
    if fallback is None:
        pytest.fail(
            "inconclusive: no page was found through a narrow CQL query",
            pytrace=False,
        )
    return fallback


def test_confluence_spaces_match_bbk(targets: dict[str, ProductTarget]) -> None:
    confluence = targets["confluence"]
    rows = _live_call(
        "Confluence spaces",
        list_spaces,
        confluence.base_url,
        token=confluence.token,
        limit=SPACE_SCAN_LIMIT,
    )
    _assert_space_rows(rows)


def test_confluence_cql_returns_bbk_rows(
    targets: dict[str, ProductTarget], discovered: LivePage
) -> None:
    confluence = targets["confluence"]
    query = f'space = "{discovered.space_key}" and type = page'
    rows = _live_call(
        "Confluence CQL",
        search_cql,
        confluence.base_url,
        query,
        token=confluence.token,
        limit=PAGE_SCAN_LIMIT,
    )
    _assert_content_rows(rows)
    identifiers = {str(row["id"]) for row in rows}
    _require(
        discovered.page_id in identifiers,
        "the discovered page must appear in the CQL rows that found it",
    )


def test_confluence_page_storage_matches_bbk(
    targets: dict[str, ProductTarget], discovered: LivePage
) -> None:
    confluence = targets["confluence"]
    page = _live_call(
        "Confluence page",
        get_page,
        confluence.base_url,
        discovered.page_id,
        token=confluence.token,
    )
    _assert_page(page)
    _require(
        _page_identity(page) == discovered.page_id,
        "the requested page must be the returned page",
    )


def test_confluence_page_markdown_is_non_empty(
    discovered: LivePage,
) -> None:
    markdown = render_page_markdown(discovered.page)
    _require(
        isinstance(markdown, str) and bool(markdown.strip()),
        "page Markdown must be non-empty text",
    )
    title = str(discovered.page["title"])
    first_line = markdown.splitlines()[0] if markdown else ""
    _require(
        first_line.startswith("# ") and bool(first_line[2:].strip()),
        "page Markdown must open with a non-empty title heading",
    )
    # Markdown escaping may alter punctuation in the title, so only a readable
    # word (letters and digits, never escaped) is required in the heading.
    token = _TERM_WORD.search(title)
    if token is not None:
        _require(
            token.group(0) in first_line,
            "the title heading must keep readable text from the page title",
        )


def test_confluence_children_match_bbk(
    targets: dict[str, ProductTarget], discovered: LivePage
) -> None:
    if not discovered.children:
        pytest.skip("inconclusive: the discovered page has no direct children")
    confluence = targets["confluence"]
    rows = _live_call(
        "Confluence children",
        list_children,
        confluence.base_url,
        discovered.page_id,
        token=confluence.token,
        limit=CHILD_LIMIT,
    )
    _assert_child_rows(rows)
    _require(bool(rows), "inconclusive: direct children disappeared")
    _require(
        any(isinstance(row["title"], str) and bool(row["title"]) for row in rows),
        "at least one child must have a readable title",
    )


def test_whoami_reports_three_products(targets: dict[str, ProductTarget]) -> None:
    checks = _live_call(
        "whoami",
        whoami,
        confluence=targets["confluence"],
        jira=targets["jira"],
        bitbucket=targets["bitbucket"],
    )
    _require(isinstance(checks, dict), "whoami must return an object")
    _require(
        set(checks) == {"confluence", "jira", "bitbucket"},
        "whoami must probe exactly the three BBK products",
    )
    for product in PRODUCTS:
        entry = checks[product]
        _require(isinstance(entry, dict), f"whoami {product} entry must be an object")
        _require(
            entry.get("ok") is True,
            f"whoami {product} must report authenticated access",
        )

    confluence_identity = checks["confluence"].get("identity")
    _require(
        isinstance(confluence_identity, dict)
        and set(confluence_identity) == {"username", "displayName"},
        "whoami Confluence identity fields differ from AtlaWire "
        "{username, displayName}",
    )
    if isinstance(confluence_identity, dict):
        _require(
            isinstance(confluence_identity.get("username"), str)
            and bool(confluence_identity["username"]),
            "whoami Confluence username must be non-empty text",
        )
        display_name = confluence_identity.get("displayName")
        _require(
            display_name is None or isinstance(display_name, str),
            "whoami Confluence displayName must be text or None",
        )

    jira_identity = checks["jira"].get("identity")
    _require(
        isinstance(jira_identity, dict)
        and set(jira_identity) == {"name", "displayName"},
        "whoami Jira identity fields differ from AtlaWire {name, displayName}",
    )
    if isinstance(jira_identity, dict):
        _require(
            isinstance(jira_identity.get("name"), str) and bool(jira_identity["name"]),
            "whoami Jira name must be non-empty text",
        )

    # BBK reported the Bitbucket server version here. AtlaWire deliberately
    # reports only a proven authenticated read, so version parity is a known gap.
    bitbucket_entry = checks["bitbucket"]
    _require(
        isinstance(bitbucket_entry, dict)
        and set(bitbucket_entry) == {"ok", "authenticated"}
        and bitbucket_entry.get("authenticated") is True,
        "whoami Bitbucket must report {ok: true, authenticated: true}",
    )


def _search_term(discovered: LivePage) -> str:
    title = discovered.page.get("title")
    if isinstance(title, str):
        match = _TERM_WORD.search(title)
        if match is not None:
            return match.group(0)
    return discovered.space_key


def _assert_row_terms(row: dict[str, object], channel: str) -> None:
    """Check a merged row keeps the non-empty terms that found it."""
    terms = row["terms"]
    _require(
        isinstance(terms, list)
        and bool(terms)
        and all(isinstance(term, str) and term for term in terms),
        f"federated {channel} row terms must be non-empty text",
    )


def _assert_federated_rows(result: dict[str, object]) -> None:
    confluence_rows = result["confluence"]
    _require(
        isinstance(confluence_rows, list), "federated confluence rows must be a list"
    )
    for row in confluence_rows:
        _require(
            isinstance(row, dict)
            and set(row) == {"id", "title", "space", "type", "url", "terms"},
            "federated confluence row fields differ from AtlaWire contract",
        )
        if isinstance(row, dict):
            _assert_row_terms(row, "Confluence")
            identifier = row["id"]
            _require(
                not isinstance(identifier, bool)
                and isinstance(identifier, (str, int))
                and str(identifier) != "",
                "federated Confluence row id must be non-empty text or an integer",
            )

    jira_rows = result["jira"]
    _require(isinstance(jira_rows, list), "federated Jira rows must be a list")
    for row in jira_rows:
        _require(
            isinstance(row, dict)
            and set(row)
            == {
                "key",
                "status",
                "type",
                "priority",
                "assignee",
                "updated",
                "summary",
                "terms",
            },
            "federated Jira row fields differ from AtlaWire contract",
        )
        if isinstance(row, dict):
            _require(
                isinstance(row["key"], str) and bool(row["key"]),
                "federated Jira row key must be non-empty text",
            )
            _require(
                isinstance(row["updated"], str) and bool(row["updated"]),
                "federated Jira row updated must be non-empty text",
            )
            _require(
                isinstance(row["summary"], str),
                "federated Jira row summary must be text",
            )
            _assert_row_terms(row, "Jira")

    bitbucket_rows = result["bitbucket"]
    _require(
        isinstance(bitbucket_rows, list), "federated Bitbucket rows must be a list"
    )
    for row in bitbucket_rows:
        _require(
            isinstance(row, dict)
            and set(row)
            == {
                "project",
                "repository",
                "file",
                "hitCount",
                "matchEvidence",
                "terms",
            },
            "federated Bitbucket row fields differ from AtlaWire contract",
        )
        if isinstance(row, dict):
            for field in ("project", "repository", "file"):
                _require(
                    isinstance(row[field], str) and bool(row[field]),
                    f"federated Bitbucket row {field} must be non-empty text",
                )
            hit_count = row["hitCount"]
            _require(
                hit_count is None
                or (
                    isinstance(hit_count, int)
                    and not isinstance(hit_count, bool)
                    and hit_count >= 0
                ),
                "federated Bitbucket hitCount must be a non-negative integer or None",
            )
            _require(
                row["matchEvidence"] in MATCH_EVIDENCE,
                "federated Bitbucket matchEvidence must be a known evidence value",
            )
            _assert_row_terms(row, "Bitbucket")


def test_federated_find_counts_and_errors(
    targets: dict[str, ProductTarget], discovered: LivePage
) -> None:
    term = _search_term(discovered)
    result = _live_call(
        "federated search",
        federated_search,
        [term],
        confluence=targets["confluence"],
        jira=targets["jira"],
        bitbucket=targets["bitbucket"],
        limit=FIND_LIMIT,
    )
    _require(isinstance(result, dict), "federated search must return an object")
    _require(
        set(result)
        == {
            "terms",
            "confluence",
            "jira",
            "bitbucket",
            "counts",
            "errors",
            "complete",
            "budget",
            "limits",
            "limitations",
        },
        "federated result fields differ from the AtlaWire contract",
    )
    _require(
        result["terms"] == [term],
        "federated result must echo the effective search terms",
    )
    _require(
        isinstance(result["errors"], dict) and result["errors"] == {},
        "federated result must report an empty error mapping (BBK: empty "
        "list) when every product answered",
    )
    _require(
        result["complete"] is True,
        "federated result must be complete when no product failed",
    )

    counts = result["counts"]
    _require(isinstance(counts, dict), "federated counts must be an object")
    if isinstance(counts, dict):
        _require(
            set(counts) == {"confluence", "jira", "bitbucket"},
            "federated counts must cover exactly the three products",
        )
        for channel in PRODUCTS:
            value = counts[channel]
            _require(
                isinstance(value, int) and not isinstance(value, bool),
                f"federated counts.{channel} must be an integer",
            )
            rows = result[channel]
            _require(
                isinstance(rows, list) and value == len(rows),
                f"federated counts.{channel} must equal its merged row count",
            )

    budget = result["budget"]
    _require(isinstance(budget, dict), "federated budget must be an object")
    if isinstance(budget, dict):
        _require(
            set(budget) == {"limit", "used", "exhausted"},
            "federated budget fields differ from the AtlaWire contract",
        )
        _require(
            isinstance(budget["limit"], int) and budget["limit"] > 0,
            "federated budget limit must be a positive integer",
        )
        _require(
            isinstance(budget["used"], int) and budget["used"] >= 1,
            "federated search must charge at least one logical read",
        )
        _require(
            budget["exhausted"] is False,
            "federated search must not exhaust the read budget",
        )

    limits = result["limits"]
    _require(isinstance(limits, dict), "federated limits must be an object")
    if isinstance(limits, dict):
        _require(
            limits.get("per_term_per_product") == FIND_LIMIT,
            "federated limits must report the requested per-term cap",
        )

    limitations = result["limitations"]
    _require(
        isinstance(limitations, list) and bool(limitations),
        "federated result must keep its limitations list",
    )
    _require(
        all(isinstance(item, str) and item for item in limitations),
        "federated limitations must be non-empty text items",
    )

    _assert_federated_rows(result)
    merged = sum(result["counts"].values()) if isinstance(counts, dict) else 0
    if merged == 0:
        pytest.skip("inconclusive: the derived term produced no merged rows")

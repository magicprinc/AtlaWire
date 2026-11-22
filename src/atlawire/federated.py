"""Read-only federated search across Confluence, Jira, and Bitbucket.

This is the AtlaWire counterpart of BBK's ``find``: several formulations of one
question are searched in all three products, duplicate hits are merged, and only
compact rows plus counts are returned. Each product is called through its
existing public read adapter with its own explicit matched base URL and token,
so no destination or credential is ever shared between products.

Differences from BBK's ``find``:

* **Fail closed.** A failure in any product raises
  [AtlaWireError][atlawire.http.AtlaWireError] and publishes nothing. BBK
  returned the surviving channels plus an ``errors`` list; such a partial answer
  can look complete to an agent, so it is not reproduced here.
* **No raw term interpolation.** Each term becomes one double-quoted literal.
  Double quotes, backslashes, controls, bidi controls, and lone surrogates are
  rejected before any request instead of escaped, because Jira Server documents
  both quoted strings and a two-backslash text-search escape while CQL documents
  a narrower escape set; one grammar applied to both could silently change a
  term. References: Jira Software Server 8.3, "Advanced searching", and
  Confluence, "Advanced Searching using CQL":
https://confluence.atlassian.com/jirasoftwareserver083/advanced-searching-976770304.html
https://developer.atlassian.com/server/confluence/advanced-searching-using-cql/
* **Deterministic output.** Rows keep first-seen order; pages merge by ID, issues
  by key, and Bitbucket files by project/repository/path. Every row lists the
  terms that found it.

The result is deliberately incomplete: every product is capped per term, and
Bitbucket can return only indexed code, so ``limitations`` is always present.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypedDict

from atlawire.bitbucket_search import MatchEvidence, SearchRow, search_code
from atlawire.confluence import ContentRow, search_cql
from atlawire.http import AtlaWireError, normalize_base_url
from atlawire.jira import IssueRow as JiraIssueRow
from atlawire.jira import search_issues

__all__ = [
    "LIMITATIONS",
    "LIMIT_DEFAULT",
    "LIMIT_MAX",
    "LIMIT_MIN",
    "ProductTarget",
    "federated_search",
]

LIMIT_MIN = 1
# Intersection of the three adapters' ceilings (Bitbucket search caps at 999).
LIMIT_MAX = 999
LIMIT_DEFAULT = 20
JIRA_ORDER = "created DESC"

LIMITATIONS = (
    (
        "Each product returns at most the per-term limit; matches beyond that "
        "cap may be omitted."
    ),
    (
        "Bitbucket searches only code indexed by the Bitbucket Search plugin, "
        "typically the default branch, so matches outside that coverage may be "
        "missing."
    ),
    (
        "Counts are unique merged rows, not proof that no further match exists "
        "in any product."
    ),
)

_BEARER_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]+")
_EVIDENCE_RANK: dict[MatchEvidence, int] = {
    "highlight": 2,
    "context-only": 1,
    "none": 0,
}
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
_INVALID_TERM = (
    "A search term must be plain text without double quotes, backslashes, or "
    "control characters."
)


@dataclass(frozen=True, slots=True)
class ProductTarget:
    """One product's matched destination and bearer token pair."""

    base_url: str
    token: str = field(repr=False)


class PageRow(TypedDict):
    """A merged Confluence page row."""

    id: str | int
    title: str | None
    space: str | None
    type: str | None
    url: str | None
    terms: list[str]


class IssueRow(TypedDict):
    """A merged Jira issue row."""

    key: str
    status: str | None
    type: str | None
    priority: str | None
    assignee: str | None
    updated: str
    summary: str
    terms: list[str]


class FileRow(TypedDict):
    """A merged indexed Bitbucket file row."""

    project: str
    repository: str
    file: str
    hitCount: int | None
    matchEvidence: MatchEvidence
    terms: list[str]


def federated_search(
    terms: Sequence[str],
    *,
    confluence: ProductTarget,
    jira: ProductTarget,
    bitbucket: ProductTarget,
    limit: int = LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Search every term in all three products and return merged compact rows.

    ``terms`` holds different formulations of one question, for example
    ``["ported numbers", "ported", "МВНО"]``. At least one non-blank term is
    required; an exact repeated term is searched once. ``confluence``, ``jira``,
    and ``bitbucket`` are independent explicit pairs: each adapter receives only
    its own base URL and token, and every pair is validated before the first
    request, so a later failure cannot follow requests sent to a wrong
    destination.

    ``limit`` is the row cap passed to each product for each term (1 to 999).
    Deduplication happens after those caps, so the rows returned never prove
    that a product holds no further match.

    Confluence is queried with ``text ~ "<term>"``, Jira with the same clause
    ordered by ``created DESC`` (BBK's default), and Bitbucket with the term as
    the plugin's free-text query; the term itself is never rewritten except for
    the surrounding quotes. The Bitbucket term is passed verbatim, so the plugin
    may apply its own query qualifiers, which can only narrow that product.
    Bitbucket paging reads every server-capped page until the per-term limit or
    the terminal page, so a short page cannot silently end that term's search; a
    later-page transport or cursor failure stops the whole call.

    Returns one JSON-serializable object:

    * ``terms`` — the effective terms in first-seen order;
    * ``confluence`` — ``{id, title, space, type, url, terms}`` rows;
    * ``jira`` — ``{key, status, type, priority, assignee, updated, summary,
      terms}`` rows;
    * ``bitbucket`` — ``{project, repository, file, hitCount, matchEvidence,
      terms}`` rows; ``matchEvidence`` keeps the strongest value seen for that
      file across terms (``highlight`` > ``context-only`` > ``none``);
    * ``counts`` — unique merged rows per product;
    * ``limits`` — the per-term cap actually used;
    * ``limitations`` — the always-present coverage warnings.

    Raises [AtlaWireError][atlawire.http.AtlaWireError] for invalid input, an
    invalid or incomplete pair, any product failure, or a result lacking a
    stable identity. Nothing is returned in those cases.
    """
    searched = _search_terms(terms)
    _check_limit(limit)
    targets = (
        _target("Confluence", confluence, allow_http_loopback),
        _target("Jira", jira, allow_http_loopback),
        _target("Bitbucket", bitbucket, allow_http_loopback),
    )
    # Build every query before the first request, so no term can fail late.
    queries = tuple((term, _cql_query(term), _jql_query(term)) for term in searched)
    pages, issues, files = _collect(queries, targets, limit, allow_http_loopback)
    return {
        "terms": list(searched),
        "confluence": list(pages.values()),
        "jira": list(issues.values()),
        "bitbucket": list(files.values()),
        "counts": {
            "confluence": len(pages),
            "jira": len(issues),
            "bitbucket": len(files),
        },
        "limits": {"per_term_per_product": limit},
        "limitations": list(LIMITATIONS),
    }


def _collect(
    queries: Sequence[tuple[str, str, str]],
    targets: tuple[ProductTarget, ProductTarget, ProductTarget],
    limit: int,
    allow_http_loopback: bool,
) -> tuple[
    dict[str, PageRow], dict[str, IssueRow], dict[tuple[str, str, str], FileRow]
]:
    """Merge one term at a time in BBK's Confluence, Jira, Bitbucket order."""
    pages: dict[str, PageRow] = {}
    issues: dict[str, IssueRow] = {}
    files: dict[tuple[str, str, str], FileRow] = {}
    confluence, jira, bitbucket = targets
    for term, cql, jql in queries:
        for page in _confluence_rows(confluence, cql, limit, allow_http_loopback):
            _merge_page(pages, page, term)
        for issue in _jira_rows(jira, jql, limit, allow_http_loopback):
            _merge_issue(issues, issue, term)
        for code in _bitbucket_rows(bitbucket, term, limit, allow_http_loopback):
            _merge_file(files, code, term)
    return pages, issues, files


def _confluence_rows(
    target: ProductTarget, query: str, limit: int, allow_http_loopback: bool
) -> list[ContentRow]:
    try:
        return search_cql(
            target.base_url,
            query,
            token=target.token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise _failure("Confluence", exc) from None


def _jira_rows(
    target: ProductTarget, query: str, limit: int, allow_http_loopback: bool
) -> list[JiraIssueRow]:
    try:
        return search_issues(
            target.base_url,
            query,
            token=target.token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise _failure("Jira", exc) from None


def _bitbucket_rows(
    target: ProductTarget, query: str, limit: int, allow_http_loopback: bool
) -> list[SearchRow]:
    try:
        return search_code(
            target.base_url,
            query,
            token=target.token,
            limit=limit,
            every_page=True,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise _failure("Bitbucket", exc) from None


def _failure(product: str, exc: AtlaWireError) -> AtlaWireError:
    """Describe a stopped federated call without echoing its request details."""
    return AtlaWireError(
        f"Federated search stopped: the {product} search failed and no partial "
        f"result was published. {exc}"
    )


def _merge_page(pages: dict[str, PageRow], row: ContentRow, term: str) -> None:
    page_id = row["id"]
    if isinstance(page_id, bool) or page_id is None or str(page_id) == "":
        raise AtlaWireError("Confluence search returned a page without a stable ID.")
    key = str(page_id)
    entry = pages.get(key)
    if entry is None:
        pages[key] = PageRow(
            id=page_id,
            title=row["title"],
            space=row["space"],
            type=row["type"],
            url=row["url"],
            terms=[term],
        )
        return
    _merge_term(entry["terms"], term)


def _merge_issue(issues: dict[str, IssueRow], row: JiraIssueRow, term: str) -> None:
    key = row["key"]
    if not isinstance(key, str) or not key:
        raise AtlaWireError("Jira search returned an issue without a stable key.")
    entry = issues.get(key)
    if entry is None:
        issues[key] = IssueRow(
            key=key,
            status=row["status"],
            type=row["type"],
            priority=row["priority"],
            assignee=row["assignee"],
            updated=row["updated"],
            summary=row["summary"],
            terms=[term],
        )
        return
    _merge_term(entry["terms"], term)


def _merge_file(
    files: dict[tuple[str, str, str], FileRow], row: SearchRow, term: str
) -> None:
    project = row["project"]
    repository = row["repository"]
    path = row["file"]
    if not isinstance(project, str) or not project:
        raise AtlaWireError("Bitbucket search returned a file without a project.")
    if not isinstance(repository, str) or not repository:
        raise AtlaWireError("Bitbucket search returned a file without a repository.")
    if not isinstance(path, str) or not path:
        raise AtlaWireError("Bitbucket search returned a file without a path.")
    # Project keys and repository slugs are case-insensitive in Bitbucket; the
    # path is not. The first row keeps its spelling for deterministic output.
    key = (project.lower(), repository.lower(), path)
    entry = files.get(key)
    if entry is None:
        files[key] = FileRow(
            project=project,
            repository=repository,
            file=path,
            hitCount=row["hitCount"],
            matchEvidence=row["matchEvidence"],
            terms=[term],
        )
        return
    entry["hitCount"] = _max_hit_count(entry["hitCount"], row["hitCount"])
    entry["matchEvidence"] = _stronger_evidence(
        entry["matchEvidence"], row["matchEvidence"]
    )
    _merge_term(entry["terms"], term)


def _max_hit_count(current: int | None, candidate: int | None) -> int | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)


def _stronger_evidence(
    current: MatchEvidence, candidate: MatchEvidence
) -> MatchEvidence:
    """Keep the strongest confirmed evidence for one file across terms.

    A later term can produce a highlighted line for a file that an earlier term
    only matched through context, and keeping the earlier value would hide that
    confirmed match. The ranking is total, so the result does not depend on the
    term order.
    """
    if _EVIDENCE_RANK[candidate] > _EVIDENCE_RANK[current]:
        return candidate
    return current


def _merge_term(terms: list[str], term: str) -> None:
    if term not in terms:
        terms.append(term)


def _search_terms(terms: Sequence[str]) -> tuple[str, ...]:
    """Validate every term before any request and drop exact repeats."""
    if isinstance(terms, (str, bytes)) or not isinstance(terms, Sequence):
        raise AtlaWireError(
            "Expected at least one search term as a sequence of strings."
        )
    unique: list[str] = []
    for term in terms:
        _check_term(term)
        if term not in unique:
            unique.append(term)
    if not unique:
        raise AtlaWireError("Expected at least one search term.")
    return tuple(unique)


def _check_term(term: object) -> None:
    if not isinstance(term, str) or not term.strip():
        raise AtlaWireError("Each search term must be non-empty text.")
    for char in term:
        code = ord(char)
        if (
            char in {'"', "\\"}
            or code < 0x20
            or 0x7F <= code <= 0x9F
            or 0xD800 <= code <= 0xDFFF
            or code in {0x2028, 0x2029}
            or char in _BIDI_CONTROLS
        ):
            raise AtlaWireError(_INVALID_TERM)


def _quoted(term: str) -> str:
    """Wrap a screened term in one double-quoted literal.

    Both grammars accept double-quoted values, and the term is the only content
    inside the quotes. ``"`` and ``\\`` are rejected rather than escaped: the
    Jira 8.3 text-search escape differs from CQL's documented set, and the
    deployed versions are not verified. Without those two characters the
    literal cannot terminate early, so the surrounding clause stays fixed.
    """
    _check_term(term)
    return f'"{term}"'


def _cql_query(term: str) -> str:
    return f"text ~ {_quoted(term)}"


def _jql_query(term: str) -> str:
    return f"text ~ {_quoted(term)} ORDER BY {JIRA_ORDER}"


def _check_limit(limit: object) -> None:
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not LIMIT_MIN <= limit <= LIMIT_MAX
    ):
        raise AtlaWireError(
            f"The per-term limit must be from {LIMIT_MIN} to {LIMIT_MAX}."
        )


def _target(product: str, value: object, allow_http_loopback: bool) -> ProductTarget:
    """Validate one explicit pair and normalize only its destination."""
    if not isinstance(value, ProductTarget):
        raise AtlaWireError(f"Expected an explicit {product} base URL and token pair.")
    if not isinstance(value.base_url, str) or not isinstance(value.token, str):
        raise AtlaWireError(f"The {product} base URL or token is invalid.")
    try:
        base_url = normalize_base_url(
            value.base_url, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError:
        raise AtlaWireError(f"The {product} base URL is invalid.") from None
    if _BEARER_TOKEN.fullmatch(value.token) is None:
        raise AtlaWireError(f"The {product} token is missing or invalid.")
    return ProductTarget(base_url=base_url, token=value.token)

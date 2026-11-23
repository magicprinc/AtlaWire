"""Read-only federated search across Confluence, Jira, and Bitbucket.

This is the AtlaWire counterpart of BBK's ``find``: several formulations of one
question are searched in all three products, duplicate hits are merged, and only
compact rows plus counts are returned. Each product is called through its
existing public read adapter with its own explicit matched base URL and token,
so no destination or credential is ever shared between products.

Differences from BBK's ``find``:

* **Partial answers are labelled.** An unavailable or failing product
  contributes no rows and exactly one message in ``errors``, and ``complete`` is
  false; the total-failure error is raised only when no product/term read
  completed at all. BBK returned the surviving channels plus an ``errors`` list;
  the difference here is that every partial answer says so via ``complete``.
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
* **Bounded work.** One call charges a fixed number of logical reads, and a run
  that runs out stops scheduling instead of overspending. Exhaustion is
  reported in its own ``budget`` block rather than as a product error, because
  no product failed.

The result is deliberately incomplete: every product is capped per term, and
Bitbucket can return only indexed code, so ``limitations`` is always present.
"""

import re
from collections.abc import Callable, Sequence
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
    "READ_BUDGET",
    "ProductTarget",
    "federated_search",
]

LIMIT_MIN = 1
# Intersection of the three adapters' ceilings (Bitbucket search caps at 999).
LIMIT_MAX = 999
LIMIT_DEFAULT = 20
# One logical read is one product/term adapter invocation, plus one more for
# every Bitbucket page after the first in that term's every_page traversal.
# 60 covers the useful case (up to 20 terms across three products) in one call
# while still bounding an operator who pastes many formulations of one query.
# A long term list is not a request for more work per term; it is a fallback
# list, so the cap is a call bound, not a per-term guarantee.
READ_BUDGET = 60
JIRA_ORDER = "created DESC"
_PRODUCT_SLOTS = (
    ("confluence", "Confluence"),
    ("jira", "Jira"),
    ("bitbucket", "Bitbucket"),
)

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
    confluence: ProductTarget | None,
    jira: ProductTarget | None,
    bitbucket: ProductTarget | None,
    limit: int = LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Search every term in all three products and return merged compact rows.

    ``terms`` holds different formulations of one question, for example
    ``["ported numbers", "ported", "МВНО"]``. At least one non-blank term is
    required; an exact repeated term is searched once. ``confluence``, ``jira``,
    and ``bitbucket`` are independent explicit pairs: each adapter receives only
    its own base URL and token. Every supplied pair is validated strictly before
    the first request, so a token is never sent to a destination it was not
    configured with. ``None`` means that product is not configured; it is
    reported in ``errors`` and the other products are still searched.

    ``limit`` is the row cap passed to each product for each term (1 to 999).
    Deduplication happens after those caps, so the rows returned never prove
    that a product holds no further match.

    One call performs at most
    [READ_BUDGET][atlawire.federated.READ_BUDGET] logical reads across every
    product and term. Each product/term adapter invocation costs one read, and a
    Bitbucket term costs one more for every page it reads after the first. The
    budget is checked before a read starts, so an exhausted run stops scheduling
    work, keeps every completed result, and reports ``complete: false``.

    Confluence is queried with ``text ~ "<term>"``, Jira with the same clause
    ordered by ``created DESC`` (BBK's default), and Bitbucket with the term as
    the plugin's free-text query; the term itself is never rewritten except for
    the surrounding quotes. The Bitbucket term is passed verbatim, so the plugin
    may apply its own query qualifiers, which can only narrow that product.
    Bitbucket paging reads every server-capped page until the per-term limit or
    the terminal page, so a short page cannot silently end that term's search; a
    later-page transport or cursor failure stops that product's term only.

    Returns one JSON-serializable object:

    * ``terms`` — the effective terms in first-seen order;
    * ``confluence`` — ``{id, title, space, type, url, terms}`` rows;
    * ``jira`` — ``{key, status, type, priority, assignee, updated, summary,
      terms}`` rows;
    * ``bitbucket`` — ``{project, repository, file, hitCount, matchEvidence,
      terms}`` rows; ``matchEvidence`` keeps the strongest value seen for that
      file across terms (``highlight`` > ``context-only`` > ``none``);
    * ``counts`` — unique merged rows per product;
    * ``errors`` — one message per product that was unavailable or failed for
      at least one term;
    * ``complete`` — true only when no product is unavailable, no error was
      recorded, and the read budget was not exhausted;
    * ``budget`` — ``{limit, used, exhausted}``: the cap, how many logical reads
      were charged, and whether a read was refused. Exhaustion is reported here
      alone: no product failed, so it never becomes a per-product error;
    * ``limits`` — the per-term cap actually used;
    * ``limitations`` — the always-present coverage warnings.

    Raises [AtlaWireError][atlawire.http.AtlaWireError] for invalid input, an
    invalid supplied pair, or when no product/term read completed at all; the
    last case uses a distinct message when the read budget stopped the run.
    A failed product/term keeps no rows, while earlier successful terms and the
    other products stay.
    """
    searched = _search_terms(terms)
    _check_limit(limit)
    targets, errors = _validated_targets(
        (confluence, jira, bitbucket), allow_http_loopback
    )
    # Build every query before the first request, so no term can fail late.
    queries = tuple((term, _cql_query(term), _jql_query(term)) for term in searched)
    budget = _ReadBudget(READ_BUDGET)
    merged = _collect(queries, targets, errors, limit, allow_http_loopback, budget)
    if merged.completed == 0:
        if budget.refused:
            raise AtlaWireError(
                "Federated search read budget was exhausted before any product "
                "answered; nothing was returned."
            )
        raise AtlaWireError(
            "Federated search failed for every product; nothing was returned."
        )
    return {
        "terms": list(searched),
        "confluence": list(merged.pages.values()),
        "jira": list(merged.issues.values()),
        "bitbucket": list(merged.files.values()),
        "counts": {
            "confluence": len(merged.pages),
            "jira": len(merged.issues),
            "bitbucket": len(merged.files),
        },
        "errors": errors,
        "complete": not errors and not budget.refused,
        "budget": {
            "limit": budget.limit,
            "used": budget.used,
            "exhausted": budget.refused,
        },
        "limits": {"per_term_per_product": limit},
        "limitations": list(LIMITATIONS),
    }


def _validated_targets(
    values: tuple[ProductTarget | None, ProductTarget | None, ProductTarget | None],
    allow_http_loopback: bool,
) -> tuple[dict[str, ProductTarget], dict[str, str]]:
    """Validate each supplied pair independently and record missing slots.

    A missing product becomes one error and no target, so the other products
    are still searched. Every supplied pair is validated strictly before the
    first request, which keeps a token away from an unconfigured destination.
    """
    targets: dict[str, ProductTarget] = {}
    errors: dict[str, str] = {}
    for (slot, product), value in zip(_PRODUCT_SLOTS, values, strict=True):
        if value is None:
            errors[slot] = (
                f"The {product} base URL and token are not configured or invalid."
            )
            continue
        targets[slot] = _target(product, value, allow_http_loopback)
    return targets, errors


class _BudgetExhausted(Exception):
    """Internal signal: a read was refused, so its product/term is not started.

    This is deliberately not an [AtlaWireError][atlawire.http.AtlaWireError]:
    nothing failed, and a refused read must not be reported as a product error.
    """


@dataclass(slots=True)
class _ReadBudget:
    """Charges logical reads and records the first refusal."""

    limit: int
    used: int = 0
    refused: bool = False

    def take(self) -> bool:
        """Charge one read, or refuse it and remember that work was skipped."""
        if self.used < self.limit:
            self.used += 1
            return True
        self.refused = True
        return False


@dataclass(slots=True)
class _Merged:
    """Rows merged so far plus the number of product/term reads that finished."""

    pages: dict[str, PageRow] = field(default_factory=dict)
    issues: dict[str, IssueRow] = field(default_factory=dict)
    files: dict[tuple[str, str, str], FileRow] = field(default_factory=dict)
    completed: int = 0


def _collect(
    queries: Sequence[tuple[str, str, str]],
    targets: dict[str, ProductTarget],
    errors: dict[str, str],
    limit: int,
    allow_http_loopback: bool,
    budget: _ReadBudget,
) -> _Merged:
    """Merge one term at a time; keep surviving products on failure.

    Each product/term batch is fetched and validated in full before the first
    row is merged, so a late validation error in that batch cannot publish rows
    from the failed read. The budget is checked before every product/term read;
    a refusal stops all further scheduling, while every completed read keeps its
    rows. ``completed`` counts finished product/term reads, so partial failures
    are not mistaken for a total failure when rows happen to be empty.
    """
    merged = _Merged()
    for term, cql, jql in queries:
        keep_going = _collect_confluence(
            merged,
            errors,
            budget,
            targets.get("confluence"),
            term,
            cql,
            limit,
            allow_http_loopback,
        )
        if keep_going:
            keep_going = _collect_jira(
                merged,
                errors,
                budget,
                targets.get("jira"),
                term,
                jql,
                limit,
                allow_http_loopback,
            )
        if keep_going:
            keep_going = _collect_bitbucket(
                merged,
                errors,
                budget,
                targets.get("bitbucket"),
                term,
                limit,
                allow_http_loopback,
            )
        if not keep_going:
            break
    return merged


def _collect_confluence(
    merged: _Merged,
    errors: dict[str, str],
    budget: _ReadBudget,
    target: ProductTarget | None,
    term: str,
    query: str,
    limit: int,
    allow_http_loopback: bool,
) -> bool:
    """Read and merge one Confluence term; return false when the budget refused."""
    if target is None:
        return True
    if not budget.take():
        return False
    try:
        batch = _confluence_batch(target, query, limit, allow_http_loopback)
    except AtlaWireError as exc:
        errors.setdefault("confluence", str(exc))
        return True
    for key, page in batch:
        _merge_page(merged.pages, key, page, term)
    merged.completed += 1
    return True


def _collect_jira(
    merged: _Merged,
    errors: dict[str, str],
    budget: _ReadBudget,
    target: ProductTarget | None,
    term: str,
    query: str,
    limit: int,
    allow_http_loopback: bool,
) -> bool:
    """Read and merge one Jira term; return false when the budget refused."""
    if target is None:
        return True
    if not budget.take():
        return False
    try:
        batch = _jira_batch(target, query, limit, allow_http_loopback)
    except AtlaWireError as exc:
        errors.setdefault("jira", str(exc))
        return True
    for key, issue in batch:
        _merge_issue(merged.issues, key, issue, term)
    merged.completed += 1
    return True


def _collect_bitbucket(
    merged: _Merged,
    errors: dict[str, str],
    budget: _ReadBudget,
    target: ProductTarget | None,
    term: str,
    limit: int,
    allow_http_loopback: bool,
) -> bool:
    """Read and merge one Bitbucket term, charging every page after the first.

    The page hook charges before the adapter asks for the next page, so a term
    whose remaining pages do not fit the budget is refused before an extra
    request exists. Its first-page rows are then discarded with the rest of that
    term's batch, exactly like any other failed read.
    """
    if target is None:
        return True
    if not budget.take():
        return False
    try:
        batch = _bitbucket_batch(
            target, term, limit, allow_http_loopback, _page_reader(budget)
        )
    except _BudgetExhausted:
        return False
    except AtlaWireError as exc:
        errors.setdefault("bitbucket", str(exc))
        return True
    for key, code in batch:
        _merge_file(merged.files, key, code, term)
    merged.completed += 1
    return True


def _page_reader(budget: _ReadBudget) -> Callable[[], None]:
    """Return a Bitbucket page hook that charges each page after the first."""
    pages = 0

    def on_page() -> None:
        nonlocal pages
        pages += 1
        if pages > 1 and not budget.take():
            raise _BudgetExhausted

    return on_page


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
    target: ProductTarget,
    query: str,
    limit: int,
    allow_http_loopback: bool,
    on_page: Callable[[], None] | None = None,
) -> list[SearchRow]:
    try:
        return search_code(
            target.base_url,
            query,
            token=target.token,
            limit=limit,
            every_page=True,
            on_page=on_page,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise _failure("Bitbucket", exc) from None


def _confluence_batch(
    target: ProductTarget, query: str, limit: int, allow_http_loopback: bool
) -> list[tuple[str, ContentRow]]:
    """Fetch one Confluence term and validate every row before any merge."""
    rows = _confluence_rows(target, query, limit, allow_http_loopback)
    return [(_page_key(row), row) for row in rows]


def _jira_batch(
    target: ProductTarget, query: str, limit: int, allow_http_loopback: bool
) -> list[tuple[str, JiraIssueRow]]:
    """Fetch one Jira term and validate every row before any merge."""
    rows = _jira_rows(target, query, limit, allow_http_loopback)
    return [(_issue_key(row), row) for row in rows]


def _bitbucket_batch(
    target: ProductTarget,
    query: str,
    limit: int,
    allow_http_loopback: bool,
    on_page: Callable[[], None] | None = None,
) -> list[tuple[tuple[str, str, str], SearchRow]]:
    """Fetch one Bitbucket term and validate every row before any merge."""
    rows = _bitbucket_rows(target, query, limit, allow_http_loopback, on_page)
    return [(_file_key(row), row) for row in rows]


def _failure(product: str, exc: AtlaWireError) -> AtlaWireError:
    """Describe a stopped federated call without echoing its request details."""
    return AtlaWireError(f"{product} search failed. {exc}")


def _page_key(row: ContentRow) -> str:
    """Return the stable page key, rejecting an unusable row."""
    page_id = row["id"]
    if isinstance(page_id, bool) or page_id is None or str(page_id) == "":
        raise AtlaWireError("Confluence search returned a page without a stable ID.")
    return str(page_id)


def _merge_page(
    pages: dict[str, PageRow], key: str, row: ContentRow, term: str
) -> None:
    entry = pages.get(key)
    if entry is None:
        pages[key] = PageRow(
            id=row["id"],
            title=row["title"],
            space=row["space"],
            type=row["type"],
            url=row["url"],
            terms=[term],
        )
        return
    _merge_term(entry["terms"], term)


def _issue_key(row: JiraIssueRow) -> str:
    """Return the stable issue key, rejecting an unusable row."""
    key = row["key"]
    if not isinstance(key, str) or not key:
        raise AtlaWireError("Jira search returned an issue without a stable key.")
    return key


def _merge_issue(
    issues: dict[str, IssueRow], key: str, row: JiraIssueRow, term: str
) -> None:
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


def _file_key(row: SearchRow) -> tuple[str, str, str]:
    """Return the case-folded file key, rejecting an unusable row."""
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
    return (project.lower(), repository.lower(), path)


def _merge_file(
    files: dict[tuple[str, str, str], FileRow],
    key: tuple[str, str, str],
    row: SearchRow,
    term: str,
) -> None:
    entry = files.get(key)
    if entry is None:
        files[key] = FileRow(
            project=row["project"],
            repository=row["repository"],
            file=row["file"],
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

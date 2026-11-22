"""Read-only pull request review packet for Bitbucket Server.

The packet answers the factual part of a review: what the pull request is,
which commits it carries, which files it changes, how the validated server diff
looks, which Jira ticket it names, where the browser views are, and which
heuristic signals the changed Java/Kotlin code raises.

Nothing here reads a local repository, starts a process, writes a file, or
follows a URL found in a response. Bitbucket and Jira are separate products:
the Bitbucket token is used only for Bitbucket reads, and the optional Jira
base URL/token pair is used only for Jira reads.

Symbol, complexity, javadoc and red-flag checks are regex heuristics, not a
parser or compiler. They are marked as heuristic in the packet and in the
Markdown report. A detected ticket without a Jira pair is reported as
unverified rather than silently treated as absent. A declared-truncated server
diff is rejected by the adapter, but an unflagged server diff is never reported
as proven complete.
"""

import html
import re
from collections.abc import Sequence
from typing import NamedTuple, TypedDict
from urllib.parse import quote

from atlawire import bitbucket, jira
from atlawire._markdown import (
    SafeMarkdownConverter,
    convert_html,
    escape_controls,
    fenced_block,
    inline,
    one_line,
)
from atlawire.http import (
    AtlaWireError,
    normalize_base_url,
    reject_credential_echo as reject_shared_credential_echo,
)

__all__ = [
    "ADDED_SYMBOL_LIMIT",
    "BIG_METHOD_LIMIT",
    "COMMIT_LIMIT",
    "COMMIT_MESSAGE_LIMIT",
    "DEFERRED_CAPABILITIES",
    "DESCRIPTION_LIMIT",
    "DIFF_TEXT_BYTES_LIMIT",
    "FILE_LIMIT",
    "HEURISTIC_FILE_LIMIT",
    "PACKET_LIMITATIONS",
    "PACKET_PROFILE",
    "PACKET_VERSION",
    "RED_FLAG_LIMIT",
    "TICKET_DESCRIPTION_LIMIT",
    "UNDOCUMENTED_LIMIT",
    "PrReviewChecks",
    "PrReviewPacket",
    "PrReviewTicket",
    "collect_pr_review",
    "is_test_path",
    "parse_pr_link",
    "reject_credential_echo",
    "render_markdown",
]

PACKET_PROFILE = "read-only-review"
PACKET_VERSION = 2
DEFERRED_CAPABILITIES: tuple[str, ...] = ()
PACKET_LIMITATIONS = (
    "Java/Kotlin symbol, complexity, javadoc and red-flag checks are regex "
    "heuristics, not a parser or compiler.",
    "Same-name overloads are paired heuristically by kind and name.",
    "Heuristic source reads are capped at a fixed number of Java/Kotlin files.",
    "Ticket discovery scans branch, commit, title and description text and may "
    "select a key-shaped non-ticket token.",
    "Browser before/after links use the changed path; a rename can make the "
    "before link point at a path absent from the target revision.",
    "A ref without repository metadata falls back to the pull request "
    "repository for file links and heuristic source reads.",
    "An unflagged Bitbucket diff response is not proven complete.",
    "profile.partial=False means no known omission was detected in requested "
    "material; it is not a proof of snapshot or diff completeness.",
)

# Packet bounds. Rows keep their whole projected fields; only long free text and
# the rendered diff are shortened, and every shortening has an explicit flag.
COMMIT_LIMIT = 500
COMMIT_MESSAGE_LIMIT = 16_384
DESCRIPTION_LIMIT = 65_536
DIFF_TEXT_BYTES_LIMIT = 262_144
FILE_LIMIT = 1000
TICKET_DESCRIPTION_LIMIT = 2_500
HEURISTIC_FILE_LIMIT = 50
HEURISTIC_FAILURE_LIMIT = 20
FILES_NOT_ANALYZED_LIMIT = 20
RED_FLAG_LIMIT = 20
ADDED_SYMBOL_LIMIT = 20
UNDOCUMENTED_LIMIT = 10
TEST_NAME_LIMIT = 10
BIG_METHOD_LIMIT = 10

_DIFF_CONTEXT_MAX = 100
_PULL_REQUEST_ID_MAX = 2**63 - 1

# These markers say where a per-file line count came from. ``not-requested``
# and ``server-diff-missing-file`` deliberately leave the counts null instead
# of presenting an invented zero.
LINES_FROM_DIFF = "server-diff"
LINES_DIFF_NO_HUNKS = "server-diff-no-textual-hunks"
LINES_DIFF_MISSING = "server-diff-missing-file"
LINES_NOT_REQUESTED = "not-requested"

_BASE_URL_INVALID = (
    "Use an HTTPS base URL without credentials, query, or fragment."
)
_REPO_INVALID = "Expected a repository as PROJECT/slug."
_ID_INVALID = "Expected a pull request ID as a positive signed 64-bit integer."
_CONTEXT_INVALID = "The diff context must be an integer from 0 to 100."
_TOKEN_INVALID = "Missing or invalid bearer token."
_JIRA_PAIR_INVALID = "Jira base URL and token must be supplied together."

# Validation mirrors the public adapters so bad arguments fail before the
# first adapter call, including when a caller substitutes the adapter in tests.
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_PR_ID_TEXT = re.compile(r"[1-9][0-9]*")
# Mirrors atlawire.http.bearer_session; the adapter remains the transport
# authority, but a bad token must not reach it as a surprise TypeError.
_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]+")

_PR_URL = re.compile(
    r"/projects/(?P<project>[^/]+)/repos/(?P<slug>[^/]+)"
    r"/pull-requests/(?P<id>\d+)"
)
_TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9_]{1,15}-\d{1,7})\b")
# Obvious key-shaped standards are not ticket references. This corrects a
# legacy false positive (for example "UTF-8") without pretending the scan is
# authoritative.
_TICKET_DENYLIST = frozenset(
    {
        "AES-128",
        "AES-256",
        "HTTP-2",
        "ISO-8859",
        "SHA-1",
        "SHA-256",
        "SHA-512",
        "TLS-1",
        "UTF-8",
        "UTF-16",
        "UTF-32",
    }
)

_TEST_PATH = re.compile(
    r"(^|/)(src/test|src/it|test|tests)/|(?:Test|Tests|IT|Spec)\.(java|kt)$"
)
_JAVA_METHOD = re.compile(
    r"^\s{1,}(?:(?:public|protected|private|static|final|abstract|"
    r"synchronized|default|native|strictfp)\s+)*"
    r"(?:<[^>]+>\s*)?[\w.$<>\[\], ?]+\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
)
_JAVA_TYPE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|sealed|"
    r"non-sealed)\s+)*(?:class|interface|enum|record)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)"
)
_COMPLEXITY_TOKENS = re.compile(r"\b(if|for|while|case|catch)\b|&&|\|\||\?")
_CONTROL_NAMES = frozenset(
    {"if", "for", "while", "switch", "catch", "return", "throw", "new", "else"}
)
_RED_FLAGS = (
    ("printStackTrace", re.compile(r"\.printStackTrace\s*\(")),
    ("System.out.print", re.compile(r"System\.(out|err)\.print")),
    ("empty catch", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")),
    ("TODO/FIXME", re.compile(r"\b(TODO|FIXME|XXX)\b")),
    ("Thread.sleep", re.compile(r"Thread\.sleep\s*\(")),
    (
        "commented-out code",
        re.compile(r"^\s*//\s*(?:if|for|while|return|[A-Za-z_$][\w$]*\s*\()"),
    ),
)
_ADDED_SYMBOL = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|"
    r"default)\s+)*(?:class|interface|enum|record)\s+\w+"
    r"|^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|"
    r"default)\s+)+[\w.$<>\[\], ?]+\s+\w+\s*\("
)
_RENDER_UNAVAILABLE = (
    "_Rendered description conversion was unavailable; no safe fallback was "
    "available._"
)
_HEURISTIC_NOTE = (
    "These are heuristic signals from changed lines and source text, not a "
    "compiler, parser or proof of a defect."
)


class PrReviewCommit(TypedDict):
    """One projected pull request commit."""

    hash: str
    date: str | None
    author: str | None
    message: str
    message_truncated: bool


class PrReviewFileLinks(TypedDict):
    """Browser views of one changed file; empty when the side does not exist."""

    before: str
    after: str
    diff: str


class PrReviewFile(TypedDict):
    """One changed file with counts, test classification and browser links."""

    path: str
    type: str | None
    node: str | None
    added: int | None
    removed: int | None
    lines_source: str
    test: bool
    links: PrReviewFileLinks


class PrReviewLinks(TypedDict):
    """Browser views of the pull request itself."""

    overview: str
    diff: str


class PrReviewDiff(TypedDict):
    """Bounded view of the validated server diff and its completeness limits."""

    requested: bool
    context: int
    text: str | None
    text_bytes: int
    text_returned_bytes: int
    text_truncated: bool
    declared_truncation_checked: bool
    proven_complete: bool
    # File entries in the validated diff response, not changed-file rows.
    files_with_changes: int | None
    added: int | None
    removed: int | None
    # True only when every listed changed file had a matching diff entry.
    counts_complete: bool | None


class PrReviewTicket(TypedDict):
    """Optional Jira context, or a visibly unverified detected key."""

    key: str
    verified: bool
    heuristic: bool
    url: str | None
    summary: str
    status: str
    type: str
    priority: str
    assignee: str
    reporter: str
    description: str
    description_truncated: bool
    error: str | None


class PrReviewSymbol(TypedDict):
    """One heuristic Java/Kotlin type or method in a changed file."""

    file: str
    name: str
    kind: str
    status: str
    lines_before: int
    lines_after: int
    complexity: int
    javadoc: bool
    line: int


class PrReviewChecks(TypedDict):
    """Heuristic review signals; never presented as compiler or parser output."""

    files_total: int
    java_files: int
    test_files: int
    test_names: list[str]
    methods_touched: int
    methods_without_javadoc: int
    types_without_javadoc: int
    undocumented_types: list[str]
    big_methods: list[dict[str, object]]
    red_flags: list[dict[str, object]]
    added_symbols: list[str]
    description_chars: int
    commits: int
    diff_requested: bool
    symbols: list[PrReviewSymbol]
    heuristic: bool
    analysis_complete: bool | None
    analysis_limited: bool
    unavailable_files: list[dict[str, object]]
    files_not_analyzed: list[str]
    notes: list[str]


class PrReviewProfile(TypedDict):
    """Describe the packet profile and any known omitted material.

    ``partial`` is true when a known requested component was omitted,
    truncated or unavailable. False is not a proof of snapshot or diff
    completeness; see ``limitations`` and ``diff.proven_complete``.
    ``partial_reasons`` names each detected omission for the agent.
    """

    name: str
    version: int
    partial: bool
    partial_reasons: list[str]
    deferred: list[str]
    limitations: list[str]


class PrReviewPacket(TypedDict):
    """A bounded, JSON-serialisable read-only review packet."""

    repo: str
    pr_id: int
    title: str
    description: str
    description_truncated: bool
    author: str
    state: str
    from_branch: str
    to_branch: str
    from_hash: str
    to_hash: str
    created: int | None
    updated: int | None
    links: PrReviewLinks
    commits: list[PrReviewCommit]
    commits_total: int
    commits_truncated: bool
    files: list[PrReviewFile]
    files_total: int
    files_truncated: bool
    diff: PrReviewDiff
    ticket: PrReviewTicket | None
    checks: PrReviewChecks
    profile: PrReviewProfile


class _Ref(NamedTuple):
    """One pull request side: display branch, commit and content repository."""

    branch: str
    commit: str
    repository: str


class _JiraConfig(NamedTuple):
    """An explicit Jira pair; never resolved from the environment here."""

    base_url: str
    token: str


class _LineChange(NamedTuple):
    """One added or removed source line with its line number."""

    line: int
    text: str


class _FileFacts(NamedTuple):
    """Structured diff facts for one file, including changed line numbers."""

    added: int
    removed: int
    hunks: int
    textual: bool
    added_lines: tuple[_LineChange, ...]
    removed_lines: tuple[_LineChange, ...]
    source_path: str | None
    destination_path: str | None


class _Member(TypedDict):
    """One heuristic Java/Kotlin type or method declaration."""

    kind: str
    name: str
    line: int
    lines: int
    complexity: int
    javadoc: bool


class _AnalysisBundle(NamedTuple):
    """All heuristic results produced by one bounded source analysis."""

    flags: list[dict[str, object]]
    added_symbols: list[str]
    symbols: list[PrReviewSymbol]
    big: list[tuple[str, _Member]]
    undocumented_types: list[tuple[str, _Member]]
    undocumented_methods: list[_Member]
    method_count: int
    failures: list[dict[str, object]]
    not_analyzed: list[str]
    analysis_complete: bool
    notes: list[str]


def collect_pr_review(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    include_diff: bool = True,
    context: int = 2,
    allow_http_loopback: bool = False,
    jira_base_url: str | None = None,
    jira_token: str | None = None,
) -> PrReviewPacket:
    """Collect a read-only review packet for one pull request.

    ``base_url``/``token`` are the Bitbucket pair. The optional
    ``jira_base_url``/``jira_token`` pair is used only for Jira ticket reads;
    neither pair is resolved from the environment or a saved credential file.
    Supplying only one half of the Jira pair is an argument error.

    Core reads are the pull request, commits, changed files and, when
    ``include_diff`` is true, the declared-truncation-checked diff. A core read
    failure raises and returns no packet. A Jira enrichment failure is recorded
    as an unverified ticket, and a heuristic source-read failure is recorded in
    ``checks`` so a degraded packet is visible rather than silently complete.

    A detected ticket without a Jira pair remains in ``ticket`` with
    ``verified`` false. A detected ticket is never silently omitted.

    ``profile.partial`` is finalized after checks. It is true when a known
    requested component was omitted, truncated or unavailable, and
    ``profile.partial_reasons`` names each case. ``include_diff=False`` is
    treated as an intentional but partial review: the diff material that the
    full review workflow includes was deliberately omitted. False only means no
    known omission was detected; it is never a snapshot or diff completeness
    claim.
    """
    wants_diff = _require_bool(include_diff, "include_diff")
    loopback = _require_bool(allow_http_loopback, "allow_http_loopback")
    context_lines = _require_context(context)
    identifier = _require_pr_id(pr_id)
    repository = _require_repo(repo)
    bearer = _require_token(token)
    jira_config = _jira_config(jira_base_url, jira_token, loopback)
    if not isinstance(base_url, str):
        raise AtlaWireError(_BASE_URL_INVALID)
    base = normalize_base_url(base_url, allow_http_loopback=loopback)

    info, commits, changed, diff_value = _core_reads(
        base,
        repository,
        identifier,
        bearer,
        wants_diff=wants_diff,
        context=context_lines,
        loopback=loopback,
    )
    from_ref = _ref(info, "fromRef", repository)
    to_ref = _ref(info, "toRef", repository)
    ticket = _ticket_packet(
        _find_ticket(info, commits), jira_config, loopback
    )
    diff_section, by_destination, by_source = _diff_section(
        diff_value, context_lines, requested=wants_diff
    )
    packet = _build_packet(
        repository,
        identifier,
        info,
        commits,
        changed,
        diff_section,
        by_destination,
        by_source,
        from_ref,
        to_ref,
        ticket,
        base=base,
        context=context_lines,
        include_diff=wants_diff,
    )
    packet["checks"] = _checks(
        packet,
        by_destination,
        by_source,
        from_ref,
        to_ref,
        base=base,
        bearer=bearer,
        loopback=loopback,
    )
    _finalize_profile(packet)
    product_tokens = tuple(
        token
        for token in (
            bearer,
            jira_config.token if jira_config is not None else None,
        )
        if token
    )
    reject_credential_echo(packet, tokens=product_tokens)
    # Keep the local guard for entity/concatenation cases, and apply the
    # shared guard for its base64/percent spellings before returning anything.
    reject_shared_credential_echo(packet, tokens=product_tokens)
    return packet


def _core_reads(
    base: str,
    repo: str,
    pr_id: int,
    token: str,
    *,
    wants_diff: bool,
    context: int,
    loopback: bool,
) -> tuple[dict[str, object], list[object], list[object], object]:
    """Read the four required Bitbucket constituents or raise."""
    info = bitbucket.get_pull_request(
        base, repo, pr_id, token=token, allow_http_loopback=loopback
    )
    commits = bitbucket.list_pull_request_commits(
        base, repo, pr_id, token=token, allow_http_loopback=loopback
    )
    changed = bitbucket.list_pull_request_files(
        base, repo, pr_id, token=token, allow_http_loopback=loopback
    )
    diff_value: object = None
    if wants_diff:
        diff_value = bitbucket.get_pull_request_diff(
            base,
            repo,
            pr_id,
            token=token,
            context=context,
            allow_http_loopback=loopback,
        )
    return info, commits, changed, diff_value


def _build_packet(
    repo: str,
    pr_id: int,
    info: dict[str, object],
    commits: Sequence[object],
    changed: Sequence[object],
    diff_section: PrReviewDiff,
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    from_ref: _Ref,
    to_ref: _Ref,
    ticket: PrReviewTicket | None,
    *,
    base: str,
    context: int,
    include_diff: bool,
) -> PrReviewPacket:
    """Project validated reads into the bounded packet without further I/O."""
    all_file_rows = _file_rows(
        changed,
        by_destination,
        by_source,
        repo=repo,
        pr_id=pr_id,
        from_ref=from_ref,
        to_ref=to_ref,
        base=base,
        include_diff=include_diff,
    )
    if include_diff:
        diff_section["counts_complete"] = all(
            row["lines_source"] in {LINES_FROM_DIFF, LINES_DIFF_NO_HUNKS}
            for row in all_file_rows
        )
    all_commit_rows = [_commit_row(row) for row in commits]
    description, description_truncated = _bounded(
        _text(info.get("description")).strip(), DESCRIPTION_LIMIT
    )
    return PrReviewPacket(
        repo=repo,
        pr_id=pr_id,
        title=_text(info.get("title")),
        description=description,
        description_truncated=description_truncated,
        author=_author(info),
        state=_text(info.get("state")),
        from_branch=from_ref.branch,
        to_branch=to_ref.branch,
        from_hash=from_ref.commit,
        to_hash=to_ref.commit,
        created=_optional_int(info.get("createdDate")),
        updated=_optional_int(info.get("updatedDate")),
        links=_pr_links(base, repo, pr_id),
        commits=all_commit_rows[:COMMIT_LIMIT],
        commits_total=len(all_commit_rows),
        commits_truncated=len(all_commit_rows) > COMMIT_LIMIT,
        files=all_file_rows[:FILE_LIMIT],
        files_total=len(all_file_rows),
        files_truncated=len(all_file_rows) > FILE_LIMIT,
        diff=diff_section,
        ticket=ticket,
        checks=_empty_checks(
            files_total=len(all_file_rows),
            description_chars=len(description),
            commits=len(all_commit_rows),
            diff_requested=include_diff,
        ),
        profile=PrReviewProfile(
            name=PACKET_PROFILE,
            version=PACKET_VERSION,
            # Finalized after checks; an unfinalized packet is not callable
            # complete by accident.
            partial=True,
            partial_reasons=[],
            deferred=list(DEFERRED_CAPABILITIES),
            limitations=list(PACKET_LIMITATIONS),
        ),
    )


def _file_rows(
    changed: Sequence[object],
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    *,
    repo: str,
    pr_id: int,
    from_ref: _Ref,
    to_ref: _Ref,
    base: str,
    include_diff: bool,
) -> list[PrReviewFile]:
    """Project every changed-file row before the packet cap is applied."""
    return [
        _file_row(
            row,
            by_destination,
            by_source,
            include_diff=include_diff,
            repo=repo,
            pr_id=pr_id,
            from_ref=from_ref,
            to_ref=to_ref,
            base=base,
        )
        for row in changed
    ]


def _finalize_profile(packet: PrReviewPacket) -> None:
    """Set the packet status from explicit component omissions."""
    reasons = _partial_reasons(packet)
    packet["profile"]["partial"] = bool(reasons)
    packet["profile"]["partial_reasons"] = reasons


def _partial_reasons(packet: PrReviewPacket) -> list[str]:
    reasons: list[str] = []
    if packet["description_truncated"]:
        reasons.append("Author description was truncated.")
    if packet["commits_truncated"]:
        reasons.append("Commit list was truncated.")
    if any(row["message_truncated"] for row in packet["commits"]):
        reasons.append("One or more commit messages were truncated.")
    if packet["files_truncated"]:
        reasons.append("Changed-file list was truncated.")
    diff = packet["diff"]
    if not diff["requested"]:
        reasons.append(
            "Diff was not requested; diff review material was intentionally "
            "omitted."
        )
    else:
        if diff["text_truncated"]:
            reasons.append("Rendered diff text was truncated.")
        if diff["counts_complete"] is False:
            reasons.append(
                "One or more changed files had no matching diff entry; line "
                "counts are incomplete."
            )
    ticket = packet["ticket"]
    if ticket is not None:
        if not ticket["verified"]:
            reasons.append(
                f"Detected ticket {ticket['key']} is unverified: "
                f"{ticket['error'] or 'no reason recorded'}."
            )
        if ticket["description_truncated"]:
            reasons.append("Ticket description was truncated.")
    checks = packet["checks"]
    if checks["analysis_complete"] is False:
        reasons.append("Heuristic analysis is incomplete.")
    if checks["analysis_limited"] or checks["files_not_analyzed"]:
        reasons.append(
            "Heuristic analysis skipped files because the source-read cap was "
            "reached."
        )
    if checks["unavailable_files"]:
        reasons.append(
            "Heuristic source reads were unavailable for one or more files."
        )
    return reasons


def _empty_checks(
    *,
    files_total: int,
    description_chars: int,
    commits: int,
    diff_requested: bool,
) -> PrReviewChecks:
    return PrReviewChecks(
        files_total=files_total,
        java_files=0,
        test_files=0,
        test_names=[],
        methods_touched=0,
        methods_without_javadoc=0,
        types_without_javadoc=0,
        undocumented_types=[],
        big_methods=[],
        red_flags=[],
        added_symbols=[],
        description_chars=description_chars,
        commits=commits,
        diff_requested=diff_requested,
        symbols=[],
        heuristic=True,
        analysis_complete=None,
        analysis_limited=False,
        unavailable_files=[],
        files_not_analyzed=[],
        notes=[_HEURISTIC_NOTE],
    )


def _require_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise AtlaWireError(f"The {name} flag must be a boolean.")
    return value


def _require_context(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= _DIFF_CONTEXT_MAX
    ):
        raise AtlaWireError(_CONTEXT_INVALID)
    return value


def _require_pr_id(value: object) -> int:
    if isinstance(value, bool):
        raise AtlaWireError(_ID_INVALID)
    if isinstance(value, int):
        identifier = value
    elif isinstance(value, str):
        # Check length before conversion so huge digit strings cannot stall or
        # hit the interpreter's integer-string conversion limit.
        if len(value) > 19 or _PR_ID_TEXT.fullmatch(value) is None:
            raise AtlaWireError(_ID_INVALID)
        identifier = int(value)
    else:
        raise AtlaWireError(_ID_INVALID)
    if not 1 <= identifier <= _PULL_REQUEST_ID_MAX:
        raise AtlaWireError(_ID_INVALID)
    return identifier


def _require_repo(value: object) -> str:
    if not isinstance(value, str):
        raise AtlaWireError(_REPO_INVALID)
    project, separator, slug = value.partition("/")
    if (
        not separator
        or "/" in slug
        or _PROJECT_KEY.fullmatch(project) is None
        or _REPOSITORY_SLUG.fullmatch(slug) is None
        or slug in {".", ".."}
    ):
        raise AtlaWireError(_REPO_INVALID)
    return value


def _require_token(value: object) -> str:
    if not isinstance(value, str) or not value or _TOKEN.fullmatch(value) is None:
        raise AtlaWireError(_TOKEN_INVALID)
    return value


def _jira_config(
    base_url: object, token: object, allow_http_loopback: bool
) -> _JiraConfig | None:
    if base_url is None and token is None:
        return None
    if base_url is None or token is None:
        raise AtlaWireError(_JIRA_PAIR_INVALID)
    if not isinstance(base_url, str) or not isinstance(token, str):
        raise AtlaWireError(_JIRA_PAIR_INVALID)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    return _JiraConfig(base_url=base, token=_require_token(token))


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _author(info: dict[str, object]) -> str:
    author = info.get("author")
    if not isinstance(author, dict):
        return ""
    user = author.get("user")
    if not isinstance(user, dict):
        return ""
    return _text(user.get("displayName"))


def _ref(info: dict[str, object], key: str, fallback_repo: str) -> _Ref:
    ref = info.get(key)
    if not isinstance(ref, dict):
        return _Ref("", "", fallback_repo)
    repository = _ref_repository(ref, fallback_repo)
    return _Ref(
        branch=_text(ref.get("displayId")),
        commit=_text(ref.get("latestCommit")),
        repository=repository,
    )


def _ref_repository(ref: dict[str, object], fallback_repo: str) -> str:
    repository = ref.get("repository")
    if not isinstance(repository, dict):
        return fallback_repo
    project = repository.get("project")
    project_key = project.get("key") if isinstance(project, dict) else None
    slug = repository.get("slug")
    if (
        not isinstance(project_key, str)
        or _PROJECT_KEY.fullmatch(project_key) is None
        or not isinstance(slug, str)
        or _REPOSITORY_SLUG.fullmatch(slug) is None
        or slug in {".", ".."}
    ):
        return fallback_repo
    return f"{project_key}/{slug}"


def _bounded(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def _commit_row(value: object) -> PrReviewCommit:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a pull request commit row.")
    identifier = value.get("hash")
    message = value.get("message")
    date = value.get("date")
    author = value.get("author")
    if not isinstance(identifier, str) or not identifier:
        raise AtlaWireError("Invalid hash in a pull request commit row.")
    if not isinstance(message, str):
        raise AtlaWireError("Invalid message in a pull request commit row.")
    if date is not None and not isinstance(date, str):
        raise AtlaWireError("Invalid date in a pull request commit row.")
    if author is not None and not isinstance(author, str):
        raise AtlaWireError("Invalid author in a pull request commit row.")
    bounded, truncated = _bounded(message, COMMIT_MESSAGE_LIMIT)
    return PrReviewCommit(
        hash=identifier,
        date=date,
        author=author,
        message=bounded,
        message_truncated=truncated,
    )


def _file_row(
    value: object,
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    *,
    include_diff: bool,
    repo: str,
    pr_id: int,
    from_ref: _Ref,
    to_ref: _Ref,
    base: str,
) -> PrReviewFile:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a pull request file row.")
    path = value.get("path")
    change_type = value.get("type")
    node = value.get("node")
    if not isinstance(path, str) or not path:
        raise AtlaWireError("Invalid path in a pull request file row.")
    if change_type is not None and not isinstance(change_type, str):
        raise AtlaWireError("Invalid type in a pull request file row.")
    if node is not None and not isinstance(node, str):
        raise AtlaWireError("Invalid node in a pull request file row.")

    facts = by_destination.get(path)
    if facts is None:
        facts = by_source.get(path)
    if not include_diff:
        added = removed = None
        lines_source = LINES_NOT_REQUESTED
    elif facts is None:
        added = removed = None
        lines_source = LINES_DIFF_MISSING
    elif not facts.textual:
        added = removed = 0
        lines_source = LINES_DIFF_NO_HUNKS
    else:
        added = facts.added
        removed = facts.removed
        lines_source = LINES_FROM_DIFF
    before_path = (
        facts.source_path
        if facts is not None and facts.source_path
        else path
    )
    after_path = (
        facts.destination_path
        if facts is not None and facts.destination_path
        else path
    )
    return PrReviewFile(
        path=path,
        type=change_type,
        node=node,
        added=added,
        removed=removed,
        lines_source=lines_source,
        test=is_test_path(path),
        links=_file_links(
            base,
            repo,
            pr_id,
            from_ref,
            to_ref,
            before_path=before_path,
            after_path=after_path,
            exists_before=change_type != "ADD",
            exists_after=change_type != "DELETE",
        ),
    )


def _pr_links(base: str, repo: str, pr_id: int) -> PrReviewLinks:
    project, _, slug = repo.partition("/")
    prefix = (
        f"{base}/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/pull-requests/{pr_id}"
    )
    return PrReviewLinks(overview=f"{prefix}/overview", diff=f"{prefix}/diff")


def _file_links(
    base: str,
    repo: str,
    pr_id: int,
    from_ref: _Ref,
    to_ref: _Ref,
    *,
    before_path: str,
    after_path: str,
    exists_before: bool,
    exists_after: bool,
) -> PrReviewFileLinks:
    before = ""
    if exists_before and to_ref.commit:
        before = _browse_link(
            base, to_ref.repository, before_path, at=to_ref.commit
        )
    after = ""
    if exists_after and from_ref.commit:
        after = _browse_link(
            base, from_ref.repository, after_path, at=from_ref.commit
        )
    project, _, slug = repo.partition("/")
    diff = (
        f"{base}/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/pull-requests/{pr_id}/diff"
        f"#{quote(after_path, safe='/')}"
    )
    return PrReviewFileLinks(before=before, after=after, diff=diff)


def _browse_link(base: str, repo: str, path: str, *, at: str) -> str:
    project, _, slug = repo.partition("/")
    return (
        f"{base}/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/browse/{quote(path, safe='/')}"
        f"?at={quote(at, safe='')}"
    )


def _diff_section(
    value: object, context: int, *, requested: bool
) -> tuple[PrReviewDiff, dict[str, _FileFacts], dict[str, _FileFacts]]:
    if not requested:
        return (
            PrReviewDiff(
                requested=False,
                context=context,
                text=None,
                text_bytes=0,
                text_returned_bytes=0,
                text_truncated=False,
                declared_truncation_checked=False,
                proven_complete=False,
                files_with_changes=None,
                added=None,
                removed=None,
                counts_complete=None,
            ),
            {},
            {},
        )

    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket pull request diff object.")
    # The shared in-package renderer validates and renders the already fetched
    # JSON. It performs no HTTP call, so the packet still makes one diff read.
    text = bitbucket._render_pull_request_diff_text(value, context=context)
    by_destination, by_source, entries, added, removed = _diff_facts(value)
    bounded, total_bytes, returned_bytes, truncated = _bounded_diff_text(text)
    return (
        PrReviewDiff(
            requested=True,
            context=context,
            text=bounded,
            text_bytes=total_bytes,
            text_returned_bytes=returned_bytes,
            text_truncated=truncated,
            declared_truncation_checked=True,
            proven_complete=False,
            files_with_changes=entries,
            added=added if entries else None,
            removed=removed if entries else None,
            counts_complete=None,
        ),
        by_destination,
        by_source,
    )


def _diff_facts(
    value: dict[str, object],
) -> tuple[dict[str, _FileFacts], dict[str, _FileFacts], int, int, int]:
    """Count lines and keep changed line numbers after the shared renderer.

    The extractor keeps its own minimal shape checks so a changed renderer
    cannot silently turn malformed data into zero line counts.
    """
    diffs = value.get("diffs")
    if not isinstance(diffs, list):
        raise AtlaWireError("Expected a Bitbucket diffs array.")
    by_destination: dict[str, _FileFacts] = {}
    by_source: dict[str, _FileFacts] = {}
    total_added = 0
    total_removed = 0
    for entry in diffs:
        if not isinstance(entry, dict):
            raise AtlaWireError("Expected a Bitbucket diff object.")
        source = bitbucket._diff_side_path(entry, "source")
        destination = bitbucket._diff_side_path(entry, "destination")
        if source is None and destination is None:
            raise AtlaWireError("A Bitbucket diff must declare a path.")
        facts = _entry_facts(entry, source, destination)
        total_added += facts.added
        total_removed += facts.removed
        if destination is not None:
            _merge_facts(by_destination, destination, facts)
        if source is not None:
            _merge_facts(by_source, source, facts)
    return (
        by_destination,
        by_source,
        len(diffs),
        total_added,
        total_removed,
    )


def _entry_facts(
    entry: dict[str, object], source: str | None, destination: str | None
) -> _FileFacts:
    hunks = entry.get("hunks")
    if "hunks" not in entry or hunks == []:
        return _FileFacts(0, 0, 0, False, (), (), source, destination)
    if not isinstance(hunks, list):
        raise AtlaWireError("Invalid hunks in a Bitbucket diff.")
    added_lines: list[_LineChange] = []
    removed_lines: list[_LineChange] = []
    for hunk in hunks:
        hunk_added, hunk_removed = _hunk_lines(hunk)
        added_lines.extend(hunk_added)
        removed_lines.extend(hunk_removed)
    return _FileFacts(
        len(added_lines),
        len(removed_lines),
        len(hunks),
        True,
        tuple(added_lines),
        tuple(removed_lines),
        source,
        destination,
    )


def _hunk_lines(value: object) -> tuple[list[_LineChange], list[_LineChange]]:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket diff hunk object.")
    source_line = _start_line(value, "sourceLine")
    destination_line = _start_line(value, "destinationLine")
    segments = value.get("segments")
    if not isinstance(segments, list):
        raise AtlaWireError("Invalid segments in a Bitbucket diff hunk.")
    added: list[_LineChange] = []
    removed: list[_LineChange] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise AtlaWireError("Expected a Bitbucket diff segment object.")
        kind = segment.get("type")
        lines = segment.get("lines")
        if not isinstance(lines, list):
            raise AtlaWireError("Invalid lines in a Bitbucket diff segment.")
        for entry in lines:
            if not isinstance(entry, dict):
                raise AtlaWireError("Expected a Bitbucket diff line object.")
            text = entry.get("line")
            if not isinstance(text, str):
                raise AtlaWireError("Invalid text in a Bitbucket diff line.")
            if kind == "ADDED":
                added.append(_LineChange(destination_line, text))
                destination_line += 1
            elif kind == "REMOVED":
                removed.append(_LineChange(source_line, text))
                source_line += 1
            elif kind == "CONTEXT":
                source_line += 1
                destination_line += 1
            else:
                raise AtlaWireError(
                    "Unsupported type in a Bitbucket diff segment."
                )
    return added, removed


def _start_line(hunk: dict[str, object], key: str) -> int:
    value = hunk.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AtlaWireError("Invalid line range in a Bitbucket diff hunk.")
    return value


def _merge_facts(
    mapping: dict[str, _FileFacts], key: str, facts: _FileFacts
) -> None:
    previous = mapping.get(key)
    if previous is None:
        mapping[key] = facts
        return
    mapping[key] = _FileFacts(
        previous.added + facts.added,
        previous.removed + facts.removed,
        previous.hunks + facts.hunks,
        previous.textual or facts.textual,
        previous.added_lines + facts.added_lines,
        previous.removed_lines + facts.removed_lines,
        previous.source_path or facts.source_path,
        previous.destination_path or facts.destination_path,
    )


def _bounded_diff_text(text: str) -> tuple[str, int, int, bool]:
    """Shorten the view on a line boundary and report its exact byte sizes."""
    total = len(text.encode("utf-8"))
    if total <= DIFF_TEXT_BYTES_LIMIT:
        return text, total, total, False
    kept: list[str] = []
    used = 0
    for line in text.splitlines(keepends=True):
        if used + len(line.encode("utf-8")) > DIFF_TEXT_BYTES_LIMIT:
            break
        kept.append(line)
        used += len(line.encode("utf-8"))
    return "".join(kept), total, used, True


def _find_ticket(
    info: dict[str, object], commits: Sequence[object]
) -> str | None:
    """Find a key-shaped ticket from branches, commits, title or description."""
    branches = []
    for key in ("fromRef", "toRef"):
        ref = info.get(key)
        if isinstance(ref, dict):
            branches.append(_text(ref.get("displayId")))
    for source in branches:
        key = _ticket_from_text(source)
        if key:
            return key
    for commit in commits:
        if isinstance(commit, dict):
            key = _ticket_from_text(_text(commit.get("message")))
            if key:
                return key
    for source in (_text(info.get("title")), _text(info.get("description"))):
        key = _ticket_from_text(source)
        if key:
            return key
    return None


def _ticket_from_text(value: str) -> str | None:
    for match in _TICKET_RE.finditer(value):
        key = match.group(1)
        if key not in _TICKET_DENYLIST:
            return key
    return None


def _ticket_packet(
    key: str | None, config: _JiraConfig | None, loopback: bool
) -> PrReviewTicket | None:
    if key is None:
        return None
    if config is None:
        return _unverified_ticket(
            key,
            "Jira base URL and token were not supplied; ticket details were "
            "not verified.",
        )
    try:
        issue = jira.get_issue(
            config.base_url,
            key,
            token=config.token,
            allow_http_loopback=loopback,
        )
    except AtlaWireError as exc:
        return _unverified_ticket(key, _first_line(exc))
    return _verified_ticket(key, issue, config.base_url)


def _unverified_ticket(key: str, reason: str) -> PrReviewTicket:
    return PrReviewTicket(
        key=key,
        verified=False,
        heuristic=True,
        url=None,
        summary="",
        status="",
        type="",
        priority="",
        assignee="",
        reporter="",
        description="",
        description_truncated=False,
        error=reason,
    )


def _verified_ticket(
    key: str, issue: dict[str, object], base_url: str
) -> PrReviewTicket:
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        return _unverified_ticket(key, "Jira returned an issue without fields.")
    issue_key = _text(issue.get("key")) or key
    description, truncated = _ticket_description(issue, fields)
    return PrReviewTicket(
        key=issue_key,
        verified=True,
        heuristic=True,
        url=f"{base_url}/browse/{quote(issue_key, safe='')}",
        summary=_one_line_field(fields, "summary"),
        status=_named_field(fields, "status"),
        type=_named_field(fields, "issuetype"),
        priority=_named_field(fields, "priority"),
        assignee=_named_field(fields, "assignee", display_name=True),
        reporter=_named_field(fields, "reporter", display_name=True),
        description=description,
        description_truncated=truncated,
        error=None,
    )


def _one_line_field(fields: dict[str, object], key: str) -> str:
    value = fields.get(key)
    return one_line(value) if isinstance(value, str) else ""


def _named_field(
    fields: dict[str, object], key: str, *, display_name: bool = False
) -> str:
    value = fields.get(key)
    if not isinstance(value, dict):
        return ""
    name = value.get("displayName" if display_name else "name")
    return one_line(name) if isinstance(name, str) else ""


def _ticket_description(
    issue: dict[str, object], fields: dict[str, object]
) -> tuple[str, bool]:
    rendered_fields = issue.get("renderedFields")
    rendered = (
        rendered_fields.get("description")
        if isinstance(rendered_fields, dict)
        else None
    )
    if isinstance(rendered, str) and rendered.strip():
        converted = convert_html(
            rendered,
            SafeMarkdownConverter(
                escape_misc=True, heading_style="atx", bullets="-"
            ),
        )
        if converted:
            if len(converted) <= TICKET_DESCRIPTION_LIMIT:
                return converted, False
            # A blind slice can remove a closing code fence. Keep the excerpt
            # literal inside an outer fence chosen longer than any inner run.
            bounded, _ = _bounded(converted, TICKET_DESCRIPTION_LIMIT)
            return fenced_block(bounded, "text"), True
    raw = fields.get("description")
    if isinstance(raw, str) and raw.strip():
        bounded, truncated = _bounded(raw, TICKET_DESCRIPTION_LIMIT)
        return fenced_block(bounded, "text"), truncated
    if isinstance(rendered, str) and rendered.strip():
        return _RENDER_UNAVAILABLE, False
    return "", False


def _first_line(exc: BaseException) -> str:
    text = str(exc).splitlines()
    return (text[0] if text else "Ticket read failed.")[:300]


def _checks(
    packet: PrReviewPacket,
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    from_ref: _Ref,
    to_ref: _Ref,
    *,
    base: str,
    bearer: str,
    loopback: bool,
) -> PrReviewChecks:
    files = packet["files"]
    java_entries = [
        entry
        for entry in files
        if entry["path"].endswith((".java", ".kt"))
    ]
    test_entries = [entry for entry in files if entry["test"]]
    test_names = [entry["path"] for entry in test_entries][:TEST_NAME_LIMIT]
    if not packet["diff"]["requested"]:
        return _no_diff_checks(
            packet, java_entries, test_entries, test_names
        )

    reader = _FileReader(base, bearer, loopback)
    analysis_entries = [entry for entry in java_entries if not entry["test"]]
    bundle = _analysis_bundle(
        files,
        analysis_entries,
        by_destination,
        by_source,
        from_ref,
        to_ref,
        reader,
    )
    return _checks_result(
        packet, java_entries, test_entries, test_names, bundle
    )


def _analysis_bundle(
    files: Sequence[PrReviewFile],
    analysis_entries: list[PrReviewFile],
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    from_ref: _Ref,
    to_ref: _Ref,
    reader: "_FileReader",
) -> _AnalysisBundle:
    flags, added_symbols = _heuristic_signals(
        analysis_entries, by_destination, by_source
    )
    attempted: set[str] = set()
    not_analyzed: list[str] = []
    members_by_file = _member_analysis(
        analysis_entries,
        by_destination,
        by_source,
        from_ref,
        reader,
        attempted,
        not_analyzed,
    )
    symbols = _changed_symbols(
        files,
        by_destination,
        by_source,
        from_ref,
        to_ref,
        reader,
        attempted,
        not_analyzed,
    )
    big, undocumented_types, undocumented_methods, method_count = (
        _member_metrics(members_by_file)
    )
    analysis_complete = not reader.failures and not not_analyzed
    notes = [_HEURISTIC_NOTE]
    if not analysis_complete:
        notes.append(
            "Some heuristic source reads or symbol analyses were unavailable; "
            "see unavailable_files and files_not_analyzed."
        )
    return _AnalysisBundle(
        flags=flags,
        added_symbols=added_symbols,
        symbols=symbols,
        big=big,
        undocumented_types=undocumented_types,
        undocumented_methods=undocumented_methods,
        method_count=method_count,
        failures=reader.failures,
        not_analyzed=not_analyzed,
        analysis_complete=analysis_complete,
        notes=notes,
    )


def _no_diff_checks(
    packet: PrReviewPacket,
    java_entries: list[PrReviewFile],
    test_entries: list[PrReviewFile],
    test_names: list[str],
) -> PrReviewChecks:
    return PrReviewChecks(
        files_total=len(packet["files"]),
        java_files=len(java_entries),
        test_files=len(test_entries),
        test_names=test_names,
        methods_touched=0,
        methods_without_javadoc=0,
        types_without_javadoc=0,
        undocumented_types=[],
        big_methods=[],
        red_flags=[],
        added_symbols=[],
        description_chars=len(packet["description"]),
        commits=len(packet["commits"]),
        diff_requested=False,
        symbols=[],
        heuristic=True,
        analysis_complete=None,
        analysis_limited=False,
        unavailable_files=[],
        files_not_analyzed=[],
        notes=[
            _HEURISTIC_NOTE,
            "Diff was not requested; heuristic checks and symbol analysis "
            "were not evaluated.",
        ],
    )


def _heuristic_signals(
    entries: list[PrReviewFile],
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
) -> tuple[list[dict[str, object]], list[str]]:
    flags: list[dict[str, object]] = []
    added_symbols: list[str] = []
    for entry in entries:
        facts = _facts_for(entry["path"], by_destination, by_source)
        if facts is None:
            continue
        flags.extend(_red_flags(facts.added_lines, entry["path"]))
        added_symbols.extend(_added_symbols(facts.added_lines))
    return flags, added_symbols


def _member_analysis(
    entries: list[PrReviewFile],
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    from_ref: _Ref,
    reader: "_FileReader",
    attempted: set[str],
    not_analyzed: list[str],
) -> list[tuple[str, _Member]]:
    members_by_file: list[tuple[str, _Member]] = []
    for entry in entries:
        if entry["type"] == "DELETE":
            continue
        facts = _facts_for(entry["path"], by_destination, by_source)
        if facts is None or not facts.added_lines:
            continue
        after_path = facts.destination_path or entry["path"]
        if not _claim_attempt(after_path, attempted, not_analyzed):
            continue
        text = reader.text(
            from_ref.repository, after_path, from_ref.commit, "new"
        )
        if text is None:
            continue
        touched = _members_touched(
            _java_members(text),
            {line for line, _ in facts.added_lines},
        )
        for member in touched:
            members_by_file.append((after_path, member))
    return members_by_file


def _member_metrics(
    members_by_file: list[tuple[str, _Member]],
) -> tuple[
    list[tuple[str, _Member]],
    list[tuple[str, _Member]],
    list[_Member],
    int,
]:
    methods = [
        member for _, member in members_by_file if member["kind"] == "method"
    ]
    big = sorted(
        [
            (path, member)
            for path, member in members_by_file
            if member["kind"] == "method"
            and (member["lines"] > 40 or member["complexity"] > 10)
        ],
        key=lambda item: (-item[1]["lines"], -item[1]["complexity"]),
    )[:BIG_METHOD_LIMIT]
    undocumented_types = [
        (path, member)
        for path, member in members_by_file
        if member["kind"] == "type" and not member["javadoc"]
    ]
    undocumented_methods = [
        member
        for member in methods
        if not member["javadoc"] and member["lines"] > 3
    ]
    return big, undocumented_types, undocumented_methods, len(methods)


def _checks_result(
    packet: PrReviewPacket,
    java_entries: list[PrReviewFile],
    test_entries: list[PrReviewFile],
    test_names: list[str],
    bundle: _AnalysisBundle,
) -> PrReviewChecks:
    return PrReviewChecks(
        files_total=len(packet["files"]),
        java_files=len(java_entries),
        test_files=len(test_entries),
        test_names=test_names,
        methods_touched=bundle.method_count,
        methods_without_javadoc=len(bundle.undocumented_methods),
        types_without_javadoc=len(bundle.undocumented_types),
        undocumented_types=_undocumented_labels(bundle.undocumented_types),
        big_methods=_big_method_rows(bundle.big),
        red_flags=bundle.flags[:RED_FLAG_LIMIT],
        added_symbols=bundle.added_symbols[:ADDED_SYMBOL_LIMIT],
        description_chars=len(packet["description"]),
        commits=len(packet["commits"]),
        diff_requested=True,
        symbols=bundle.symbols,
        heuristic=True,
        analysis_complete=bundle.analysis_complete,
        analysis_limited=bool(bundle.not_analyzed),
        unavailable_files=bundle.failures,
        files_not_analyzed=bundle.not_analyzed,
        notes=bundle.notes,
    )


def _undocumented_labels(
    types: list[tuple[str, _Member]],
) -> list[str]:
    return [
        f"{path}:{member['line']} {member['name']}"
        for path, member in types[:UNDOCUMENTED_LIMIT]
    ]


def _big_method_rows(
    big: list[tuple[str, _Member]],
) -> list[dict[str, object]]:
    return [
        {
            "file": path,
            "line": member["line"],
            "name": member["name"],
            "lines": member["lines"],
            "complexity": member["complexity"],
        }
        for path, member in big
    ]


def _facts_for(
    path: str,
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
) -> _FileFacts | None:
    facts = by_destination.get(path)
    return facts if facts is not None else by_source.get(path)


def _changed_symbols(
    files: Sequence[PrReviewFile],
    by_destination: dict[str, _FileFacts],
    by_source: dict[str, _FileFacts],
    from_ref: _Ref,
    to_ref: _Ref,
    reader: "_FileReader",
    attempted: set[str],
    not_analyzed: list[str],
) -> list[PrReviewSymbol]:
    rows: list[PrReviewSymbol] = []
    for entry in files:
        path = entry["path"]
        if not path.endswith((".java", ".kt")):
            continue
        facts = _facts_for(path, by_destination, by_source)
        if facts is None or (not facts.added_lines and not facts.removed_lines):
            continue
        before_path = facts.source_path or path
        after_path = facts.destination_path or path
        required: list[str] = []
        if entry["type"] != "ADD":
            required.append(before_path)
        if entry["type"] != "DELETE":
            required.append(after_path)
        if not all(
            _claim_attempt(item, attempted, not_analyzed)
            for item in required
        ):
            _add_unique(not_analyzed, path, FILES_NOT_ANALYZED_LIMIT)
            continue
        before: list[_Member] = []
        after: list[_Member] = []
        before_ok = entry["type"] == "ADD"
        after_ok = entry["type"] == "DELETE"
        if entry["type"] != "ADD":
            text = reader.text(
                to_ref.repository, before_path, to_ref.commit, "old"
            )
            before_ok = text is not None
            if text is not None:
                before = _java_members(text)
        if entry["type"] != "DELETE":
            text = reader.text(
                from_ref.repository, after_path, from_ref.commit, "new"
            )
            after_ok = text is not None
            if text is not None:
                after = _java_members(text)
        if not before_ok or not after_ok:
            # A failed side read cannot support an added/modified/removed
            # classification; the failure is already visible in checks.
            continue
        display_path = after_path if entry["type"] != "DELETE" else before_path
        rows.extend(
            _symbol_rows(
                display_path,
                before,
                after,
                {line for line, _ in facts.removed_lines},
                {line for line, _ in facts.added_lines},
            )
        )
    return rows


def _claim_attempt(
    path: str, attempted: set[str], not_analyzed: list[str]
) -> bool:
    """Reserve one distinct file for heuristic reading within the cap."""
    if path in attempted:
        return True
    if len(attempted) >= HEURISTIC_FILE_LIMIT:
        _add_unique(not_analyzed, path, FILES_NOT_ANALYZED_LIMIT)
        return False
    attempted.add(path)
    return True


def _symbol_rows(
    path: str,
    before: list[_Member],
    after: list[_Member],
    removed_lines: set[int],
    added_lines: set[int],
) -> list[PrReviewSymbol]:
    touched_before = _members_touched(before, removed_lines)
    touched_after = _members_touched(after, added_lines)
    used: set[int] = set()
    rows: list[PrReviewSymbol] = []
    for member in touched_after:
        prior = _take_member(touched_before, member, used)
        if prior is None:
            prior = _take_member(before, member, used)
        rows.append(
            _symbol_row(
                path,
                member,
                status="modified" if prior else "added",
                lines_before=prior["lines"] if prior else 0,
            )
        )
    for member in touched_before:
        if id(member) in used:
            continue
        rows.append(
            _symbol_row(
                path,
                member,
                status="removed",
                lines_before=member["lines"],
                lines_after=0,
            )
        )
    return rows


def _take_member(
    members: list[_Member], wanted: _Member, used: set[int]
) -> _Member | None:
    for member in members:
        if id(member) in used:
            continue
        if member["kind"] == wanted["kind"] and member["name"] == wanted["name"]:
            used.add(id(member))
            return member
    return None


def _symbol_row(
    path: str,
    member: _Member,
    *,
    status: str,
    lines_before: int,
    lines_after: int | None = None,
) -> PrReviewSymbol:
    return PrReviewSymbol(
        file=path,
        name=member["name"],
        kind=member["kind"],
        status=status,
        lines_before=lines_before,
        lines_after=member["lines"] if lines_after is None else lines_after,
        complexity=member["complexity"],
        javadoc=member["javadoc"],
        line=member["line"],
    )


def _members_touched(
    members: list[_Member], lines: set[int]
) -> list[_Member]:
    if not lines:
        return []
    touched: list[_Member] = []
    for member in members:
        start = member["line"]
        stop = start + max(member["lines"], 1) - 1
        if any(start <= line <= stop for line in lines):
            touched.append(member)
    return touched


def _add_unique(values: list[str], value: str, limit: int) -> None:
    if value not in values and len(values) < limit:
        values.append(value)


def _red_flags(
    lines: tuple[_LineChange, ...], path: str
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for change in lines:
        for name, pattern in _RED_FLAGS:
            if pattern.search(change.text):
                found.append(
                    {
                        "rule": name,
                        "line": change.line,
                        "text": change.text.strip()[:160],
                        "file": path,
                    }
                )
    return found


def _added_symbols(lines: tuple[_LineChange, ...]) -> list[str]:
    out: list[str] = []
    for change in lines:
        if _ADDED_SYMBOL.search(change.text):
            out.append(change.text.strip()[:120])
    return out


class _FileReader:
    """Read changed source files with an explicit token and a failure log."""

    def __init__(self, base: str, token: str, loopback: bool) -> None:
        self._base = base
        self._token = token
        self._loopback = loopback
        self._cache: dict[tuple[str, str, str], str | None] = {}
        self.failures: list[dict[str, object]] = []

    def text(
        self, repo: str, path: str, at: str, side: str
    ) -> str | None:
        if not at:
            self._fail(path, side, "Missing commit hash for this side.")
            return None
        key = (repo, path, at)
        if key in self._cache:
            return self._cache[key]
        try:
            text: str | None = bitbucket.get_repository_file(
                self._base,
                repo,
                path,
                token=self._token,
                at=at,
                allow_http_loopback=self._loopback,
            )
        except AtlaWireError as exc:
            self._fail(path, side, _first_line(exc))
            text = None
        self._cache[key] = text
        return text

    def _fail(self, path: str, side: str, error: str) -> None:
        if len(self.failures) >= HEURISTIC_FAILURE_LIMIT:
            return
        self.failures.append({"path": path, "side": side, "error": error})


def reject_credential_echo(
    packet: object, *, tokens: Sequence[str | None]
) -> None:
    """Refuse a completed packet that echoes a supplied credential.

    Every string value is HTML-entity-decoded and also checked in a
    concatenation of all packet strings, so a token split by entities or across
    adjacent fields cannot leak through a library caller. The error is generic
    and contains no credential.
    """
    secrets = [
        token for token in tokens if isinstance(token, str) and token
    ]
    if not secrets:
        return
    strings = list(_packet_strings(packet))
    decoded = [_decode_entities(value) for value in strings]
    joined = "".join(decoded)
    for secret in secrets:
        if any(secret in value for value in decoded) or secret in joined:
            raise AtlaWireError(
                "The completed packet would echo a credential; output was "
                "refused."
            )


def _decode_entities(value: str) -> str:
    """Decode bounded repeated entities, which can hide a token split."""
    for _ in range(3):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


def _packet_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(_packet_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_packet_strings(item))
    elif isinstance(value, tuple):
        for item in value:
            strings.extend(_packet_strings(item))
    return strings


def parse_pr_link(value: str) -> tuple[str, int]:
    """Extract ``PROJECT/slug`` and the ID from a Bitbucket pull request URL."""
    if not isinstance(value, str):
        raise AtlaWireError("Expected a Bitbucket pull request link.")
    match = _PR_URL.search(value)
    if match is None:
        raise AtlaWireError(
            "Expected /projects/KEY/repos/slug/pull-requests/N."
        )
    repo = f"{match.group('project')}/{match.group('slug')}"
    return repo, int(match.group("id"))


def is_test_path(path: str) -> bool:
    """Return whether a changed path is conventionally a test file."""
    return bool(_TEST_PATH.search(path or ""))


def _code_only(source: str) -> str:
    """Blank strings and comments while preserving line numbers."""
    out: list[str] = []
    in_block = False
    for line in source.splitlines(keepends=True):
        result: list[str] = []
        index = 0
        in_string = ""
        while index < len(line):
            char = line[index]
            pair = line[index : index + 2]
            if in_block:
                if pair == "*/":
                    in_block = False
                    result.append("  ")
                    index += 2
                    continue
                result.append(" " if char not in "\n" else char)
                index += 1
                continue
            if in_string:
                if char == "\\":
                    result.append("  ")
                    index += 2
                    continue
                if char == in_string:
                    in_string = ""
                result.append(" " if char not in "\n" else char)
                index += 1
                continue
            if pair == "//":
                tail = line[index:]
                content = tail.rstrip("\r\n")
                result.append(" " * len(content) + tail[len(content) :])
                break
            if pair == "/*":
                in_block = True
                result.append("  ")
                index += 2
                continue
            if char in "\"'":
                in_string = char
                result.append(" ")
                index += 1
                continue
            result.append(char)
            index += 1
        out.append("".join(result))
    return "".join(out)


def _has_javadoc(
    clean_lines: list[str], original_lines: list[str], index: int
) -> bool:
    """Inspect original comment text because cleaned lines blank javadoc.

    Blank and annotation lines are skipped; a comment block is recognized by
    its original closing delimiter, so line comments cannot document a member.
    """
    look = index - 1
    while look >= 0:
        clean = clean_lines[look].strip()
        original = original_lines[look].strip()
        if clean.startswith("@"):
            look -= 1
            continue
        if not clean:
            if original.endswith("*/") and not original.startswith("//"):
                return True
            look -= 1
            continue
        return False
    return False


def _java_members(source: str) -> list[_Member]:
    """Heuristically find Java/Kotlin type and method declarations."""
    clean = _code_only(source)
    lines = clean.splitlines()
    original_lines = source.splitlines()
    members: list[_Member] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        type_match = _JAVA_TYPE.match(line)
        method_match = _JAVA_METHOD.match(line)
        is_type = bool(type_match)
        is_method = (
            bool(method_match)
            and not stripped.startswith("*")
            and not is_type
        )
        if is_method:
            name = method_match.group("name") if method_match else ""
            if name in _CONTROL_NAMES:
                is_method = False
        if not (is_type or is_method):
            index += 1
            continue
        match = type_match if is_type else method_match
        name = match.group("name") if match else ""
        has_doc = _has_javadoc(lines, original_lines, index)
        end, body = _member_end(lines, index)
        members.append(
            _Member(
                kind="type" if is_type else "method",
                name=name,
                line=index + 1,
                lines=end - index + 1,
                complexity=(
                    1 + len(_COMPLEXITY_TOKENS.findall(body))
                    if not is_type
                    else 0
                ),
                javadoc=has_doc,
            )
        )
        index = index + 1 if is_type else end + 1
    return members


def _member_end(lines: list[str], start: int) -> tuple[int, str]:
    """Return the last body line and body text without running to EOF.

    A declaration with no opening brace and no semicolon is treated as its own
    line. This corrects the legacy heuristic that stretched abstract or Kotlin
    declarations to the end of the file.
    """
    body: list[str] = []
    depth = 0
    opened = False
    cursor = start
    while cursor < len(lines):
        current = lines[cursor]
        body.append(current)
        depth += current.count("{") - current.count("}")
        if "{" in current:
            opened = True
        if opened and depth <= 0:
            return cursor, "\n".join(body)
        if not opened:
            if ";" in current:
                return cursor, "\n".join(body)
            if cursor == start:
                # Allman style may put the opening brace on the next nonempty
                # line; otherwise the declaration ends on its own line.
                look = cursor + 1
                while look < len(lines) and not lines[look].strip():
                    look += 1
                if look >= len(lines) or "{" not in lines[look]:
                    return cursor, "\n".join(body)
                cursor = look
                continue
        cursor += 1
    return cursor - 1, "\n".join(body)


def _render_ticket_markdown(ticket: PrReviewTicket | None) -> list[str]:
    if ticket is None:
        return []
    key = inline(ticket["key"])
    if not ticket["verified"]:
        return [
            f"## Ticket {_code(ticket['key'])} (unverified)",
            "",
            f"_{inline(ticket['error'] or 'not verified')}_",
            "",
        ]
    lines = [f"## Ticket {_code(ticket['key'])} — {inline(ticket['summary'])}", ""]
    metadata = [
        f"- status: **{inline(ticket['status'] or 'unknown')}**",
        f"- type: {inline(ticket['type'] or 'unknown')}",
        f"- priority: {inline(ticket['priority'] or 'unknown')}",
        f"- assignee: {inline(ticket['assignee'] or 'unassigned')}",
        f"- reporter: {inline(ticket['reporter'] or 'unknown')}",
        "- detection: heuristic text scan",
    ]
    if ticket["url"]:
        metadata.append(f"- link: {ticket['url']}")
    lines.extend(metadata)
    if ticket["description"]:
        lines += ["", "### What the ticket asks", "", ticket["description"]]
        if ticket["description_truncated"]:
            lines.append(
                f"\n_Description truncated to {TICKET_DESCRIPTION_LIMIT} "
                "characters._"
            )
    lines.append("")
    return lines


def _render_files_markdown(packet: PrReviewPacket) -> list[str]:
    lines = [
        f"## Files ({packet['files_total']}, tests: "
        f"{packet['checks']['test_files']})",
        "",
    ]
    if packet["files_truncated"]:
        lines += ["_Changed-file list was truncated._", ""]
    lines += [
        "| file | type | tests | ± | before | after |",
        "|---|---|---|---|---|---|",
    ]
    for entry in packet["files"]:
        marks = (
            "—"
            if entry["added"] is None
            else f"+{entry['added']}/-{entry['removed']}"
        )
        before = _link("before", entry["links"]["before"])
        after = _link("after", entry["links"]["after"])
        lines.append(
            f"| {_table_text(entry['path'])} | "
            f"{_table_text(entry['type'] or '')} "
            f"| {'yes' if entry['test'] else 'no'} | {marks} "
            f"| {before} | {after} |"
        )
    return lines


def _render_checks_markdown(packet: PrReviewPacket) -> list[str]:
    checks = packet["checks"]
    lines = [
        "## Heuristic checks",
        "",
        f"_{inline(_HEURISTIC_NOTE)}_",
        "",
        f"- **Tests**: {checks['test_files']} test file(s), "
        f"{checks['java_files']} Java/Kotlin file(s) changed",
    ]
    if checks["test_names"]:
        lines.append(
            f"  - {', '.join(_code(path) for path in checks['test_names'])}"
        )
    if not checks["diff_requested"]:
        lines += [
            "- Diff was not requested; deeper checks were not evaluated.",
            "",
        ]
        return lines
    lines.extend(_render_heuristic_metrics(checks))
    lines.extend(_render_symbols_markdown(checks))
    lines.extend(_render_incomplete_markdown(checks))
    lines.append("")
    return lines


def _render_heuristic_metrics(checks: PrReviewChecks) -> list[str]:
    lines = [
        f"- **Javadoc heuristics**: {checks['types_without_javadoc']} type(s) "
        f"without javadoc, {checks['methods_without_javadoc']} method(s) "
        f"without javadoc ({checks['methods_touched']} method(s) touched)"
    ]
    if checks["undocumented_types"]:
        lines.append(
            "  - without description: "
            + ", ".join(_code(item) for item in checks["undocumented_types"])
        )
    if checks["big_methods"]:
        lines.append("- **Large/complex methods** (>40 lines or complexity >10):")
        for method in checks["big_methods"]:
            lines.append(
                f"  - {_code(str(method['name']))} in "
                f"{_code(str(method['file']))}:{method['line']} — "
                f"{method['lines']} lines, complexity {method['complexity']}"
            )
    else:
        lines.append("- **Large/complex methods**: none detected by the heuristic")
    if checks["red_flags"]:
        lines.append("- **Red-flag signals**:")
        for flag in checks["red_flags"]:
            lines.append(
                f"  - {_code(str(flag['rule']))} in "
                f"{_code(str(flag['file']))}:{flag['line']} — "
                f"{inline(str(flag['text']))}"
            )
    else:
        lines.append("- **Red-flag signals**: none detected")
    if checks["added_symbols"]:
        lines.append("- **Declarations in added lines**:")
        lines.extend(f"  - {_code(symbol)}" for symbol in checks["added_symbols"])
    return lines


def _render_symbols_markdown(checks: PrReviewChecks) -> list[str]:
    if not checks["symbols"]:
        return []
    lines = [
        "",
        "### Changed types and methods (heuristic)",
        "",
        "| status | symbol | file | lines before → after | "
        "complexity | javadoc |",
        "|---|---|---|---|---|---|",
    ]
    order = {"added": 0, "modified": 1, "removed": 2}
    for symbol in sorted(
        checks["symbols"],
        key=lambda item: (
            order.get(item["status"], 9),
            item["file"],
            item["line"],
        ),
    )[:40]:
        lines.append(
            f"| {symbol['status']} | {_table_text(symbol['name'])} "
            f"({symbol['kind']}) | "
            f"{_table_text(symbol['file'])}:{symbol['line']} "
            f"| {symbol['lines_before']} → {symbol['lines_after']} "
            f"| {symbol['complexity']} "
            f"| {'yes' if symbol['javadoc'] else 'no'} |"
        )
    return lines


def _render_incomplete_markdown(checks: PrReviewChecks) -> list[str]:
    if checks["analysis_complete"] is not False:
        return []
    lines = ["", "_Heuristic analysis is incomplete._"]
    for failure in checks["unavailable_files"]:
        lines.append(
            f"- unavailable: {_code(str(failure['path']))} "
            f"({failure['side']}) — {inline(str(failure['error']))}"
        )
    if checks["files_not_analyzed"]:
        lines.append(
            "- not analyzed: "
            + ", ".join(_code(path) for path in checks["files_not_analyzed"])
        )
    return lines


def _render_completeness_markdown(packet: PrReviewPacket) -> list[str]:
    reasons = packet["profile"]["partial_reasons"]
    lines = ["## Completeness", ""]
    if reasons:
        lines.append(
            "_The packet is partial: known requested material was omitted, "
            "truncated or unavailable._"
        )
        lines.extend(f"- {inline(reason)}" for reason in reasons)
    else:
        lines.append(
            "_No known omission was detected. This is not a proof of snapshot "
            "or diff completeness._"
        )
    lines.append("")
    return lines


def render_markdown(packet: PrReviewPacket) -> str:
    """Render a review packet as Markdown without inventing facts."""
    lines: list[str] = []
    lines.extend(_render_ticket_markdown(packet["ticket"]))
    lines += [
        f"# {_code(packet['repo'])}#{packet['pr_id']} — {inline(packet['title'])}",
        "",
        f"- state: **{inline(packet['state'])}**, author: "
        f"{inline(packet['author'] or 'unknown')}",
        f"- branches: {_code(packet['from_branch'])} → "
        f"{_code(packet['to_branch'])}",
        f"- hashes: {_code(packet['from_hash'][:10])} → "
        f"{_code(packet['to_hash'][:10])}",
        f"- links: [overview]({packet['links']['overview']}) · "
        f"[diff]({packet['links']['diff']})",
        "",
    ]
    lines.extend(_render_completeness_markdown(packet))
    lines += [
        "## Author's description",
        "",
        fenced_block(packet["description"] or "(empty)", "text"),
        "",
    ]
    if packet["description_truncated"]:
        lines += ["_Author description was truncated._", ""]
    lines += [
        f"## Commits ({packet['commits_total']})",
        "",
    ]
    if packet["commits_truncated"]:
        lines += ["_Commit list was truncated._", ""]
    for commit in packet["commits"]:
        truncated = " _(message truncated)_" if commit["message_truncated"] else ""
        lines.append(
            f"- {_code(commit['hash'][:10])} "
            f"{inline(commit['date'] or '')} "
            f"{inline(commit['author'] or '')} — "
            f"{inline(commit['message'])}{truncated}"
        )
    lines.extend(_render_files_markdown(packet))
    lines.append("")
    lines.extend(_render_checks_markdown(packet))
    if packet["diff"]["text"]:
        lines += [
            "<details><summary>diff</summary>",
            "",
            fenced_block(packet["diff"]["text"], "diff"),
            "",
            "</details>",
        ]
        if packet["diff"]["text_truncated"]:
            lines += [
                "",
                f"_Diff text truncated to {DIFF_TEXT_BYTES_LIMIT} bytes; "
                "line counts still come from the full validated response._",
            ]
    return escape_controls("\n".join(lines).rstrip() + "\n")


def _link(label: str, url: str) -> str:
    return f"[{label}]({url})" if url else "—"


def _code(value: str) -> str:
    """Return a GFM code span that cannot be closed by its own content."""
    text = one_line(value)
    if not text:
        return "` `"
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", text)),
        default=0,
    )
    fence = "`" * max(1, longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _table_text(value: str) -> str:
    """Return an autolink-safe literal table cell for one GFM cell.

    Untrusted text stays inside code spans, which suppress Markdown links,
    extended autolinks and inline HTML. Ordinary spaces, including repeated and
    edge spaces, are preserved; tabs, line breaks and unsafe controls are made
    visible. Pipes are split out of the spans and escaped for the table scanner,
    so backslashes in the filename are never confused with table escapes. The
    escaped pipe is rendered literally outside the code spans.
    """
    text = _table_safe_text(value)
    if not text:
        return ""
    if "|" not in text:
        return _table_code_segment(text)
    parts = text.split("|")
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index:
            rendered.append("\\|")
        if part:
            rendered.append(_table_code_segment(part))
    return "".join(rendered)


def _table_safe_text(value: str) -> str:
    """Preserve ordinary spaces while making controls and breaks visible.

    Table values are not passed through ``one_line`` because repeated and edge
    spaces are meaningful in Git paths. Tabs, line breaks, BOM and unsafe
    controls are rendered as visible escape text; bidi controls and lone
    surrogates are escaped by the shared control helper.
    """
    text = escape_controls(value)
    return (
        text.replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\ufeff", "\\ufeff")
    )


def _table_code_segment(text: str) -> str:
    """Render one already-normalized table segment without re-normalizing it.

    Code spans strip one surrounding space when both ends are spaces, so pad
    such content once; whitespace-only content is preserved as-is because the
    stripping rule excludes it. The fence is longer than every backtick run.
    """
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", text)),
        default=0,
    )
    fence = "`" * max(1, longest + 1)
    edge_needs_pad = (
        text.startswith((" ", "`")) or text.endswith((" ", "`"))
    )
    not_all_ascii_spaces = bool(text.strip(" "))
    pad = " " if not_all_ascii_spaces and edge_needs_pad else ""
    return f"{fence}{pad}{text}{pad}{fence}"

"""Read-only file-extension inventory across visible Bitbucket repositories.

Bitbucket Server 5.10 has no server-side extension search (``ext:`` is not
supported), so the inventory is a ``projects -> repositories -> /files`` walk.
The module issues only the existing read-only
[list_projects][atlawire.bitbucket.list_projects],
[list_repositories][atlawire.bitbucket.list_repositories] and
[list_repository_files][atlawire.bitbucket.list_repository_files] calls against
one supplied destination and token. It never writes, never follows response
links, and never retries a request.

Work is bounded and owned. Every listing is one page walk capped by
``max_pages``; at most ``workers`` file walks run at once, and a new walk is
submitted only when a slot frees. The all-visible request upper bound is
``max_pages * (1 + projects + repositories)``; a scoped ``project`` skips the
project listing and is bounded by ``max_pages * (1 + repositories)``. A
non-budget failure drops the pending queue, cancels queued futures, waits for
running futures, and then re-raises the original exception, so
[scan_repository_extensions][atlawire.repo_scan.scan_repository_extensions]
returns no partial rows. A page-budget failure raised by a shared Bitbucket
reader stops the walk early but keeps the rows already read:
[scan_repository_extensions_report][atlawire.repo_scan.scan_repository_extensions_report]
returns them with ``complete=False``, the number of repositories actually
walked, a known or unknown repository total, and the reader's message as
``reason``, so an exhausted default budget is visible instead of an error with
no rows.
"""

import re
from collections import deque
from concurrent.futures import (
    FIRST_COMPLETED,
    CancelledError,
    Future,
    ThreadPoolExecutor,
    wait,
)
from typing import TypedDict

from atlawire.bitbucket import (
    PageLimitError,
    list_projects,
    list_repositories,
    list_repository_files,
)
from atlawire.http import AtlaWireError, bearer_session, normalize_base_url

# Shared grammar: a Bitbucket key is not a Jira key, so the concept is imported.
from atlawire.identifiers import BITBUCKET_PROJECT_KEY as _PROJECT_KEY

_DEFAULT_WORKERS = 8
_MAX_WORKERS = 8
_DEFAULT_MAX_PAGES = 100
_SAMPLE_LIMIT = 5
_EXTENSION_UNSAFE = re.compile(r"[\s/\\\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_INVALID_EXTENSION = "The file extension must be non-empty text such as .py."
_INVALID_WORKERS = "The worker count must be between 1 and 8."
_INVALID_PAGE_LIMIT = "The page limit must be between 1 and 1000."
_INVALID_PROJECT = "Expected a Bitbucket project key or ~user project."


class ExtensionMatch(TypedDict):
    """One repository that contains at least one file with the extension."""

    project: str
    repository: str
    files: int
    matched: int
    sample: list[str]


class ExtensionScanReport(TypedDict):
    """Rows read so far plus explicit evidence about the walk's completeness.

    ``repositories_scanned`` counts file walks that finished, whether or not
    they matched. ``repositories_total`` is the enumerated repository count and
    is ``None`` when enumeration itself stopped on the page budget, so an
    unknown total is never reported as a complete denominator.
    """

    rows: list[ExtensionMatch]
    complete: bool
    repositories_scanned: int
    repositories_total: int | None
    reason: str | None


def scan_repository_extensions(
    base_url: str,
    extension: str,
    *,
    token: str,
    workers: int = _DEFAULT_WORKERS,
    max_pages: int = _DEFAULT_MAX_PAGES,
    allow_http_loopback: bool = False,
    project: str | None = None,
) -> list[ExtensionMatch]:
    """Return repositories containing files whose path ends with ``extension``.

    ``extension`` accepts ``.py``, ``py`` and any mixed-case form; it is
    normalized to one leading dot and lower case before matching, so matching
    is case-insensitive. The suffix is matched literally, not as a glob. An
    empty value, a leading double dot, whitespace, path separators and control
    characters are rejected before any request.

    ``project`` is an optional Bitbucket project key or ``~user`` project. A
    present value is validated before any request, the visible-project listing
    is not requested, and only that project's repositories are enumerated.
    ``None`` keeps the all-visible-project walk unchanged.

    Visible projects and their repositories (or only the scoped project's
    repositories) are enumerated completely first, in server order, and only
    then is one ``/files`` walk started per repository on its default branch
    (``at`` is omitted). Every path is counted in ``files``; paths ending with
    the normalized extension are counted in ``matched`` and the first five, in
    server order, are returned as ``sample``. Repositories without a match are
    omitted. Rows are sorted by ``matched`` descending and then by project and
    repository ascending, which keeps ties deterministic.

    ``workers`` must be between 1 and 8 (the BBK default is 8), and
    ``max_pages`` must be between 1 and 1000 and applies to each listing call.
    Extension, scope, worker, page, token and destination validation happen
    before enumeration. Any project, repository, file-page, budget, transport or
    validation failure propagates unchanged and returns no rows. The result
    never contains a response-link destination: request paths are rebuilt only
    from the supplied base URL and the validated ``project``/``slug`` fields.
    Use :func:`scan_repository_extensions_report` when a page-budget cut must
    publish the rows read before it instead of raising.
    """
    report = scan_repository_extensions_report(
        base_url,
        extension,
        token=token,
        workers=workers,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        project=project,
    )
    if not report["complete"]:
        raise AtlaWireError(
            report["reason"] or "The repository inventory was incomplete."
        )
    return report["rows"]


def scan_repository_extensions_report(
    base_url: str,
    extension: str,
    *,
    token: str,
    workers: int = _DEFAULT_WORKERS,
    max_pages: int = _DEFAULT_MAX_PAGES,
    allow_http_loopback: bool = False,
    project: str | None = None,
) -> ExtensionScanReport:
    """Return the extension inventory plus explicit completeness evidence.

    Validation, enumeration, and matching match
    :func:`scan_repository_extensions`, and every non-budget failure propagates
    unchanged. A page-budget failure raised by the shared Bitbucket readers is
    not propagated: enumeration or the file walks stop, the rows already read
    are returned, ``complete`` is false, and ``reason`` carries the reader's
    message. ``repositories_scanned`` counts finished file walks;
    ``repositories_total`` is the enumerated repository count, or ``None`` when
    enumeration itself stopped on the budget.
    """
    normalized = _normalize_extension(extension)
    _validate_workers(workers)
    _validate_page_limit(max_pages)
    _validate_project(project)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    _validate_token(token)
    targets, enumeration_reason = _repository_targets(
        base,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        project=project,
    )
    rows, scanned, walk_reason = _scan_targets(
        base,
        targets,
        extension=normalized,
        token=token,
        workers=workers,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )
    reason = enumeration_reason if enumeration_reason is not None else walk_reason
    return ExtensionScanReport(
        rows=rows,
        complete=reason is None,
        repositories_scanned=scanned,
        repositories_total=None if enumeration_reason is not None else len(targets),
        reason=reason,
    )


def _normalize_extension(extension: object) -> str:
    """Return one lower-case extension with exactly one leading dot."""
    if not isinstance(extension, str):
        raise AtlaWireError(_INVALID_EXTENSION)
    body = extension.removeprefix(".")
    if not body or body.startswith(".") or _EXTENSION_UNSAFE.search(body):
        raise AtlaWireError(_INVALID_EXTENSION)
    return f".{body.lower()}"


def _validate_workers(workers: object) -> None:
    """Reject a worker count outside the small, owned concurrency window."""
    if (
        not isinstance(workers, int)
        or isinstance(workers, bool)
        or not 1 <= workers <= _MAX_WORKERS
    ):
        raise AtlaWireError(_INVALID_WORKERS)


def _validate_page_limit(max_pages: object) -> None:
    """Reject a per-call page budget outside the shared Bitbucket bound."""
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError(_INVALID_PAGE_LIMIT)


def _validate_project(project: object) -> None:
    """Accept an omitted scope or one validated Bitbucket project key."""
    if project is None:
        return
    if not isinstance(project, str) or _PROJECT_KEY.fullmatch(project) is None:
        raise AtlaWireError(_INVALID_PROJECT)


def _validate_token(token: object) -> None:
    """Validate the bearer token before an empty tree can hide it.

    The shared session factory owns the token rules. Creating and closing a
    session performs no request, so an invalid token fails even when the server
    exposes no projects or repositories.
    """
    if not isinstance(token, str):
        raise AtlaWireError(
            "Missing or invalid bearer token.",
            category="credentials",
            product="bitbucket",
        )
    bearer_session(token, product="bitbucket").close()


def _repository_targets(
    base_url: str,
    *,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
    project: str | None,
) -> tuple[list[tuple[str, str]], str | None]:
    """Read every target repository before any file walk.

    A provided project is read directly through the repository adapter; the
    visible-project list is not requested, so unrelated projects cannot be
    enumerated. Without a scope every visible project is read in server order.

    A page-budget failure from the shared readers is returned as the second
    item and stops enumeration at the last completed listing, so already
    enumerated targets stay usable; every other failure propagates unchanged.
    """
    if project is not None:
        try:
            repositories = list_repositories(
                base_url,
                project,
                token=token,
                max_pages=max_pages,
                allow_http_loopback=allow_http_loopback,
            )
        except AtlaWireError as exc:
            if _is_page_limit_error(exc):
                return [], str(exc)
            raise
        return [(project, repository["slug"]) for repository in repositories], None
    targets: list[tuple[str, str]] = []
    try:
        projects = list_projects(
            base_url,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        if _is_page_limit_error(exc):
            return [], str(exc)
        raise
    for visible in projects:
        key = visible["key"]
        try:
            repositories = list_repositories(
                base_url,
                key,
                token=token,
                max_pages=max_pages,
                allow_http_loopback=allow_http_loopback,
            )
        except AtlaWireError as exc:
            if _is_page_limit_error(exc):
                return targets, str(exc)
            raise
        targets.extend((key, repository["slug"]) for repository in repositories)
    return targets, None


def _is_page_limit_error(exc: BaseException) -> bool:
    """Tell the shared readers' page-budget stop from a real failure.

    Only the dedicated page-budget stop becomes a partial report; transport,
    validation, and server errors must keep propagating so a partial inventory
    never hides them. The exception type is the contract, not its message text.
    """
    return isinstance(exc, PageLimitError)


def _scan_targets(
    base_url: str,
    targets: list[tuple[str, str]],
    *,
    extension: str,
    token: str,
    workers: int,
    max_pages: int,
    allow_http_loopback: bool,
) -> tuple[list[ExtensionMatch], int, str | None]:
    """Run bounded file walks and report rows, finished walks, and a budget cut.

    The rows are returned only when no failure was recorded; a page-budget stop
    is reported as the third item while the rows already read stay published.
    """
    if not targets:
        return [], 0, None
    pending = deque(targets)
    in_flight: dict[Future[ExtensionMatch | None], tuple[str, str]] = {}
    rows: list[ExtensionMatch] = []
    scanned = 0
    failure: BaseException | None = None
    page_limit: str | None = None
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while pending or in_flight:
            while (
                failure is None
                and page_limit is None
                and pending
                and len(in_flight) < workers
            ):
                project, repository = pending.popleft()
                future = pool.submit(
                    _scan_repository,
                    base_url,
                    project,
                    repository,
                    extension=extension,
                    token=token,
                    max_pages=max_pages,
                    allow_http_loopback=allow_http_loopback,
                )
                in_flight[future] = (project, repository)
            if not in_flight:
                break
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                in_flight.pop(future)
                try:
                    error = future.exception()
                except CancelledError:
                    # A cancelled walk is expected only after our own page-budget
                    # stop; without one it must fail instead of dropping a
                    # repository silently.
                    if page_limit is None:
                        error = AtlaWireError("The repository inventory was cancelled.")
                    else:
                        continue
                if error is not None:
                    if _is_page_limit_error(error):
                        if page_limit is None:
                            page_limit = str(error)
                            for other in in_flight:
                                other.cancel()
                            pending.clear()
                    elif failure is None:
                        failure = error
                        for other in in_flight:
                            other.cancel()
                        pending.clear()
                    continue
                scanned += 1
                row = future.result()
                if row is not None:
                    rows.append(row)
    finally:
        # Even after the first failure, wait for a blocked running worker and
        # cancel anything still queued before the original error is re-raised.
        pool.shutdown(wait=True, cancel_futures=True)
    if failure is not None:
        raise failure
    return sorted(rows, key=_sort_key), scanned, page_limit


def _scan_repository(
    base_url: str,
    project: str,
    repository: str,
    *,
    extension: str,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
) -> ExtensionMatch | None:
    """List one repository's default-branch files and project its matches."""
    paths = list_repository_files(
        base_url,
        f"{project}/{repository}",
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )
    matched = [path for path in paths if path.lower().endswith(extension)]
    if not matched:
        return None
    return ExtensionMatch(
        project=project,
        repository=repository,
        files=len(paths),
        matched=len(matched),
        sample=matched[:_SAMPLE_LIMIT],
    )


def _sort_key(row: ExtensionMatch) -> tuple[int, str, str]:
    """Sort by match count descending, then by stable repository identity."""
    return (-row["matched"], row["project"], row["repository"])

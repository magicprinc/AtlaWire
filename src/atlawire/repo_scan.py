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
project listing and is bounded by ``max_pages * (1 + repositories)``. The first
worker failure drops the pending queue, cancels queued futures, waits for
running futures, and then re-raises the original exception, so no partial rows
are returned. A page or budget failure raised by the shared Bitbucket readers is
treated the same way.
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
    list_projects,
    list_repositories,
    list_repository_files,
)
from atlawire.http import AtlaWireError, bearer_session, normalize_base_url

_DEFAULT_WORKERS = 8
_MAX_WORKERS = 8
_DEFAULT_MAX_PAGES = 100
_SAMPLE_LIMIT = 5
_EXTENSION_UNSAFE = re.compile(r"[\s/\\\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
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
    """
    normalized = _normalize_extension(extension)
    _validate_workers(workers)
    _validate_page_limit(max_pages)
    _validate_project(project)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    _validate_token(token)
    targets = _repository_targets(
        base,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        project=project,
    )
    return _scan_targets(
        base,
        targets,
        extension=normalized,
        token=token,
        workers=workers,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
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
        raise AtlaWireError("Missing or invalid bearer token.")
    bearer_session(token).close()


def _repository_targets(
    base_url: str,
    *,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
    project: str | None,
) -> list[tuple[str, str]]:
    """Read every target repository before any file walk.

    A provided project is read directly through the repository adapter; the
    visible-project list is not requested, so unrelated projects cannot be
    enumerated. Without a scope every visible project is read in server order.
    """
    if project is not None:
        repositories = list_repositories(
            base_url,
            project,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
        return [(project, repository["slug"]) for repository in repositories]
    targets: list[tuple[str, str]] = []
    projects = list_projects(
        base_url,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )
    for visible in projects:
        key = visible["key"]
        repositories = list_repositories(
            base_url,
            key,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
        targets.extend((key, repository["slug"]) for repository in repositories)
    return targets


def _scan_targets(
    base_url: str,
    targets: list[tuple[str, str]],
    *,
    extension: str,
    token: str,
    workers: int,
    max_pages: int,
    allow_http_loopback: bool,
) -> list[ExtensionMatch]:
    """Run bounded file walks and publish either all rows or one failure."""
    if not targets:
        return []
    pending = deque(targets)
    in_flight: dict[Future[ExtensionMatch | None], tuple[str, str]] = {}
    rows: list[ExtensionMatch] = []
    failure: BaseException | None = None
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while pending or in_flight:
            while failure is None and pending and len(in_flight) < workers:
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
                    # Expected only after our own cancellation; an unexpected
                    # cancellation must fail instead of dropping a repository.
                    error = AtlaWireError("The repository inventory was cancelled.")
                if error is not None:
                    if failure is None:
                        failure = error
                        for other in in_flight:
                            other.cancel()
                        pending.clear()
                    continue
                row = future.result()
                if row is not None:
                    rows.append(row)
    finally:
        # Even after the first failure, wait for a blocked running worker and
        # cancel anything still queued before the original error is re-raised.
        pool.shutdown(wait=True, cancel_futures=True)
    if failure is not None:
        raise failure
    return sorted(rows, key=_sort_key)


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

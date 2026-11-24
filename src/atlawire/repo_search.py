"""Read-only search across many Bitbucket repositories.

Two engines, one result contract:

* ``index`` -- one plugin-index search call. Fast and shallow: exact terms,
  typically the default branch only.
* ``bytes`` -- enumerate repositories, resolve each default branch, then read
  file bytes and evaluate a Python regular expression. Deeper and slower.

``fetch="archive"`` keeps the ``bytes`` engine but replaces one raw read per
file with one zip archive read per repository, then scans entries in memory.
Nothing is extracted to disk, and entry names and sizes are bounded.

The result mirrors ``grep_repository``: rows carry ``repo``/``path``/``line``/
``text``, and ``status`` is ``complete``, ``truncated`` or ``timeout``. A
listing, read or regex failure raises without returning partial rows; an
exhausted total budget after hits returns them with ``status="timeout"``.
"""

import fnmatch
import io
import re
import zipfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from time import monotonic as _monotonic
from typing import Literal, NamedTuple, TypedDict

from atlawire.bitbucket import (
    _read_repository_file_in_session,
    get_default_branch,
    get_repository_archive,
    list_repository_files,
)
from atlawire.bitbucket_search import search_code
from atlawire.http import AtlaWireError, bearer_session, normalize_base_url
from atlawire.repo_grep import (
    HIT_TEXT_LIMIT,
    _default_text_file,
    _eligible,
    _glob_filter,
    _HelperFailure,
    _HelperInvalidRegex,
    _HelperTimeout,
    _match_line_numbers,
    _path_filter,
    _pattern_text,
    _split_lines,
    _validate_pattern,
)
from atlawire.repo_scan import _repository_targets

SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 1000
SEARCH_LIMIT_DEFAULT = 200
MAX_REPOS_MIN = 1
MAX_REPOS_MAX = 100
MAX_REPOS_DEFAULT = 25
MAX_FILES_MIN = 1
MAX_FILES_MAX = 100_000
MAX_FILES_DEFAULT = 5_000
MAX_BYTES_MIN = 1
MAX_BYTES_MAX = 1024 * 1024 * 1024
MAX_BYTES_DEFAULT = 256 * 1024 * 1024
# The plugin search accepts at most 999 rows per call.
_INDEX_LIMIT_MAX = 999
TIMEOUT_DEFAULT = 120.0
REGEX_TIMEOUT_DEFAULT = 5.0
WORKERS_MAX = 8

type Engine = Literal["auto", "index", "bytes"]
type Fetch = Literal["files", "archive"]

LIMITATIONS: tuple[str, ...] = (
    (
        "The index engine sees only what the Bitbucket Search plugin indexed, "
        "typically the default branch, and matches exact terms."
    ),
    (
        "The bytes engine reads the default branch of bounded repositories; other "
        "branches are not searched."
    ),
    (
        "The archive engine rejects absolute, parent-relative or directory entries "
        "and caps each entry and the total decompressed size."
    ),
    (
        "A capped result reports truncated/complete; reaching a limit never proves "
        "that no further match exists."
    ),
)

_REGEX_META = re.compile(r"[\\^$.|?*+()\[\]{}]")
_ZIP_ABSOLUTE = re.compile(r"^(?:/|\\\\|[A-Za-z]:)")


class RepoSearchRow(TypedDict):
    """One matching line, or one index lead with no line number."""

    repo: str
    path: str
    line: int | None
    text: str
    text_truncated: bool


class RepoSearchResult(TypedDict):
    """Cross-repository search result with explicit completeness metadata."""

    rows: list[RepoSearchRow]
    engine: str
    fetch: str
    status: str
    truncated: bool
    complete: bool
    files_scanned: int
    files_eligible: int
    repositories_scanned: int
    repositories_total: int | None
    budget: dict[str, object]
    limitations: list[str]


def search_repositories(
    base_url: str,
    query: str,
    *,
    token: str,
    project: str | None = None,
    repo_glob: str | None = None,
    path_glob: str | None = None,
    engine: Engine = "auto",
    fetch: Fetch = "files",
    limit: int = SEARCH_LIMIT_DEFAULT,
    max_repos: int = MAX_REPOS_DEFAULT,
    max_files: int = MAX_FILES_DEFAULT,
    max_bytes: int = MAX_BYTES_DEFAULT,
    workers: int = 1,
    ignore_case: bool = True,
    timeout_s: float = TIMEOUT_DEFAULT,
    regex_timeout_s: float = REGEX_TIMEOUT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> RepoSearchResult:
    """Search many repositories in one bounded, read-only call.

    ``query`` is an exact plugin term for ``engine="index"`` and a Python
    regular expression for ``engine="bytes"``. ``engine="auto"`` picks
    ``index`` only when the query has no regex metacharacters and no
    ``repo_glob``/``path_glob`` is given; otherwise it uses ``bytes``.

    ``project`` scopes enumeration to one project key. ``repo_glob`` filters
    ``PROJECT/slug`` names with a case-sensitive glob. ``path_glob`` filters
    file paths; without it the document's default text suffixes apply.

    ``fetch="archive"`` is only valid with the ``bytes`` engine and downloads
    one zip archive per repository. Archive entries are bounded by
    ``max_bytes`` per entry and in total, by ``max_files`` entries, and unsafe
    names (absolute, parent-relative, backslash, directory) are rejected.

    ``workers`` above 1 runs repositories in parallel; each worker owns its own
    session, and results merge in repository order so output stays
    deterministic. Any listing, read, archive or regex failure raises without
    returning partial rows.
    """
    _validate_query(query)
    _validate_engine(engine)
    _validate_fetch(fetch)
    if engine != "bytes" and fetch == "archive":
        raise AtlaWireError("The archive fetch requires the bytes engine.")
    _validate_int(limit, SEARCH_LIMIT_MIN, SEARCH_LIMIT_MAX, "search limit")
    _validate_int(max_repos, MAX_REPOS_MIN, MAX_REPOS_MAX, "repository budget")
    _validate_int(max_files, MAX_FILES_MIN, MAX_FILES_MAX, "file budget")
    _validate_int(max_bytes, MAX_BYTES_MIN, MAX_BYTES_MAX, "byte budget")
    _validate_int(workers, 1, WORKERS_MAX, "worker count")
    _validate_int(max_pages, 1, 1000, "page limit")
    _validate_timeout(timeout_s)
    _validate_timeout(regex_timeout_s)
    if not isinstance(ignore_case, bool):
        raise AtlaWireError("The ignore-case option must be a boolean.")
    selected_glob = _glob_filter(repo_glob)
    selected_path = _path_filter(path_glob)
    pattern = _pattern_text(query)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)

    chosen = _choose_engine(engine, pattern, selected_glob, selected_path, fetch)
    if chosen == "index":
        return _index_search(
            base,
            pattern,
            token=token,
            project=project,
            repo_glob=selected_glob,
            limit=limit,
            ignore_case=ignore_case,
            allow_http_loopback=allow_http_loopback,
        )
    return _bytes_search(
        base,
        pattern,
        token=token,
        project=project,
        repo_glob=selected_glob,
        path_glob=selected_path,
        fetch=fetch,
        limit=limit,
        max_repos=max_repos,
        max_files=max_files,
        max_bytes=max_bytes,
        workers=workers,
        ignore_case=ignore_case,
        timeout_s=timeout_s,
        regex_timeout_s=regex_timeout_s,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )


def _validate_query(query: object) -> None:
    if not isinstance(query, str) or not query or not query.strip():
        raise AtlaWireError("Expected a non-empty search query.")


def _validate_engine(engine: object) -> None:
    if engine not in {"auto", "index", "bytes"}:
        raise AtlaWireError("The search engine must be auto, index, or bytes.")


def _validate_fetch(fetch: object) -> None:
    if fetch not in {"files", "archive"}:
        raise AtlaWireError("The fetch mode must be files or archive.")


def _validate_int(value: object, low: int, high: int, label: str) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not low <= value <= high
    ):
        raise AtlaWireError(f"The {label} must be between {low} and {high}.")


def _validate_timeout(value: object) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise AtlaWireError("The timeout must be a positive number.")


def _choose_engine(
    engine: str,
    query: str,
    repo_glob: str | None,
    path_glob: str | None,
    fetch: str,
) -> Literal["index", "bytes"]:
    """Resolve ``auto`` to one engine with a rule an agent can predict."""
    if engine != "auto":
        return engine  # type: ignore[return-value]
    if fetch == "archive" or repo_glob is not None or path_glob is not None:
        return "bytes"
    return "bytes" if _REGEX_META.search(query) else "index"


def _index_search(
    base: str,
    query: str,
    *,
    token: str,
    project: str | None,
    repo_glob: str | None,
    limit: int,
    ignore_case: bool,
    allow_http_loopback: bool,
) -> RepoSearchResult:
    page_limit = min(limit, _INDEX_LIMIT_MAX)
    rows = search_code(
        base,
        query,
        token=token,
        project=project,
        limit=page_limit,
        every_page=True,
        allow_http_loopback=allow_http_loopback,
    )
    result_rows: list[RepoSearchRow] = []
    repositories: set[str] = set()
    for row in rows:
        repo = f"{row['project']}/{row['repository']}"
        if repo_glob is not None and not fnmatch.fnmatchcase(repo, repo_glob):
            continue
        repositories.add(repo)
        lines = row["hits"] or [line for group in row["context"] for line in group]
        if not lines:
            result_rows.append(
                RepoSearchRow(
                    repo=repo,
                    path=row["file"],
                    line=None,
                    text="",
                    text_truncated=False,
                )
            )
            continue
        for line in lines:
            text = line["text"]
            result_rows.append(
                RepoSearchRow(
                    repo=repo,
                    path=row["file"],
                    line=line["line"],
                    text=text[:HIT_TEXT_LIMIT],
                    text_truncated=len(text) > HIT_TEXT_LIMIT,
                )
            )
    truncated = len(result_rows) >= limit
    capped = result_rows[:limit]
    return RepoSearchResult(
        rows=capped,
        engine="index",
        fetch="files",
        status="truncated" if truncated else "complete",
        truncated=truncated,
        complete=not truncated,
        files_scanned=len(
            {(row["project"], row["repository"], row["file"]) for row in rows}
        ),
        files_eligible=len(result_rows),
        repositories_scanned=len(repositories),
        repositories_total=len(repositories),
        budget={
            "repositories": len(repositories),
            "files": len(rows),
            "bytes": 0,
            "exhausted": False,
        },
        limitations=list(LIMITATIONS[:2]),
    )


def _bytes_search(
    base: str,
    pattern: str,
    *,
    token: str,
    project: str | None,
    repo_glob: str | None,
    path_glob: str | None,
    fetch: str,
    limit: int,
    max_repos: int,
    max_files: int,
    max_bytes: int,
    workers: int,
    ignore_case: bool,
    timeout_s: float,
    regex_timeout_s: float,
    max_pages: int,
    allow_http_loopback: bool,
) -> RepoSearchResult:
    _validate_pattern(
        pattern,
        ignore_case=ignore_case,
        timeout_s=min(regex_timeout_s, timeout_s),
    )
    targets, reason = _repository_targets(
        base,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        project=project,
    )
    selected = [
        target
        for target in targets
        if repo_glob is None
        or fnmatch.fnmatchcase(f"{target[0]}/{target[1]}", repo_glob)
    ]
    repositories_total = len(selected)
    repo_capped = len(selected) > max_repos
    selected = selected[:max_repos]
    deadline = _monotonic() + timeout_s

    def run(target: tuple[str, str]) -> _RepoOutcome:
        return _scan_repository(
            base,
            target,
            pattern,
            token=token,
            fetch=fetch,
            path_glob=path_glob,
            ignore_case=ignore_case,
            regex_timeout_s=regex_timeout_s,
            max_files=max_files,
            max_bytes=max_bytes,
            deadline=deadline,
            allow_http_loopback=allow_http_loopback,
        )

    outcomes = _run_targets(selected, run, workers)

    rows: list[RepoSearchRow] = []
    files_scanned = 0
    files_eligible = 0
    bytes_used = 0
    timed_out = False
    file_capped = False
    byte_capped = False
    for outcome in outcomes:
        rows.extend(outcome.rows)
        files_scanned += outcome.files_scanned
        files_eligible += outcome.files_eligible
        bytes_used += outcome.bytes_used
        timed_out = timed_out or outcome.timed_out
        file_capped = file_capped or outcome.file_capped
        byte_capped = byte_capped or outcome.byte_capped

    truncated = len(rows) > limit or repo_capped or file_capped or byte_capped
    rows = rows[:limit]
    if timed_out and not rows:
        raise AtlaWireError(
            "The repository search budget was exhausted before any match; "
            "increase timeout_s or narrow the scope."
        )
    status = "timeout" if timed_out else ("truncated" if truncated else "complete")
    limitations = list(LIMITATIONS)
    if reason is not None:
        limitations.append(f"Repository enumeration stopped: {reason}")
    return RepoSearchResult(
        rows=rows,
        engine="bytes",
        fetch=fetch,
        status=status,
        truncated=truncated,
        complete=status == "complete" and reason is None,
        files_scanned=files_scanned,
        files_eligible=files_eligible,
        repositories_scanned=len(selected),
        repositories_total=repositories_total,
        budget={
            "repositories": len(selected),
            "files": files_scanned,
            "bytes": bytes_used,
            "exhausted": timed_out or repo_capped or file_capped or byte_capped,
        },
        limitations=limitations,
    )


class _RepoOutcome(NamedTuple):
    rows: list[RepoSearchRow]
    files_scanned: int
    files_eligible: int
    bytes_used: int
    timed_out: bool
    file_capped: bool
    byte_capped: bool


def _run_targets(
    targets: Sequence[tuple[str, str]],
    run: Callable[[tuple[str, str]], _RepoOutcome],
    workers: int,
) -> list[_RepoOutcome]:
    """Run each repository once; merge in input order for determinism."""
    if workers == 1 or len(targets) <= 1:
        return [run(target) for target in targets]
    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
        futures = [pool.submit(run, target) for target in targets]
        return [future.result() for future in futures]


def _scan_repository(
    base: str,
    target: tuple[str, str],
    pattern: str,
    *,
    token: str,
    fetch: str,
    path_glob: str | None,
    ignore_case: bool,
    regex_timeout_s: float,
    max_files: int,
    max_bytes: int,
    deadline: float,
    allow_http_loopback: bool,
) -> _RepoOutcome:
    project, slug = target
    repo = f"{project}/{slug}"
    commit = _default_branch_commit(base, project, slug, token, allow_http_loopback)
    if fetch == "archive":
        return _scan_archive(
            base,
            project,
            slug,
            repo,
            commit,
            pattern,
            token=token,
            path_glob=path_glob,
            ignore_case=ignore_case,
            regex_timeout_s=regex_timeout_s,
            max_files=max_files,
            max_bytes=max_bytes,
            deadline=deadline,
            allow_http_loopback=allow_http_loopback,
        )
    return _scan_files(
        base,
        repo,
        commit,
        pattern,
        token=token,
        path_glob=path_glob,
        ignore_case=ignore_case,
        regex_timeout_s=regex_timeout_s,
        max_files=max_files,
        max_bytes=max_bytes,
        deadline=deadline,
        allow_http_loopback=allow_http_loopback,
    )


def _default_branch_commit(
    base: str, project: str, slug: str, token: str, allow_http_loopback: bool
) -> str:
    branch = get_default_branch(
        base,
        project,
        slug,
        token=token,
        allow_http_loopback=allow_http_loopback,
    )
    if branch is None:
        raise AtlaWireError("The repository has no default branch.")
    commit = branch.get("latestCommit")
    if not isinstance(commit, str) or not commit:
        raise AtlaWireError("Invalid repository default branch metadata.")
    return commit


def _scan_files(
    base: str,
    repo: str,
    commit: str,
    pattern: str,
    *,
    token: str,
    path_glob: str | None,
    ignore_case: bool,
    regex_timeout_s: float,
    max_files: int,
    max_bytes: int,
    deadline: float,
    allow_http_loopback: bool,
) -> _RepoOutcome:
    names = list_repository_files(
        base,
        repo,
        token=token,
        at=commit,
        allow_http_loopback=allow_http_loopback,
    )
    selected = _select(names, path_glob)
    eligible = len(selected)
    file_capped = eligible > max_files
    selected = selected[:max_files]
    rows: list[RepoSearchRow] = []
    scanned = 0
    bytes_used = 0
    with bearer_session(token, product="bitbucket") as session:
        for name in selected:
            if _remaining(deadline) is None:
                return _outcome(rows, scanned, eligible, bytes_used, True, file_capped)
            raw = _read_repository_file_in_session(
                session,
                base,
                repo,
                name,
                token=token,
                at=commit,
                allow_http_loopback=allow_http_loopback,
            )
            payload = raw.encode("utf-8")
            bytes_used += len(payload)
            if bytes_used > max_bytes:
                raise AtlaWireError(
                    f"The repository search exceeds the {max_bytes}-byte budget."
                )
            scanned += 1
            rows.extend(
                _match_rows(
                    repo,
                    name,
                    raw,
                    pattern,
                    ignore_case=ignore_case,
                    regex_timeout_s=regex_timeout_s,
                    remaining=_remaining(deadline),
                )
            )
            if len(rows) >= SEARCH_LIMIT_MAX:
                break
    return _outcome(rows, scanned, eligible, bytes_used, False, file_capped)


def _scan_archive(
    base: str,
    project: str,
    slug: str,
    repo: str,
    commit: str,
    pattern: str,
    *,
    token: str,
    path_glob: str | None,
    ignore_case: bool,
    regex_timeout_s: float,
    max_files: int,
    max_bytes: int,
    deadline: float,
    allow_http_loopback: bool,
) -> _RepoOutcome:
    data = get_repository_archive(
        base,
        project,
        slug,
        token=token,
        at=commit,
        format="zip",
        max_bytes=max_bytes,
        allow_http_loopback=allow_http_loopback,
    )
    rows: list[RepoSearchRow] = []
    scanned = 0
    eligible = 0
    bytes_used = 0
    file_capped = False
    byte_capped = False
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AtlaWireError("Expected a zip repository archive.") from None
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = _safe_archive_name(info.filename)
            if not _archive_selected(name, path_glob):
                continue
            eligible += 1
            if eligible > max_files:
                file_capped = True
                break
            if _remaining(deadline) is None:
                return _outcome(rows, scanned, eligible, bytes_used, True, file_capped)
            with archive.open(info) as stream:
                raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise AtlaWireError(
                    f"Archive entry exceeds the {max_bytes}-byte budget."
                )
            bytes_used += len(raw)
            if bytes_used > max_bytes:
                byte_capped = True
                break
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Binary content is out of scope for a text search.
                continue
            scanned += 1
            rows.extend(
                _match_rows(
                    repo,
                    name,
                    text,
                    pattern,
                    ignore_case=ignore_case,
                    regex_timeout_s=regex_timeout_s,
                    remaining=_remaining(deadline),
                )
            )
    return _outcome(
        rows, scanned, eligible, bytes_used, False, file_capped, byte_capped
    )


def _select(names: list[str], path_glob: str | None) -> list[str]:
    if path_glob is None:
        return [name for name in names if _default_text_file(name)]
    return [name for name in names if _eligible(name, None, path_glob)]


def _archive_selected(name: str, path_glob: str | None) -> bool:
    if path_glob is not None:
        return _eligible(name, None, path_glob)
    return _default_text_file(name)


def _safe_archive_name(name: str) -> str:
    if (
        not name
        or _ZIP_ABSOLUTE.match(name)
        or "\\" in name
        or any(segment in {"", ".", ".."} for segment in name.split("/"))
    ):
        raise AtlaWireError("The repository archive contains an unsafe entry name.")
    return name


def _match_rows(
    repo: str,
    name: str,
    text: str,
    pattern: str,
    *,
    ignore_case: bool,
    regex_timeout_s: float,
    remaining: float | None,
) -> list[RepoSearchRow]:
    if remaining is None:
        return []
    lines = _split_lines(text)
    timeout_s = min(regex_timeout_s, remaining)
    try:
        numbers = _match_line_numbers(
            text,
            pattern,
            ignore_case=ignore_case,
            limit=SEARCH_LIMIT_MAX,
            timeout_s=timeout_s,
            line_count=len(lines),
        )
    except _HelperTimeout:
        raise AtlaWireError(
            "Repository regex evaluation timed out; no result was produced."
        ) from None
    except _HelperInvalidRegex:
        raise AtlaWireError("The repository regex is invalid.") from None
    except _HelperFailure:
        raise AtlaWireError(
            "Repository regex evaluation failed; no result was produced."
        ) from None
    rows: list[RepoSearchRow] = []
    for number in numbers:
        line = lines[number - 1]
        rows.append(
            RepoSearchRow(
                repo=repo,
                path=name,
                line=number,
                text=line[:HIT_TEXT_LIMIT],
                text_truncated=len(line) > HIT_TEXT_LIMIT,
            )
        )
    return rows


def _outcome(
    rows: list[RepoSearchRow],
    scanned: int,
    eligible: int,
    bytes_used: int,
    timed_out: bool,
    file_capped: bool = False,
    byte_capped: bool = False,
) -> _RepoOutcome:
    return _RepoOutcome(
        rows=rows,
        files_scanned=scanned,
        files_eligible=eligible,
        bytes_used=bytes_used,
        timed_out=timed_out,
        file_capped=file_capped,
        byte_capped=byte_capped,
    )


def _remaining(deadline: float) -> float | None:
    remaining = deadline - _monotonic()
    return None if remaining <= 0 else remaining

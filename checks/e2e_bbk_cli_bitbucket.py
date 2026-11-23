r"""Живой протокол CLI AtlaWire против реального Bitbucket: строго только чтение.

Запуск (Windows, из любого каталога)::

    python -B D:\REPO\github\AtlaWire\checks\e2e_bbk_cli_bitbucket.py

Зачем: агенты и скрипты BBK работают с Bitbucket через транспорт AtlaWire, а
пользовательский вход -- CLI ``atlawire``. Этот протокол повторяет на реальном
сервере ровно те read-операции, которыми они пользуются, и фиксирует для каждой
точную командную строку, exit-код и наблюдаемый факт (число строк, непустоту,
флаги полноты), чтобы расхождения были видны машинно.

Безопасность:
* allowlist из фиксированных read-команд: ни одного merge/comment/approve/
  create/delete; первая часть argv проверяется по allowlist, а весь argv -- по
  запрещённым словам;
* каждый вызов -- отдельный процесс с ``shell=False``, закрытым stdin и
  таймаутом; окружение не меняется, поэтому CLI сам берёт сохранённые
  BBK-credentials;
* 401/403/429 останавливают прогон сразу, без повторов и без повторных запросов;
* токены не печатаются: активный токен читается один раз в память только для
  сравнения с выводом; ни токен, ни тело ответов не выводятся -- только счётчики
  и короткие безопасные фрагменты.

Фикстуры обнаружены этим же прогоном на ``git.platform-s.com`` (Bitbucket 5.10):
проект AB, репозиторий AB/address-book-api, merge-коммит be6563..., обычный
коммит 825966b0..., PR 192. Идентификаторы имутабельны; если сервер или права
изменятся, проверка честно упадёт в FAIL, а не подменит наблюдаемый факт.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PRODUCT = "bitbucket"
_PROJECT = "AB"
_REPO = "AB/address-book-api"
_OTHER_REPO = "AB/address-book-common-data"
_MERGE_SHA = "be65631714af82d0a610a656f8103b04d4d50fce"
_PLAIN_SHA = "825966b056fa75d896010b1fe0e8a8d96e8b4fb9"
_PR_ID = "192"
_FILE = "src/main/java/com/devinotele/addressbook/api/controller/ContactController.java"
_FILE_DIR = "src/main/java/com/devinotele/addressbook/api/controller"
_TIMEOUT_SECONDS = 180
_GREP_GLOB = "src/main/java/**/ContactController.java"
_PR_STATES = frozenset({"OPEN", "MERGED", "DECLINED"})
_SHA = re.compile(r"[0-9a-f]{40}")
# Алиасы: то же чтение под коротким именем. Проверяется, что алиас работает и
# отдаёт ровно тот же JSON, что и оригинальная команда.
_ALIAS_CASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("pr-files", _REPO, _PR_ID, "--json"),
        ("pr", _REPO, _PR_ID, "files", "--json"),
    ),
    (
        ("pr-comments", _REPO, _PR_ID, "--json"),
        ("pr", _REPO, _PR_ID, "comments", "--json"),
    ),
    (
        (
            "grep",
            _REPO,
            "class ContactController",
            "--glob",
            _GREP_GLOB,
            "--ref",
            _MERGE_SHA,
            "--json",
        ),
        (
            "grep-repo",
            _REPO,
            "class ContactController",
            "--glob",
            _GREP_GLOB,
            "--ref",
            _MERGE_SHA,
            "--json",
        ),
    ),
    (
        ("scan", "--project", _PROJECT, "--ext", ".java", "--workers", "4", "--json"),
        (
            "scan-extension",
            "--project",
            _PROJECT,
            "--ext",
            ".java",
            "--workers",
            "4",
            "--json",
        ),
    ),
)
_ALIAS_NAMES = frozenset(alias[0][0] for alias in _ALIAS_CASES)
_SCAN_PARTIAL_ARGV = [
    "scan-extension",
    "--ext",
    ".java",
    "--max-pages",
    "1",
    "--workers",
    "8",
    "--json",
]
_SCAN_FULL_ARGV = [
    "scan-extension",
    "--project",
    _PROJECT,
    "--ext",
    ".java",
    "--workers",
    "4",
    "--json",
]
_ALLOWED_FIRST = frozenset(
    {
        "projects",
        "repos",
        "files",
        "file",
        "ls",
        "blame",
        "branches",
        "commits",
        "commit",
        "commit-changes",
        "commit-diff",
        "prs",
        "pr",
        "search",
        "grep-repo",
        "last-modified",
        "scan-extension",
    }
)
_WRITE_WORDS = (
    "merge",
    "decline",
    "approve",
    "create",
    "delete",
    "update",
    "put",
    "post",
    "patch",
    "comment-new",
    "add-comment",
)
_AUTH_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429", "401 Unauthorized", "rate limit")


@dataclass(frozen=True, slots=True)
class Fact:
    """Один наблюдаемый результат одной команды."""

    command: str
    exit_code: int
    fact: str
    matched: bool


def _cli_prefix() -> list[str]:
    """Return the CLI invocation prefix: the real executable when available."""
    executable = shutil.which("atlawire")
    if executable:
        return [executable]
    return [sys.executable, "-P", "-B", "-m", "atlawire"]


_TOKEN: list[str] = []


def _token() -> str:
    """Return the active token in memory only; it is never printed or logged."""
    if not _TOKEN:
        try:
            from atlawire.credentials import load_saved_credentials

            saved = load_saved_credentials(_PRODUCT, allow_http_loopback=False)
        except Exception:  # noqa: BLE001 - fixed fact only; the detail is not shown
            print("STOP: saved BBK credentials are unusable", file=sys.stderr)
            raise SystemExit(2) from None
        _TOKEN.append(saved.token)
    return _TOKEN[0]


def _guard(argv: list[str]) -> None:
    """Refuse anything outside the fixed read-only surface before it runs."""
    if not argv:
        raise SystemExit("empty command refused")
    if argv[0] not in _ALLOWED_FIRST and argv[0] not in _ALIAS_NAMES:
        raise SystemExit(f"command outside the read allowlist refused: {argv[0]}")
    low = " ".join(argv).lower()
    for word in _WRITE_WORDS:
        if word in low:
            raise SystemExit(f"write-like token refused: {word}")


def _invoke(argv: list[str]) -> tuple[subprocess.CompletedProcess[bytes], str]:
    """Run one read-only CLI call; never follow it with a retry."""
    _guard(argv)
    started = time.monotonic()
    completed = subprocess.run(
        [*_cli_prefix(), *argv],
        check=False,
        capture_output=True,
        timeout=_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
    )
    elapsed = time.monotonic() - started
    stream = completed.stdout + completed.stderr
    for marker in _AUTH_MARKERS:
        if marker.encode() in stream:
            print(f"STOP: auth/limit response on: {' '.join(argv)}", file=sys.stderr)
            raise SystemExit(2)
    return completed, f"{elapsed:.1f}s"


def _json_value(completed: subprocess.CompletedProcess[bytes]) -> Any:
    return json.loads(completed.stdout)


def _rows(completed: subprocess.CompletedProcess[bytes]) -> list[Any]:
    value = _json_value(completed)
    if not isinstance(value, list):
        raise TypeError("expected a JSON array")
    return value


def _ok(completed: subprocess.CompletedProcess[bytes]) -> bool:
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _short(argv: list[str], limit: int = 96) -> str:
    text = "atlawire " + " ".join(argv)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _observe(
    argv: list[str],
    fact: str,
    matched: bool,
    completed: subprocess.CompletedProcess[bytes],
) -> Fact:
    return Fact(_short(argv), completed.returncode, fact, matched)


def _project_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    keys = [str(row.get("key")) for row in rows[:3] if isinstance(row, dict)]
    return _observe(
        ["projects", "--json", "--max-pages", "1"],
        f"{len(rows)} projects, первый page; первые={keys}",
        _ok(completed) and bool(rows),
        completed,
    )


def _repo_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    slugs = [str(row.get("slug")) for row in rows[:3] if isinstance(row, dict)]
    return _observe(
        ["repos", _PROJECT, "--json", "--max-pages", "1"],
        f"{len(rows)} repos; первые={slugs}",
        _ok(completed) and bool(rows),
        completed,
    )


def _files_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    paths = [row for row in rows if isinstance(row, str)]
    known = _FILE in paths
    inside = [path for path in paths if path.startswith(_FILE_DIR + "/")]
    wrong = [path for path in inside if not path.lower().endswith(".java")]
    absolute = [
        path for path in paths if path.startswith("/") or ".." in path.split("/")
    ]
    return _observe(
        ["files", _REPO, "--json"],
        f"{len(paths)} paths; известный .java файл={known}; в {_FILE_DIR}: "
        f"{len(inside)} путей, с чужим расширением={len(wrong)}; "
        f"абсолютных/..={len(absolute)}",
        _ok(completed) and known and bool(inside) and not wrong and not absolute,
        completed,
    )


def _files_page_abort(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    message = completed.stderr.decode(errors="replace").strip().splitlines()
    first = message[0] if message else ""
    return _observe(
        ["files", _OTHER_REPO, "--json", "--max-pages", "1"],
        f"exit=1 «{first}», stdout пуст -> пагинация не обрезается молча",
        completed.returncode == 1
        and not completed.stdout.strip()
        and "page limit" in first,
        completed,
    )


def _files_full(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    return _observe(
        ["files", _OTHER_REPO, "--json", "--max-pages", "2"],
        f"{len(rows)} paths после второй страницы (не 0 и не первая страница)",
        _ok(completed) and bool(rows),
        completed,
    )


def _file_text(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    data = completed.stdout
    lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    body = b"class ContactController" in data and not data.lstrip().startswith(b"{")
    return _observe(
        ["file", _REPO, _FILE, "--at", _MERGE_SHA],
        f"{len(data)} байт, {lines} строк, сырой text/plain; тело файла={body}",
        _ok(completed) and lines > 50 and body,
        completed,
    )


def _file_text_markdown(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    text = completed.stdout.decode("utf-8", errors="replace")
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    token = _token()
    leaked = bool(token) and token in text
    markdown = "](" in text and not text.lstrip().startswith("{")
    return _observe(
        ["file", _REPO, "README.md", "--at", _MERGE_SHA],
        f"exit=0, {len(completed.stdout)} байт, {lines} строк text/markdown; "
        f"markdown-ссылки={markdown}; токен в выводе={'да' if leaked else 'нет'}",
        _ok(completed) and lines > 20 and markdown and not leaked,
        completed,
    )


def _ls_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    types = sorted({str(row.get("type")) for row in rows if isinstance(row, dict)})
    return _observe(
        ["ls", _REPO, _FILE_DIR, "--at", _MERGE_SHA, "--json"],
        f"{len(rows)} детей каталога; type={types}",
        _ok(completed) and bool(rows),
        completed,
    )


def _blame_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    lines = [row.get("line") for row in rows if isinstance(row, dict)]
    contiguous = lines == list(range(1, len(lines) + 1))
    return _observe(
        ["blame", _REPO, _FILE, "--at", _MERGE_SHA, "--json"],
        f"{len(rows)} записей blame, нумерация 1..N={contiguous}; "
        "это spans сервера, не строки файла (587)",
        _ok(completed) and bool(rows) and contiguous,
        completed,
    )


def _branch_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    ids = [str(row.get("id")) for row in rows if isinstance(row, dict)]
    commits = [str(row.get("commit")) for row in rows if isinstance(row, dict)]
    default = any(row.get("default") is True for row in rows if isinstance(row, dict))
    prefixed = bool(ids) and all(item.startswith("refs/heads/") for item in ids)
    return _observe(
        ["branches", _REPO, "--json", "--max-pages", "2"],
        f"{len(rows)} веток; refs/heads у всех={prefixed}; default={default}; "
        f"merge-ref={_MERGE_SHA in commits}; plain-ref={_PLAIN_SHA in commits}",
        _ok(completed)
        and prefixed
        and default
        and _MERGE_SHA in commits
        and _PLAIN_SHA in commits,
        completed,
    )


def _commit_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    dates = [str(row.get("date")) for row in rows if isinstance(row, dict)]
    hashes = [str(row.get("hash"))[:10] for row in rows if isinstance(row, dict)]
    ordered = bool(dates) and all(
        dates[index] >= dates[index + 1] for index in range(len(dates) - 1)
    )
    return _observe(
        ["commits", _REPO, "--limit", "3", "--json"],
        f"{len(rows)} коммитов (лимит 3); даты по убыванию={ordered}; "
        f"dates={dates}; {hashes}",
        _ok(completed) and len(rows) == 3 and ordered,
        completed,
    )


def _commit_json(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    value = _json_value(completed)
    identifier = value.get("id") if isinstance(value, dict) else None
    return _observe(
        ["commit", _REPO, _MERGE_SHA, "--json"],
        f"JSON-объект commit, id={str(identifier)[:12]}",
        identifier == _MERGE_SHA,
        completed,
    )


def _commit_changes(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    paths = [str(row.get("path")) for row in rows[:2] if isinstance(row, dict)]
    return _observe(
        ["commit-changes", _REPO, _PLAIN_SHA, "--json"],
        f"{len(rows)} изменённых файлов обычного коммита; {paths}",
        _ok(completed) and bool(rows),
        completed,
    )


def _commit_changes_merge(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    rows = _rows(completed)
    return _observe(
        ["commit-changes", _REPO, _MERGE_SHA, "--json"],
        f"{len(rows)} файлов у merge-коммита (сервер отдаёт пустой changes)",
        _ok(completed) and rows == [],
        completed,
    )


def _commit_diff(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    lines = completed.stdout.count(b"\n")
    head = completed.stdout.split(b"\n", 1)[0].decode(errors="replace")[:60]
    return _observe(
        ["commit-diff", _REPO, _PLAIN_SHA],
        f"{lines} строк review-текста; «{head}»",
        _ok(completed) and lines > 10,
        completed,
    )


def _pr_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    prs = {
        str(row.get("id")): str(row.get("state"))
        for row in rows
        if isinstance(row, dict)
    }
    states = sorted(set(prs.values()))
    return _observe(
        ["prs", _REPO, "--state", "ALL", "--limit", "3", "--json"],
        f"{len(rows)} PR (лимит 3); PR {_PR_ID} state={prs.get(_PR_ID)}; "
        f"states={states}",
        _ok(completed)
        and len(rows) == 3
        and all(state in _PR_STATES for state in prs.values())
        and prs.get(_PR_ID) == "MERGED",
        completed,
    )


def _pr_show(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    value = _json_value(completed)
    identifier = value.get("id") if isinstance(value, dict) else None
    return _observe(
        ["pr", _REPO, _PR_ID, "show"],
        f"сырой JSON PR, id={identifier}",
        str(identifier) == _PR_ID,
        completed,
    )


def _pr_part(part: str):
    def check(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
        rows = _rows(completed)
        return _observe(
            ["pr", _REPO, _PR_ID, part, "--json"],
            f"{len(rows)} строк в {part}",
            _ok(completed) and bool(rows),
            completed,
        )

    return check


def _search_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    rows = _rows(completed)
    where = [
        f"{row.get('project')}/{row.get('repository')}"
        for row in rows
        if isinstance(row, dict)
    ]
    return _observe(
        ["search", "ContactController", "--repo", _REPO, "--limit", "5", "--json"],
        f"{len(rows)} строк поиска кода (scoped --repo); {sorted(set(where))}",
        _ok(completed) and bool(rows),
        completed,
    )


def _grep_json(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    value = _json_value(completed)
    if not isinstance(value, dict):
        raise TypeError("grep-repo expected a JSON object")
    hits = value.get("hits")
    complete = value.get("complete")
    truncated = value.get("truncated")
    status = value.get("status")
    message = value.get("message")
    consistent = (
        complete is True
        and truncated is False
        and status == "complete"
        and message is None
    )
    return _observe(
        [
            "grep-repo",
            _REPO,
            "class ContactController",
            "--glob",
            _GREP_GLOB,
            "--ref",
            _MERGE_SHA,
            "--json",
        ],
        f"JSON: hits={len(hits) if isinstance(hits, list) else '?'}, "
        f"complete={complete}, truncated={truncated}, status={status}, "
        f"message={message!r}",
        _ok(completed) and isinstance(hits, list) and bool(hits) and consistent,
        completed,
    )


def _last_modified_parts(
    completed: subprocess.CompletedProcess[bytes],
) -> tuple[list[str], object, object]:
    """Return decoded keys, files map and latestCommit id of one response."""
    value = _json_value(completed)
    keys = sorted(value) if isinstance(value, dict) else []
    files = value.get("files") if isinstance(value, dict) else None
    latest = value.get("latestCommit") if isinstance(value, dict) else None
    commit = latest.get("id") if isinstance(latest, dict) else None
    return keys, files, commit


def _default_branch_commit() -> str | None:
    """Read the default-branch tip through the same read-only CLI surface."""
    completed, _ = _invoke(["branches", _REPO, "--json", "--max-pages", "2"])
    if completed.returncode != 0:
        return None
    try:
        rows = _rows(completed)
    except ValueError:
        return None
    commits = [
        str(row.get("commit"))
        for row in rows
        if isinstance(row, dict) and row.get("default") is True
    ]
    if len(commits) != 1 or _SHA.fullmatch(commits[0]) is None:
        return None
    return commits[0]


def _last_modified_default(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    """Root form without --at: the library resolves the default branch itself."""
    keys, files, commit = _last_modified_parts(completed)
    resolved = _default_branch_commit()
    latest = commit[:10] if isinstance(commit, str) else "?"
    return _observe(
        ["last-modified", _REPO],
        f"без --at: keys={keys}, files={len(files) if isinstance(files, dict) else '?'}, "
        f"latestCommit={latest}…; default-ветка={resolved[:10] if resolved else '?'}…",
        _ok(completed)
        and keys == ["files", "latestCommit"]
        and isinstance(files, dict)
        and bool(files)
        and isinstance(commit, str)
        and _SHA.fullmatch(commit) is not None
        and resolved is not None
        and commit == resolved,
        completed,
    )


def _last_modified_root_at(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    keys, files, commit = _last_modified_parts(completed)
    latest = commit[:10] if isinstance(commit, str) else "?"
    return _observe(
        ["last-modified", _REPO, "--at", _MERGE_SHA],
        f"root+--at: keys={keys}, files={len(files) if isinstance(files, dict) else '?'}, "
        f"latestCommit={latest}… (запрошен {_MERGE_SHA[:10]}…)",
        _ok(completed)
        and keys == ["files", "latestCommit"]
        and isinstance(files, dict)
        and bool(files)
        and commit == _MERGE_SHA,
        completed,
    )


def _last_modified_dir(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    keys, files, commit = _last_modified_parts(completed)
    latest = commit[:10] if isinstance(commit, str) else "?"
    known = isinstance(files, dict) and any(
        isinstance(entry, dict) and entry.get("id") == commit
        for entry in files.values()
    )
    return _observe(
        ["last-modified", _REPO, _FILE_DIR, "--at", _MERGE_SHA],
        f"каталог+--at: exit 0, keys={keys}, "
        f"files={len(files) if isinstance(files, dict) else '?'}, "
        f"latestCommit={latest}… (один из commits каталога={known})",
        _ok(completed)
        and keys == ["files", "latestCommit"]
        and isinstance(files, dict)
        and bool(files)
        and isinstance(commit, str)
        and _SHA.fullmatch(commit) is not None
        and known,
        completed,
    )


def _last_modified_path(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    error = completed.stderr.decode(errors="replace").strip()
    friendly = (
        "fails when the path names a file" in error
        and "Use the repository-root form or pass a directory path." in error
        and "HTTP 500" not in error
    )
    return _observe(
        ["last-modified", _REPO, _FILE, "--at", _MERGE_SHA],
        f"exit=1, понятная ошибка без сырого HTTP 500: «{error}»",
        completed.returncode == 1
        and not completed.stdout.strip()
        and friendly,
        completed,
    )


def _json_or_none(completed: subprocess.CompletedProcess[bytes]) -> Any:
    """Return decoded JSON or None without raising on a non-JSON payload."""
    try:
        return json.loads(completed.stdout)
    except ValueError:
        return None


def _scan_rows(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    """A complete project-scoped scan is one JSON array of validated rows."""
    value = _json_or_none(completed)
    if not isinstance(value, list):
        return _observe(
            _SCAN_FULL_ARGV,
            f"полный скан без страничного обрезания ожидался массивом, "
            f"получено {type(value).__name__}: exit={completed.returncode}",
            False,
            completed,
        )
    repos: list[str] = []
    valid = bool(value)
    for row in value:
        if not isinstance(row, dict):
            valid = False
            continue
        project = row.get("project")
        repository = row.get("repository")
        files = row.get("files")
        matched = row.get("matched")
        sample = row.get("sample")
        if project != _PROJECT or not isinstance(repository, str) or not repository:
            valid = False
        if (
            isinstance(files, bool)
            or not isinstance(files, int)
            or files <= 0
            or isinstance(matched, bool)
            or not isinstance(matched, int)
            or not 0 <= matched <= files
        ):
            valid = False
        if (
            not isinstance(sample, list)
            or not sample
            or not all(
                isinstance(path, str) and path.endswith(".java") for path in sample
            )
        ):
            valid = False
        repos.append(str(repository))
    return _observe(
        _SCAN_FULL_ARGV,
        f"массив: {len(value)} репозиториев проекта {_PROJECT} с .java, "
        f"поля/sample валидны={valid}; {repos[:3]}",
        _ok(completed) and valid,
        completed,
    )


def _scan_partial(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
    """An exhausted page budget is a partial object, not an error with no rows."""
    value = _json_or_none(completed)
    if not isinstance(value, dict):
        return _observe(
            _SCAN_PARTIAL_ARGV,
            f"неполный скан ожидался объектом с complete/счётчиками, "
            f"получено {type(value).__name__}: exit={completed.returncode}",
            False,
            completed,
        )
    rows = value.get("rows")
    complete = value.get("complete")
    scanned = value.get("repositories_scanned")
    total = value.get("repositories_total")
    reason = value.get("reason")
    counts_ok = (
        isinstance(scanned, int)
        and not isinstance(scanned, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and 0 <= scanned < total
    )
    reason_ok = isinstance(reason, str) and "page limit" in reason.lower()
    row_list = rows if isinstance(rows, list) else []
    rows_ok = bool(row_list)
    for row in row_list:
        if (
            not isinstance(row, dict)
            or not str(row.get("project") or "")
            or not str(row.get("repository") or "")
        ):
            rows_ok = False
            continue
        files = row.get("files")
        matched = row.get("matched")
        sample = row.get("sample")
        if (
            isinstance(files, bool)
            or not isinstance(files, int)
            or isinstance(matched, bool)
            or not isinstance(matched, int)
            or not 0 <= matched <= files
        ):
            rows_ok = False
        if not isinstance(sample, list) or not all(
            isinstance(path, str) and path.endswith(".java") for path in sample
        ):
            rows_ok = False
    matched_ok = complete is False and counts_ok and reason_ok and rows_ok
    return _observe(
        _SCAN_PARTIAL_ARGV,
        f"объект: complete={complete}, scanned={scanned} < total={total}, "
        f"rows={len(row_list)} (валидны={rows_ok}), reason={reason!r}",
        _ok(completed) and matched_ok,
        completed,
    )


def _alias_matches(alias_argv: list[str], original_argv: list[str]) -> Any:
    """Compare one alias invocation with its canonical command on real JSON."""

    def check(completed: subprocess.CompletedProcess[bytes], _sec: str) -> Fact:
        original, _ = _invoke(original_argv)
        alias_value = _json_or_none(completed)
        original_value = _json_or_none(original)
        same = (
            completed.returncode == 0
            and original.returncode == 0
            and alias_value is not None
            and alias_value == original_value
        )
        if isinstance(alias_value, list):
            count: object = len(alias_value)
        elif isinstance(alias_value, dict) and isinstance(alias_value.get("hits"), list):
            count = len(alias_value["hits"])
        else:
            count = "?"
        return _observe(
            alias_argv,
            f"exit=0, JSON совпал с «{' '.join(original_argv)}»={same}, "
            f"элементов/хитов={count}, байт={len(completed.stdout)}",
            _ok(completed) and same,
            completed,
        )

    return check


def _last_modified_help(
    completed: subprocess.CompletedProcess[bytes], _sec: str
) -> Fact:
    """The help must describe default-branch resolution, not the old omission text."""
    text = " ".join(completed.stdout.decode(errors="replace").lower().split())
    describes = (
        "default branch" in text
        and "latest" in text
        and "commit" in text
        and "not sent" not in text
    )
    return _observe(
        ["last-modified", "--help"],
        f"exit=0, help описывает резолв default-ветки и её latest-коммита={describes}; "
        f"устаревшего «at не отправляется»={'нет' if describes else 'ЕСТЬ'}",
        completed.returncode == 0 and describes,
        completed,
    )


_ALIAS_STEPS: tuple[tuple[list[str], Any], ...] = tuple(
    (list(alias_argv), _alias_matches(list(alias_argv), list(original_argv)))
    for alias_argv, original_argv in _ALIAS_CASES
)

# (argv-заготовка для отображения, checker) в порядке прогона.
_STEPS: tuple[tuple[list[str], Any], ...] = (
    (["projects", "--json", "--max-pages", "1"], _project_rows),
    (["repos", _PROJECT, "--json", "--max-pages", "1"], _repo_rows),
    (["files", _REPO, "--json"], _files_rows),
    (["files", _OTHER_REPO, "--json", "--max-pages", "1"], _files_page_abort),
    (["files", _OTHER_REPO, "--json", "--max-pages", "2"], _files_full),
    (["file", _REPO, _FILE, "--at", _MERGE_SHA], _file_text),
    (["file", _REPO, "README.md", "--at", _MERGE_SHA], _file_text_markdown),
    (["ls", _REPO, _FILE_DIR, "--at", _MERGE_SHA, "--json"], _ls_rows),
    (["blame", _REPO, _FILE, "--at", _MERGE_SHA, "--json"], _blame_rows),
    (["branches", _REPO, "--json", "--max-pages", "2"], _branch_rows),
    (["commits", _REPO, "--limit", "3", "--json"], _commit_rows),
    (["commit", _REPO, _MERGE_SHA, "--json"], _commit_json),
    (["commit-changes", _REPO, _PLAIN_SHA, "--json"], _commit_changes),
    (["commit-changes", _REPO, _MERGE_SHA, "--json"], _commit_changes_merge),
    (["commit-diff", _REPO, _PLAIN_SHA], _commit_diff),
    (["prs", _REPO, "--state", "ALL", "--limit", "3", "--json"], _pr_rows),
    (["pr", _REPO, _PR_ID, "show"], _pr_show),
    (["pr", _REPO, _PR_ID, "files", "--json"], _pr_part("files")),
    (["pr", _REPO, _PR_ID, "comments", "--json"], _pr_part("comments")),
    (
        ["search", "ContactController", "--repo", _REPO, "--limit", "5", "--json"],
        _search_rows,
    ),
    (
        [
            "grep-repo",
            _REPO,
            "class ContactController",
            "--glob",
            _GREP_GLOB,
            "--ref",
            _MERGE_SHA,
            "--json",
        ],
        _grep_json,
    ),
    (["last-modified", _REPO], _last_modified_default),
    (["last-modified", _REPO, "--at", _MERGE_SHA], _last_modified_root_at),
    (["last-modified", _REPO, _FILE_DIR, "--at", _MERGE_SHA], _last_modified_dir),
    (["last-modified", _REPO, _FILE, "--at", _MERGE_SHA], _last_modified_path),
    (_SCAN_FULL_ARGV, _scan_rows),
    (_SCAN_PARTIAL_ARGV, _scan_partial),
    (["last-modified", "--help"], _last_modified_help),
    *_ALIAS_STEPS,
)

_LIMITS = (
    "file: нет JSON-режима (сырой текст); text/plain и text/markdown читаются, JSON-ответ трактуется как ошибка",
    "blame: один запрос без курсора; нумерация строк синтетическая 1..N, spans сервера",
    (
        "last-modified: без --at библиотека берёт latestCommit ветки по умолчанию и шлёт его как at; "
        "каталог+--at -> 200; файл в path -> понятная ошибка, сырой HTTP 500 не отдаётся"
    ),
    "commit-changes merge-коммита: пустой список при непустом diff (семантика сервера)",
    "files: при нехватке --max-pages CLI падает exit=1 и не отдаёт частичный stdout",
    (
        "scan-extension без --project: исчерпание page budget даёт объект complete=false с "
        "repositories_scanned < repositories_total, прочитанными rows и reason, а не ошибку без строк"
    ),
    (
        "алиасы pr-files/pr-comments/grep/scan отдают тот же JSON, что pr ... files/comments, "
        "grep-repo и scan-extension"
    ),
)

_UNCHECKED = (
    "attachments: нет read-команды, выдающей attachment id (attachment-get есть, ID неоткуда взять)",
    "pr diff / pr file / pr-review / my-prs / find-repos / branch / tags: вне запрошенного набора",
    "алиасы: проверено совпадение JSON с оригиналом; --catalog/--describe отдельно не сверялись",
    "многопользовательские 401/403/429 сценарии не воспроизводились (живой валидный токен)",
    "POST-чтения (api-request) и любые записи намеренно не запускались",
)


def _git_baseline() -> str:
    repo = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )
    except OSError, subprocess.SubprocessError:
        return "git baseline unavailable"
    revision = head.stdout.strip() or "unknown"
    dirty = len(status.stdout.splitlines())
    return f"repo {revision}, рабочее дерево: {dirty} изменённых/новых путей (editable src != HEAD)"


def main() -> int:
    print("=== AtlaWire CLI, Bitbucket live, READ-ONLY protocol ===")
    print(_git_baseline())
    print(
        f"target: {_REPO}; merge={_MERGE_SHA[:10]}; plain={_PLAIN_SHA[:10]}; PR={_PR_ID}"
    )
    print()
    print("| # | команда | exit | факт |")
    print("|---|---------|------|------|")
    facts: list[Fact] = []
    for index, (argv, checker) in enumerate(_STEPS, start=1):
        completed, seconds = _invoke(argv)
        fact = checker(completed, seconds)
        facts.append(fact)
        mark = "" if fact.matched else " **FAIL**"
        print(f"| {index} | `{fact.command}` | {fact.exit_code} | {fact.fact}{mark} |")
    print()
    print("=== ОГРАНИЧЕНИЯ, подтверждённые прогоном ===")
    for line in _LIMITS:
        print(f"- {line}")
    print("=== НЕ ПРОВЕРЕНО ===")
    for line in _UNCHECKED:
        print(f"- {line}")
    failed = [fact for fact in facts if not fact.matched]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)} из {len(facts)} наблюдений не совпали)")
        for fact in failed:
            print(f"  - {fact.command}: {fact.fact}")
        return 1
    print(f"RESULT: PASS ({len(facts)} наблюдений, все совпали; только чтение)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

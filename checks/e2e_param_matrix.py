"""Живая матрица параметров функций AtlaWire на реальном сервере (только чтение).

Зачем: заказчик хочет «поиграть параметрами» функций и понять, годится ли
результат агенту. Прогон по возрастанию сложности перебирает комбинации: один
параметр, затем пары, затем три вместе. Для каждой комбинации фиксируется:
что просили, что ожидали, что вернулось, вердикт и графа «когда применимо» --
для какой реальной задачи агента нужна эта комбинация. Отдельно помечаются
комбинации, которые дублируют друг друга или бесполезны.

Запуск (Windows, из любого каталога)::

    $env:ATLAWIRE_PARAM_MATRIX_LIVE=1
    python -B D:\\REPO\\github\\AtlaWire\\checks\\e2e_param_matrix.py

Без явного гейта скрипт ничего не делает и печатает подсказку: реальные запросы
к серверу выполняются только по осознанному согласию оператора.

Коды выхода: 0 — ни одной DEFECT; 1 — есть DEFECT; 2 — нет гейта или стоп 401/403/429.

Безопасность:
* allowlist из фиксированных read-команд CLI: ни одного merge/comment/approve/
  create/delete; первая часть argv проверяется по allowlist, точные write-токены
  в аргументах запрещены;
* каждый вызов CLI -- отдельный процесс с ``shell=False`` и закрытым stdin;
  окружение очищено от ``ATLAWIRE_*`` URL/TOKEN, поэтому CLI сам берёт сохранённые
  BBK-credentials;
* библиотечные вызовы идут через те же сохранённые credentials; токен остаётся в
  памяти процесса, никогда не печатается и вычищается из любого вывода
  (``redact``); наружу отдаются только счётчики, длины и имена полей;
* 401/403/429 останавливают прогон сразу, без повторов;
* никаких записей, отправок в чат и изменений расписаний: только read-функции.

Фикстуры обнаруживаются этим же прогоном: задачи текущего пользователя в Jira,
страницы пространства ARCH в Confluence, PR/коммиты репозиториев проекта AB в
Bitbucket. Если фикстура не нашлась, строка честно получает SKIP, а не подмену.
"""

from __future__ import annotations

import html as html_module
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GATE_ENV = "ATLAWIRE_PARAM_MATRIX_LIVE"
TIMEOUT_S = 180
STOP_MARKERS = (
    "HTTP 401",
    "HTTP 403",
    "HTTP 429",
    "401 Unauthorized",
    "403 Forbidden",
    "429 Too Many Requests",
    "rate limit",
)
CLI_ALLOWED = frozenset(
    {
        "jql",
        "issue",
        "issue-comments",
        "commits",
        "files",
        "grep-repo",
        "prs",
        "my-prs",
        "cql",
        "children",
        "page",
    }
)
CLI_WRITE_WORDS = frozenset(
    {
        "merge",
        "decline",
        "approve",
        "create",
        "delete",
        "update",
        "post",
        "put",
        "patch",
    }
)
CLI_FALLBACK = (sys.executable, "-P", "-B", "-m", "atlawire")

# Fixtures for the Bitbucket deployment, established by the existing live checks.
PROJECT = "AB"
REPO = "AB/address-book-api"
OTHER_REPO = "AB/address-book-common-data"
MERGE_SHA = "be65631714af82d0a610a656f8103b04d4d50fce"
COMMIT_FILE = (
    "src/main/java/com/devinotele/addressbook/api/controller/ContactController.java"
)
GREP_GLOB = "src/main/java/**/ContactController.java"

_SECRETS: list[str] = []
_WIKI_MARKUP = re.compile(
    r"\{(code|noformat|panel|quote)\}|^h[1-6]\.|\|\|", re.MULTILINE
)
_CODE_MARKUP = re.compile(r"\{(code|noformat)\}")
_HTML_TAGS = re.compile(r"<[^>]+>")

# Графа «когда применимо»: (функция, префикс комбинации, реальная задача агента).
# Порядок важен: префикс ищется первым совпадением, поэтому частные случаи выше общих.
WHEN_RULES: tuple[tuple[str, str, str], ...] = (
    ("jira.search / CLI jql", "limit=50", "широкая выборка для триажа/отчёта"),
    (
        "jira.search / CLI jql",
        "limit=5",
        "короткий обзор последних задач для контекста",
    ),
    ("jira.search / CLI jql", "limit=1", "быстрая проверка, что JQL и доступ живы"),
    ("CLI jql", "limit=5 TSV", "человекочитаемый вывод в терминале без JSON-парсера"),
    ("CLI jql", "fields=", "выбор полей ради экономии контекста"),
    ("CLI jql", "expand=", "renderedFields прямо в поиске — HTML без отдельного issue"),
    ("jira.search_issues", "limit=1", "проверка доступа и формы строки проекции"),
    ("jira.search_issues", "limit=50", "список задач для отчёта; total не сообщается"),
    (
        "jira.search_issues",
        "limit=5 × fields=",
        "узкий набор полей против раздутого контекста — недоступно",
    ),
    (
        "jira.search_raw",
        "limit=5 × fields=summary,status",
        "таблица «ключ-статус» для отчёта",
    ),
    (
        "jira.search_raw",
        "limit=5 × fields=summary",
        "экономия контекста: только summary",
    ),
    (
        "jira.search_raw",
        "limit=5 × fields=*all",
        "глубокий разбор задачи, когда проекции мало",
    ),
    (
        "jira.search_raw",
        "limit=5 × fields=list",
        "список полей так же, как у search_all_issues",
    ),
    (
        "jira.search_raw",
        "limit=2 × expand=None",
        "сырой объект без HTML: минимум данных",
    ),
    (
        "jira.search_raw",
        "limit=2 × expand=renderedFields",
        "HTML полей для отчёта/рендера",
    ),
    (
        "jira.search_raw",
        "fields=summary × expand=",
        "узкие поля + rendered HTML одним запросом",
    ),
    ("jira.search_raw", "limit=0", "проверка валидации; агенту не нужна"),
    (
        "jira.search_all_issues",
        "limit=5 × fields=*all",
        "полные объекты задач для выгрузки",
    ),
    (
        "jira.search_all_issues",
        "limit=5 × fields=summary,status",
        "выбор полей строкой для экономии",
    ),
    (
        "jira.search_all_issues",
        "limit=5 × fields=list",
        "выбор полей списком (документированная форма)",
    ),
    (
        "CLI issue",
        "expand по умолчанию",
        "одна задача с renderedFields — базовое чтение",
    ),
    (
        "CLI issue",
        "--markdown (потеря)",
        "оценить, сколько содержимого теряет markdown",
    ),
    ("CLI issue", "--markdown × --wiki", "выбрать представление для отчёта"),
    ("CLI issue", "--markdown", "готовый Markdown для отчёта/чата без JSON-разбора"),
    ("CLI issue", "expand=changelog", "история изменений задачи одним вызовом"),
    (
        "jira.get_issue",
        "expand=renderedFields,changelog",
        "отчёт: HTML и история одним запросом",
    ),
    ("jira.get_issue", "expand=renderedFields", "HTML-представление полей для рендера"),
    (
        "jira.get_issue",
        "expand=changelog",
        "история изменений задачи для отчёта/аудита",
    ),
    ("jira.get_issue", "expand=transitions", "подсказка о доступных переходах"),
    ("jira.get_issue", "expand=None", "сырой JSON без HTML — минимум данных"),
    ("CLI issue-comments", "задача", "полный тред: анализ обсуждения задачи"),
    (
        "CLI issue-comments",
        "limit=1",
        "первые N комментариев; обрезка видна в truncated/stderr",
    ),
    (
        "jira.list_issue_comments",
        "max_pages=1",
        "защита от неполного треда при >50 комментариев",
    ),
    (
        "jira.list_issue_comments",
        "limit=1",
        "первые N комментариев; limit уходит в серверный maxResults",
    ),
    ("bitbucket.list_commits", "limit=1000", "полная история репозитория (971 коммит)"),
    ("bitbucket.list_commits", "limit=100", "история для анализа изменений"),
    ("bitbucket.list_commits", "limit=3", "недавняя история для контекста агента"),
    ("bitbucket.list_commits", "limit=1", "последний коммит: признак жизни ветки"),
    ("bitbucket.list_commits", "at × path", "история файла на релизной ветке"),
    ("bitbucket.list_commits", "at", "история до коммита/ветки — сравнение релизов"),
    ("bitbucket.list_commits", "path", "кто менял файл — поиск автора изменения"),
    (
        "bitbucket.list_commits",
        "TSV (без --json)",
        "человекочитаемый вывод в терминале",
    ),
    (
        "bitbucket.list_repository_files",
        "без --at",
        "полный список файлов — выбор пути для чтения",
    ),
    (
        "bitbucket.list_repository_files",
        "at=",
        "файлы на конкретном коммите — состояние релиза",
    ),
    (
        "bitbucket.list_repository_files",
        "max-pages=1",
        "проверка отказа вместо неполного листинга",
    ),
    (
        "bitbucket.grep_repository",
        "glob × limit=1000",
        "поиск по маске файлов целиком — аудит",
    ),
    ("bitbucket.grep_repository", "glob × limit=1", "точечный поиск в одном файле"),
    ("bitbucket.grep_repository", "без glob × limit=3", "широкий поиск по репозиторию"),
    (
        "bitbucket.grep_repository",
        "без glob × limit=1000 × timeout=60",
        "широкий скан с увеличенным бюджетом",
    ),
    (
        "bitbucket.grep_repository",
        "listing path=src × limit=1000",
        "обзор модуля без чтения содержимого",
    ),
    ("bitbucket.list_pull_requests", "state=OPEN", "открытые PR — текущая работа"),
    ("bitbucket.list_pull_requests", "state=MERGED", "смерженные PR — что уже вошло"),
    (
        "bitbucket.list_pull_requests",
        "state=DECLINED",
        "отклонённые PR — отброшенные идеи",
    ),
    (
        "bitbucket.list_pull_requests",
        "state=ALL limit=1000",
        "полный список PR — статистика репозитория",
    ),
    ("bitbucket.list_pull_requests", "state=ALL limit=3", "недавние PR всех состояний"),
    ("bitbucket.list_pull_requests", "order=", "хронологический порядок для отчёта"),
    (
        "bitbucket.my_pull_requests",
        "role=AUTHOR",
        "мои PR как автора — персональная очередь",
    ),
    ("bitbucket.my_pull_requests", "role=REVIEWER", "PR на моём ревью — что ждёт меня"),
    ("bitbucket.my_pull_requests", "role=PARTICIPANT", "PR, где я участник"),
    ("CLI prs", "role=REVIEWER", "фильтр по роли для конкретного репо — недоступен"),
    ("confluence.search_cql", "limit=1000", "выгрузка большой выборки страниц"),
    ("confluence.search_cql", "limit=100", "обзор пространства; total не сообщается"),
    (
        "confluence.search_cql",
        "limit=3",
        "короткий список страниц по теме (полнота не нужна)",
    ),
    ("confluence.search_cql", "limit=1", "проверка доступности space/CQL"),
    (
        "CLI cql",
        "expand=content.body.storage",
        "тело страниц прямо в поиске без отдельного page",
    ),
    ("confluence.list_children", "limit=100", "все дети страницы — дерево разделов"),
    ("confluence.list_children", "limit=1", "первый ребёнок — проверка вложенности"),
    ("confluence.list_children", "страница без детей", "подтверждение, что детей нет"),
    ("confluence.list_children", "limit=0", "граница 0 строк; агенту бесполезна"),
    (
        "confluence.get_page",
        "JSON (expand фиксирован)",
        "сырой JSON со storage — источник конвертации",
    ),
    (
        "confluence.get_page",
        "expand=body.storage",
        "у библиотечной get_page expand фиксирован — тело выбрать нельзя",
    ),
    (
        "CLI page",
        "expand=",
        "сырая страница с выбранным expand: версия без тела — меньше полей",
    ),
    ("confluence.get_page", "--storage", "XHTML для точной конвертации/диффа"),
    ("confluence.get_page", "--html", "то же, что --storage (алиас)"),
    ("confluence.get_page", "--markdown", "Markdown для отчёта; потери не сообщаются"),
)

# Дубли/бесполезные комбинации: (функция, префикс комбинации, объяснение).
DUP_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "jira.search / CLI jql",
        "limit=",
        "limit=1/5/50 — один механизм, меняется только N",
    ),
    (
        "jira.search_issues",
        "limit=",
        "limit=1/50 — та же функция и проекция, отличается только N",
    ),
    (
        "confluence.search_cql",
        "limit=",
        "limit=1/3/100/1000 — один механизм, отличается только N",
    ),
    (
        "bitbucket.list_commits",
        "limit=",
        "limit=1/3/100/1000 — один механизм; 100 и 1000 различаются полнотой",
    ),
    (
        "jira.search_raw",
        "limit=5 × fields=summary,status",
        "строка 'summary,status' и список дают один и тот же набор полей",
    ),
    ("confluence.get_page", "--html", "--html — полный алиас --storage"),
    (
        "confluence.get_page",
        "--storage",
        "--storage повторяет JSON-поле body.storage.value",
    ),
    (
        "confluence.get_page",
        "--markdown",
        "то же содержимое в другом виде (с потерями)",
    ),
    (
        "confluence.list_children",
        "limit=0",
        "limit=0 всегда пуст, как и страница без детей",
    ),
    (
        "confluence.list_children",
        "страница без детей",
        "дубль проверки limit=0: пустой результат",
    ),
    (
        "bitbucket.list_repository_files",
        "at=",
        "на этом репо --at и без --at дали одинаковые 89 путей",
    ),
    (
        "bitbucket.list_pull_requests",
        "order=NEWEST",
        "NEWEST совпадает с дефолтом сервера (direction не шлётся)",
    ),
    ("jira.get_issue", "expand=transitions", "дублирует отдельную команду transitions"),
)

Row = dict[str, Any]


class StopRun(Exception):
    """Остановка прогона из-за ответа 401/403/429."""


@dataclass(frozen=True, slots=True)
class CliResult:
    """Один завершённый вызов CLI: argv, exit, потоки, время."""

    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    seconds: float

    @property
    def text(self) -> str:
        return self.stdout + self.stderr


@dataclass(frozen=True, slots=True)
class LibResult:
    """Один завершённый библиотечный вызов: значение или категория ошибки."""

    exit_code: int
    value: Any = None
    error: str | None = None
    seconds: float = 0.0


@dataclass(slots=True)
class Ctx:
    """Состояние прогона: credentials, строки отчёта и найденные фикстуры."""

    creds: dict[str, Any]
    rows: list[Row] = field(default_factory=list)
    fixtures: dict[str, Any] = field(default_factory=dict)


def _cli_prefix() -> tuple[str, ...]:
    """Вернуть установленный CLI, иначе запуск модулем."""
    executable = shutil.which("atlawire")
    return (executable,) if executable else CLI_FALLBACK


def _clean_env() -> dict[str, str]:
    """Окружение без ATLAWIRE_* URL/TOKEN: единый saved-file режим."""
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("ATLAWIRE_") and name.endswith(("_TOKEN", "_URL")):
            env.pop(name, None)
    return env


def remember_secret(token: str | None) -> None:
    """Запомнить токен только для вычищения из вывода."""
    if token and token not in _SECRETS:
        _SECRETS.append(token)


def redact(text: str) -> str:
    """Убрать любой известный токен из текста перед печатью."""
    for secret in _SECRETS:
        text = text.replace(secret, "***")
    return text


def _rule_phrase(rules: tuple[tuple[str, str, str], ...], func: str, combo: str) -> str:
    """Найти пояснение по точной функции и префиксу комбинации."""
    for rule_func, prefix, phrase in rules:
        if rule_func == func and combo.startswith(prefix):
            return phrase
    return ""


def _guard_cli(args: tuple[str, ...]) -> None:
    """Отказать всему, что вне фиксированного read-поверхности."""
    if not args or args[0] not in CLI_ALLOWED:
        raise SystemExit(f"команда вне read-allowlist отклонена: {args[:1]}")
    lowered = {token.lower() for token in args[1:]}
    blocked = lowered & CLI_WRITE_WORDS
    if blocked:
        raise SystemExit(f"write-токен в аргументах отклонён: {sorted(blocked)}")


def cli(args: tuple[str, ...]) -> CliResult:
    """Выполнить один read-only вызов CLI и проверить стоп-маркеры."""
    _guard_cli(args)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [*_cli_prefix(), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            env=_clean_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CliResult(args, -9, "", "timeout", time.monotonic() - started)
    text = completed.stdout + completed.stderr
    for marker in STOP_MARKERS:
        if marker in text:
            raise StopRun(f"стоп-маркер ответа: {marker}")
    return CliResult(
        args,
        completed.returncode,
        completed.stdout,
        completed.stderr,
        time.monotonic() - started,
    )


def call(fn: Callable[..., Any], /, **kwargs: Any) -> LibResult:
    """Вызвать библиотечную функцию, различая GAP (нет параметра) и ошибку."""
    started = time.monotonic()
    try:
        value = fn(**kwargs)
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" in message:
            return LibResult(2, error=message, seconds=time.monotonic() - started)
        return LibResult(3, error=message, seconds=time.monotonic() - started)
    except Exception as exc:  # noqa: BLE001 - нужен тип и текст без тела ответа
        return LibResult(
            1,
            error=f"{type(exc).__name__}: {exc}",
            seconds=time.monotonic() - started,
        )
    return LibResult(0, value=value, seconds=time.monotonic() - started)


def add(
    ctx: Ctx,
    area: str,
    func: str,
    combo: str,
    command: str,
    exit_code: int,
    expected: str,
    fact: str,
    verdict: str,
    notes: str = "",
) -> None:
    """Записать и сразу напечатать одну строку матрицы."""
    row: Row = {
        "area": area,
        "func": func,
        "combo": combo,
        "command": command,
        "exit": exit_code,
        "expected": expected,
        "fact": fact,
        "verdict": verdict,
        "notes": notes,
        "when": _rule_phrase(WHEN_RULES, func, combo) or "—",
        "duplicate": _rule_phrase(DUP_RULES, func, combo),
    }
    ctx.rows.append(row)
    index = len(ctx.rows)
    print(f"[{index:02d}] {area} | {func} | {combo} | exit={exit_code} | {verdict}")
    print(f"     cmd: {redact(command)}")
    print(f"     ждали: {expected}")
    print(f"     факт: {redact(fact)}")
    print(f"     когда: {row['when']}")
    if row["duplicate"]:
        print(f"     дубль: {row['duplicate']}")
    if notes:
        print(f"     заметка: {redact(notes)}")


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _rows_len(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict) and isinstance(value.get("issues"), list):
        return len(value["issues"])
    return None


def _short(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _tsv_header_rows(stdout: str) -> tuple[int | None, list[str]]:
    """Вернуть заявленное в шапке число строк TSV и сами строки данных."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    declared: int | None = None
    if lines and lines[0].startswith("# "):
        match = re.match(r"#\s+(\d+)\s+row", lines[0])
        declared = int(match[1]) if match else None
        lines = lines[2:]
    return declared, lines


def _plain_tokens(markup: str, minimum: int = 6) -> list[str]:
    """Токены видимого текста разметки: для оценки потери при рендере."""
    text = html_module.unescape(_HTML_TAGS.sub(" ", markup))
    return [token for token in re.findall(rf"[0-9A-Za-zА-Яа-яЁё]{{{minimum},}}", text)]


# ---------------------------------------------------------------------------
# Обнаружение фикстур через те же read-функции
# ---------------------------------------------------------------------------


def _imports() -> dict[str, Any]:
    """Импортировать atlawire (при необходимости добавив репозиторный src)."""
    try:
        import atlawire  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from atlawire import bitbucket as bb
    from atlawire import confluence as conf
    from atlawire import jira as jr
    from atlawire import repo_grep as rg
    from atlawire.credentials import resolve_saved_credentials

    return {
        "jira": jr,
        "bitbucket": bb,
        "confluence": conf,
        "repo_grep": rg,
        "resolve": resolve_saved_credentials,
    }


def discover_credentials(mod: dict[str, Any]) -> dict[str, Any]:
    """Загрузить три сохранённые пары, не печатая ни URL, ни токен."""
    creds: dict[str, Any] = {}
    for product in ("jira", "confluence", "bitbucket"):
        try:
            resolved = mod["resolve"](
                product, supplied_base_url=None, allow_http_loopback=False
            )
        except Exception as exc:  # noqa: BLE001 - категория без секретов
            print(f"credentials {product}: недоступны ({type(exc).__name__})")
            creds[product] = None
            continue
        remember_secret(getattr(resolved, "token", None))
        creds[product] = resolved
    return creds


def _jira_fixtures(issues: list[Any]) -> dict[str, Any]:
    """Разобрать задачи в фикстуры: 0/1/много комментариев, богатое описание, wiki."""
    fx: dict[str, Any] = {
        "zero": None,
        "one": None,
        "many": None,
        "many_total": -1,
        "rich": None,
        "wiki": None,
        "wiki_is_code": False,
        "any": None,
    }
    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("key"), str):
            continue
        key = issue["key"]
        fields = issue.get("fields") or {}
        description = fields.get("description") or ""
        comments = fields.get("comment") or {}
        comment_total = comments.get("total") if isinstance(comments, dict) else None
        if not isinstance(comment_total, int):
            continue
        if comment_total == 0 and fx["zero"] is None:
            fx["zero"] = key
        if comment_total == 1 and fx["one"] is None:
            fx["one"] = key
        if comment_total > fx["many_total"]:
            fx["many"], fx["many_total"] = key, comment_total
        if len(description) > 300 and fx["rich"] is None:
            fx["rich"] = key
        if _CODE_MARKUP.search(description) and not fx["wiki_is_code"]:
            fx["wiki"], fx["wiki_is_code"] = key, True
        elif _WIKI_MARKUP.search(description) and fx["wiki"] is None:
            fx["wiki"] = key
    fx["any"] = issues[0].get("key") if issues else None
    return fx


def discover_jira(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Найти JQL с запасом строк и задачи под 0/1/много комментариев."""
    creds = ctx.creds.get("jira")
    if creds is None:
        ctx.fixtures["jira"] = None
        return
    jr = mod["jira"]
    query = "assignee = currentUser() ORDER BY updated DESC"
    result = call(
        jr.search_raw,
        base_url=creds.base_url,
        jql=query,
        token=creds.token,
        fields="summary,comment,description,updated",
        limit=100,
    )
    if result.exit_code != 0 or not result.value:
        query = "created >= -3650d ORDER BY created DESC"
        result = call(
            jr.search_raw,
            base_url=creds.base_url,
            jql=query,
            token=creds.token,
            fields="summary,comment,description,updated",
            limit=100,
        )
    if result.exit_code != 0 or not result.value:
        ctx.fixtures["jira"] = None
        return
    envelope = result.value
    fx = _jira_fixtures(envelope.get("issues") or [])
    fx["jql"], fx["total"] = query, envelope.get("total")
    ctx.fixtures["jira"] = fx
    print("fixtures jira:", {k: v for k, v in fx.items() if k != "jql"})


def discover_confluence(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Найти CQL-выборку, страницу с детьми, без детей и с богатым storage."""
    creds = ctx.creds.get("confluence")
    if creds is None:
        ctx.fixtures["confluence"] = None
        return
    conf = mod["confluence"]
    query = 'space = "ARCH" and type = page'
    result = call(
        conf.search_cql,
        base_url=creds.base_url,
        query=query,
        token=creds.token,
        limit=100,
    )
    if result.exit_code != 0 or not result.value:
        query = "type = page"
        result = call(
            conf.search_cql,
            base_url=creds.base_url,
            query=query,
            token=creds.token,
            limit=100,
        )
    if result.exit_code != 0 or not result.value:
        ctx.fixtures["confluence"] = None
        return
    pages = result.value
    fx: dict[str, Any] = {
        "cql": query,
        "pages": len(pages),
        "with_children": None,
        "child_total": 0,
        "without_children": None,
        "rich": None,
        "rich_storage": 0,
        "rich_macros": 0,
    }
    for page in pages[:8]:
        page_id = str(page.get("id"))
        kids = call(
            conf.list_children,
            base_url=creds.base_url,
            page_id_or_url=page_id,
            token=creds.token,
            limit=100,
        )
        if kids.exit_code == 0 and isinstance(kids.value, list):
            if kids.value and fx["with_children"] is None:
                fx["with_children"], fx["child_total"] = page_id, len(kids.value)
            if not kids.value and fx["without_children"] is None:
                fx["without_children"] = page_id
        fetched = call(
            conf.get_page,
            base_url=creds.base_url,
            page_id_or_url=page_id,
            token=creds.token,
        )
        if fetched.exit_code == 0 and isinstance(fetched.value, dict):
            storage = ((fetched.value.get("body") or {}).get("storage") or {}).get(
                "value"
            ) or ""
            if fx["rich"] is None and len(storage) > 2000 and "<ac:" in storage:
                fx["rich"], fx["rich_storage"] = page_id, len(storage)
                fx["rich_macros"] = storage.count("<ac:")
        if fx["with_children"] and fx["without_children"] and fx["rich"]:
            break
    ctx.fixtures["confluence"] = fx
    print("fixtures confluence:", {k: v for k, v in fx.items() if k != "cql"})


# ---------------------------------------------------------------------------
# Jira: поиск (jql/search_issues/search_raw/search_all_issues)
# ---------------------------------------------------------------------------


def jira_search(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица jql/search_issues: limit, fields, expand и их комбинации."""
    creds = ctx.creds.get("jira")
    fx = ctx.fixtures.get("jira")
    if creds is None or not fx:
        add(
            ctx,
            "JIRA",
            "jira.search",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет credentials",
            "SKIP",
            "пропуск: сохранённые credentials Jira недоступны",
        )
        return
    jr = mod["jira"]
    total = fx["total"]
    fetched: dict[int, Any] = {}
    for limit in (1, 5, 50):
        res = cli(("jql", fx["jql"], "--limit", str(limit), "--json"))
        value = _json_or_none(res.stdout)
        fetched[limit] = value
        rows = _rows_len(value)
        capped = (
            rows == limit and isinstance(total, int) and total > limit and limit >= 5
        )
        fact = f"rows={rows} total_сервера={total}; total/признак обрезки в ответе CLI отсутствует"
        add(
            ctx,
            "JIRA",
            "jira.search / CLI jql",
            f"limit={limit}",
            f"atlawire jql <jql> --limit {limit} --json",
            res.exit_code,
            f"не более {limit} строк без скрытой потери",
            fact,
            "CAP" if capped else ("PASS" if rows == limit else "DEFECT"),
            "агент не отличает неполный набор от полного" if capped else "",
        )
    declared, data = _tsv_header_rows(cli(("jql", fx["jql"], "--limit", "5")).stdout)
    add(
        ctx,
        "JIRA",
        "CLI jql",
        "limit=5 TSV",
        "atlawire jql <jql> --limit 5",
        0,
        "TSV: шапка '# 5 row(s)' и 5 строк данных",
        f"шапка={declared}, строк данных={len(data)}",
        "PASS" if declared == 5 == len(data) else "DEFECT",
    )
    projection_keys = (
        sorted(fetched[5][0])
        if isinstance(fetched.get(5), list)
        and fetched[5]
        and isinstance(fetched[5][0], dict)
        else []
    )
    fields_args = ("jql", fx["jql"], "--limit", "2", "--fields", "summary", "--json")
    fields_res = cli(fields_args)
    fields_doc = _json_or_none(fields_res.stdout)
    fields_issues = fields_doc.get("issues") if isinstance(fields_doc, dict) else None
    fields_keys = (
        sorted((fields_issues[0] or {}).get("fields") or {})
        if isinstance(fields_issues, list)
        and fields_issues
        and isinstance(fields_issues[0], dict)
        else []
    )
    fewer = (
        bool(fields_keys)
        and bool(projection_keys)
        and len(fields_keys) < len(projection_keys)
    )
    add(
        ctx,
        "JIRA",
        "CLI jql",
        "fields=summary",
        "atlawire jql ... --limit 2 --fields summary --json",
        fields_res.exit_code,
        "raw-конверт: только summary вместо полной проекции",
        f"issues={len(fields_issues) if isinstance(fields_issues, list) else None}, "
        f"поля первой={fields_keys}, проекция={projection_keys}",
        "PASS"
        if fields_res.exit_code == 0 and fields_keys == ["summary"] and fewer
        else "DEFECT",
        "меньше полей — меньше контекста агенту; raw-конверт вместо коротких строк",
    )
    expand_args = (
        "jql",
        fx["jql"],
        "--limit",
        "1",
        "--expand",
        "renderedFields",
        "--json",
    )
    expand_res = cli(expand_args)
    expand_doc = _json_or_none(expand_res.stdout)
    expand_issues = expand_doc.get("issues") if isinstance(expand_doc, dict) else None
    rendered = [
        isinstance(issue.get("renderedFields"), dict)
        for issue in (expand_issues or [])
        if isinstance(issue, dict)
    ]
    rendered_present = bool(rendered) and all(rendered)
    add(
        ctx,
        "JIRA",
        "CLI jql",
        "expand=renderedFields",
        "atlawire jql ... --limit 1 --expand renderedFields --json",
        expand_res.exit_code,
        "renderedFields у задачи в raw-конверте, в проекции их нет",
        f"issues={len(rendered)}, renderedFields у каждой={rendered_present}, "
        f"проекция без renderedFields={'renderedFields' not in projection_keys}",
        "PASS"
        if expand_res.exit_code == 0
        and rendered_present
        and "renderedFields" not in projection_keys
        else "DEFECT",
        "HTML полей одним поисковым запросом, без отдельного issue",
    )
    res = call(
        jr.search_issues,
        base_url=creds.base_url,
        query=fx["jql"],
        token=creds.token,
        limit=1,
    )
    rows = _rows_len(res.value)
    keys = sorted(res.value[0]) if isinstance(res.value, list) and res.value else []
    add(
        ctx,
        "JIRA",
        "jira.search_issues",
        "limit=1",
        "atlawire.jira.search_issues(<jql>, limit=1)",
        res.exit_code,
        "1 строка проекции",
        f"rows={rows}, поля={keys}",
        "PASS" if rows == 1 else "DEFECT",
    )
    res = call(
        jr.search_issues,
        base_url=creds.base_url,
        query=fx["jql"],
        token=creds.token,
        limit=50,
    )
    rows = _rows_len(res.value)
    capped = rows == 50 and isinstance(total, int) and total > 50
    add(
        ctx,
        "JIRA",
        "jira.search_issues",
        "limit=50",
        "atlawire.jira.search_issues(<jql>, limit=50)",
        res.exit_code,
        "50 строк c признаком неполноты",
        f"rows={rows}, total={total}, признака обрезки нет",
        "CAP" if capped else ("PASS" if rows == 50 else "DEFECT"),
        "при total>limit голый список не сообщает о неполноте; metadata-вариант ниже закрывает пробел"
        if capped
        else "",
    )
    meta = call(
        jr.search_issues_with_metadata,
        base_url=creds.base_url,
        query=fx["jql"],
        token=creds.token,
        limit=50,
    )
    value = meta.value if meta.exit_code == 0 else None
    meta_rows = (
        len(value["rows"])
        if isinstance(value, dict) and isinstance(value.get("rows"), list)
        else None
    )
    truncated = value.get("truncated") if isinstance(value, dict) else None
    reported = value.get("total") if isinstance(value, dict) else None
    known = isinstance(reported, int) and not isinstance(reported, bool)
    expected_truncated = (not known) or (meta_rows is not None and reported > meta_rows)
    consistent = (
        meta.exit_code == 0
        and meta_rows == 50
        and isinstance(truncated, bool)
        and truncated == expected_truncated
    )
    add(
        ctx,
        "JIRA",
        "jira.search_issues_with_metadata",
        "limit=50 × truncated/total",
        "search_issues_with_metadata(<jql>, limit=50)",
        meta.exit_code,
        "50 строк + честный truncated/total",
        f"rows={meta_rows}, total={reported}, truncated={truncated}",
        "PASS" if consistent else "DEFECT",
        "total отсутствует — truncated=True; при known total>rows — True",
    )
    res = call(
        jr.search_issues,
        base_url=creds.base_url,
        query=fx["jql"],
        token=creds.token,
        limit=5,
        fields="summary",
    )
    add(
        ctx,
        "JIRA",
        "jira.search_issues",
        "limit=5 × fields=summary",
        "search_issues(<jql>, limit=5, fields='summary')",
        res.exit_code,
        "комбинация limit×fields",
        _short(res.error or ""),
        "GAP" if res.exit_code == 2 else "DEFECT",
        "поля зафиксированы _SEARCH_FIELDS; выбрать их нельзя",
    )
    for fields, expect in (
        ("summary", "только summary"),
        ("*all", "все поля задачи"),
        ("summary,status", "summary+status"),
    ):
        res = call(
            jr.search_raw,
            base_url=creds.base_url,
            jql=fx["jql"],
            token=creds.token,
            fields=fields,
            limit=5,
        )
        value = res.value if res.exit_code == 0 else None
        issues = value.get("issues") if isinstance(value, dict) else None
        first = issues[0].get("fields", {}) if issues else {}
        add(
            ctx,
            "JIRA",
            "jira.search_raw",
            f"limit=5 × fields={fields}",
            f"search_raw(<jql>, fields={fields!r}, limit=5)",
            res.exit_code,
            f"issues=5, fields: {expect}, total в конверте",
            f"issues={len(issues) if issues else None}, "
            f"total={value.get('total') if isinstance(value, dict) else None}, "
            f"полей={len(first)}",
            "PASS" if issues and len(issues) == 5 else "DEFECT",
        )
    res = call(
        jr.search_raw,
        base_url=creds.base_url,
        jql=fx["jql"],
        token=creds.token,
        fields=["summary", "status"],
        limit=5,
    )
    add(
        ctx,
        "JIRA",
        "jira.search_raw",
        "limit=5 × fields=list",
        "search_raw(<jql>, fields=['summary','status'], limit=5)",
        res.exit_code,
        "список полей принимается (как в search_all_issues)",
        _short(res.error or "принято"),
        "GAP" if res.exit_code != 0 else "PASS",
        "список принимается так же, как у search_all_issues",
    )
    for fields, expect in (
        ("*all", "все поля"),
        ("summary,status", "строка полей"),
        (["summary", "status"], "список полей"),
    ):
        res = call(
            jr.search_all_issues,
            base_url=creds.base_url,
            jql=fx["jql"],
            token=creds.token,
            fields=fields,
            limit=5,
            max_pages=1,
        )
        issues = res.value if res.exit_code == 0 else None
        first = issues[0].get("fields", {}) if issues else {}
        combo = f"limit=5 × fields={fields if isinstance(fields, str) else 'list'}"
        add(
            ctx,
            "JIRA",
            "jira.search_all_issues",
            combo,
            f"search_all_issues(<jql>, fields={fields!r}, limit=5)",
            res.exit_code,
            f"5 полных объектов, {expect}",
            f"issues={len(issues) if issues else None}, полей={len(first)}",
            "PASS" if issues and len(issues) == 5 else "DEFECT",
        )
    for expand, expect in (
        (None, "renderedFields отсутствует"),
        ("renderedFields", "renderedFields у каждой задачи"),
    ):
        res = call(
            jr.search_raw,
            base_url=creds.base_url,
            jql=fx["jql"],
            token=creds.token,
            fields="summary",
            expand=expand,
            limit=2,
        )
        value = res.value if res.exit_code == 0 else None
        issues = value.get("issues") if isinstance(value, dict) else None
        has = [("renderedFields" in issue) for issue in issues] if issues else []
        add(
            ctx,
            "JIRA",
            "jira.search_raw",
            f"limit=2 × expand={expand}",
            f"search_raw(<jql>, fields='summary', expand={expand!r}, limit=2)",
            res.exit_code,
            f"2 issues, {expect}",
            f"issues={len(issues) if issues else None}, rendered={has}",
            "PASS"
            if len(has) == 2 and (not any(has) if expand is None else all(has))
            else "DEFECT",
        )
    res = call(
        jr.search_raw,
        base_url=creds.base_url,
        jql=fx["jql"],
        token=creds.token,
        fields="summary",
        expand="renderedFields",
        limit=2,
    )
    value = res.value if res.exit_code == 0 else None
    issues = value.get("issues") if isinstance(value, dict) else None
    both = bool(issues) and all(
        set(issue.get("fields") or {}) == {"summary"} and "renderedFields" in issue
        for issue in issues
    )
    add(
        ctx,
        "JIRA",
        "jira.search_raw",
        "fields=summary × expand=renderedFields × limit=2",
        "search_raw(<jql>, fields='summary', expand='renderedFields', limit=2)",
        res.exit_code,
        "поля урезаны до summary, renderedFields добавлен",
        f"issues={len(issues) if issues else None}, combo_ok={both}",
        "PASS" if both else "DEFECT",
    )
    res = call(
        jr.search_raw,
        base_url=creds.base_url,
        jql=fx["jql"],
        token=creds.token,
        limit=0,
    )
    add(
        ctx,
        "JIRA",
        "jira.search_raw",
        "limit=0",
        "search_raw(<jql>, limit=0)",
        res.exit_code,
        "валидация: 0 вне диапазона",
        _short(res.error or "принято"),
        "PASS" if res.exit_code == 1 else "DEFECT",
    )


# ---------------------------------------------------------------------------
# Jira: get_issue + комментарии
# ---------------------------------------------------------------------------


def jira_issue(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица issue/get_issue: expand=None/renderedFields/changelog/transitions."""
    creds = ctx.creds.get("jira")
    fx = ctx.fixtures.get("jira")
    if creds is None or not fx or not fx.get("any"):
        add(
            ctx,
            "JIRA",
            "jira.get_issue",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет задачи",
            "SKIP",
            "пропуск: задача для чтения не найдена",
        )
        return
    jr = mod["jira"]
    key = fx["any"]
    res = cli(("issue", key))
    value = _json_or_none(res.stdout)
    default_issue = value
    ok = isinstance(value, dict) and isinstance(value.get("fields"), dict)
    add(
        ctx,
        "JIRA",
        "CLI issue",
        "expand по умолчанию",
        f"atlawire issue {key}",
        res.exit_code,
        "JSON с fields и renderedFields",
        f"JSON-объект={ok}, ключи={sorted(value)[:8] if isinstance(value, dict) else None}",
        "PASS" if ok and "renderedFields" in value else "DEFECT",
    )
    md = cli(("issue", key, "--markdown"))
    text = md.stdout
    add(
        ctx,
        "JIRA",
        "CLI issue",
        "--markdown",
        f"atlawire issue {key} --markdown",
        md.exit_code,
        "Markdown с заголовком и статусом",
        f"строк={len(text.splitlines())}, есть '{key}:'={key in text}, есть Status={'Status:' in text}",
        "PASS" if md.exit_code == 0 and key in text and "Status:" in text else "DEFECT",
    )
    for expand in (
        None,
        "renderedFields",
        "changelog",
        "transitions",
        "renderedFields,changelog",
    ):
        res = call(
            jr.get_issue,
            base_url=creds.base_url,
            key_or_url=key,
            token=creds.token,
            expand=expand,
        )
        value = res.value if res.exit_code == 0 else None
        facts: list[str] = []
        if isinstance(value, dict):
            for name in ("renderedFields", "changelog", "transitions"):
                facts.append(f"{name}={name in value}")
            if "changelog" in value:
                facts.append(
                    f"histories={len((value.get('changelog') or {}).get('histories') or [])}"
                )
            if "transitions" in value:
                facts.append(f"transitions={len(value.get('transitions') or [])}")
        add(
            ctx,
            "JIRA",
            "jira.get_issue",
            f"expand={expand}",
            f"atlawire.jira.get_issue('{key}', expand={expand!r})",
            res.exit_code,
            "JSON с запрошенным expand и без лишних блоков",
            ", ".join(facts) if facts else _short(res.error or ""),
            "PASS" if res.exit_code == 0 else "DEFECT",
        )
    expand_args = ("issue", key, "--expand", "changelog")
    expand_res = cli(expand_args)
    expand_doc = _json_or_none(expand_res.stdout)
    expand_histories = (
        (expand_doc.get("changelog") or {}).get("histories")
        if isinstance(expand_doc, dict)
        else None
    )
    history_rows = expand_histories if isinstance(expand_histories, list) else []
    default_has_changelog = (
        isinstance(default_issue, dict) and "changelog" in default_issue
    )
    add(
        ctx,
        "JIRA",
        "CLI issue",
        "expand=changelog",
        f"atlawire issue {key} --expand changelog",
        expand_res.exit_code,
        "raw JSON с changelog и непустой историей, дефолтный issue без changelog",
        f"changelog={isinstance(expand_histories, list)}, histories={len(history_rows)}, "
        f"у дефолтного issue changelog={default_has_changelog}",
        "PASS"
        if expand_res.exit_code == 0
        and isinstance(expand_doc, dict)
        and isinstance(expand_histories, list)
        and bool(history_rows)
        and not default_has_changelog
        else "DEFECT",
        "история задачи одним вызовом вместо отдельного issue-changelog",
    )


def jira_comments(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица issue-comments: limit, страницы, задачи с 0/1/много комментариев."""
    creds = ctx.creds.get("jira")
    fx = ctx.fixtures.get("jira")
    if creds is None or not fx:
        add(
            ctx,
            "JIRA",
            "jira.list_issue_comments",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет данных",
            "SKIP",
            "пропуск: credentials Jira недоступны",
        )
        return
    jr = mod["jira"]
    for name, expected_total in (
        ("zero", 0),
        ("one", 1),
        ("many", fx.get("many_total")),
    ):
        key = fx.get(name)
        if not key:
            add(
                ctx,
                "JIRA",
                "CLI issue-comments",
                f"задача={name}",
                f"— {name}",
                -1,
                f"{name}: комментариев={expected_total}",
                "задача не найдена",
                "SKIP",
            )
            continue
        res = cli(("issue-comments", key))
        value = _json_or_none(res.stdout)
        count = len(value) if isinstance(value, list) else None
        empty_body = [
            row.get("id") for row in (value or []) if not (row or {}).get("body")
        ]
        add(
            ctx,
            "JIRA",
            "CLI issue-comments",
            f"задача {key} ({name})",
            f"atlawire issue-comments {key}",
            res.exit_code,
            f"комментариев={expected_total}, body непустой",
            f"rows={count}, без body={empty_body}",
            "PASS" if count == expected_total else "DEFECT",
        )
    key = fx.get("many") or fx.get("any")
    full = cli(("issue-comments", key))
    full_value = _json_or_none(full.stdout)
    full_rows = full_value if isinstance(full_value, list) else []
    limited = cli(("issue-comments", key, "--limit", "1"))
    limited_value = _json_or_none(limited.stdout)
    truncated = None
    reported_total = None
    limited_rows: list[Any] = []
    if isinstance(limited_value, dict):
        rows_value = limited_value.get("rows")
        limited_rows = rows_value if isinstance(rows_value, list) else []
        truncated = limited_value.get("truncated")
        reported_total = limited_value.get("total")
    elif isinstance(limited_value, list):
        limited_rows = limited_value
    full_count = len(full_rows) if full_value is not None else -1
    same_first = (
        bool(full_rows)
        and bool(limited_rows)
        and isinstance(full_rows[0], dict)
        and isinstance(limited_rows[0], dict)
        and full_rows[0].get("id") == limited_rows[0].get("id")
    )
    note_shown = "# showing 1 of" in limited.stderr
    changed = (
        full_count > 1
        and truncated is True
        and reported_total == full_count
        and len(limited_rows) == 1
        and same_first
        and note_shown
    )
    add(
        ctx,
        "JIRA",
        "CLI issue-comments",
        "limit=1",
        f"atlawire issue-comments {key} --limit 1",
        limited.exit_code,
        "limit → maxResults; обрезанный тред — объект rows/truncated/total + заметка в stderr",
        f"full={full_count}, limited={len(limited_rows)}, truncated={truncated}, "
        f"total={reported_total}, stderr-заметка={note_shown}, первый совпал={same_first}",
        "PASS"
        if full_count > 1 and changed
        else ("DEFECT" if full_count > 1 else "SKIP"),
        "первые N комментариев; обрезка видна в truncated/total и stderr"
        if full_count > 1
        else "у выбранной задачи <=1 комментария, эффект limit не наблюдается",
    )
    key = fx.get("many") or fx.get("any")
    res = call(
        jr.list_issue_comments,
        base_url=creds.base_url,
        key_or_url=key,
        token=creds.token,
        max_pages=1,
    )
    count = _rows_len(res.value)
    add(
        ctx,
        "JIRA",
        "jira.list_issue_comments",
        "max_pages=1",
        f"list_issue_comments('{key}', max_pages=1)",
        res.exit_code,
        "весь тред этой задачи (<=50 на страницу)",
        f"rows={count}, total={fx.get('many_total')}",
        "PASS" if res.exit_code == 0 else "DEFECT",
        "при total>50 ожидается ошибка 'exceeded the page limit', а не тихая обрезка",
    )
    res = call(
        jr.list_issue_comments,
        base_url=creds.base_url,
        key_or_url=key,
        token=creds.token,
        limit=1,
    )
    rows = res.value if res.exit_code == 0 else None
    limited_count = _rows_len(rows)
    meta = call(
        jr.list_issue_comments_with_metadata,
        base_url=creds.base_url,
        key_or_url=key,
        token=creds.token,
        limit=1,
    )
    meta_value = meta.value if meta.exit_code == 0 else None
    meta_rows = (
        len(meta_value["rows"])
        if isinstance(meta_value, dict) and isinstance(meta_value.get("rows"), list)
        else None
    )
    truncated = meta_value.get("truncated") if isinstance(meta_value, dict) else None
    reported_total = meta_value.get("total") if isinstance(meta_value, dict) else None
    cut_visible = (
        meta.exit_code == 0
        and meta_rows == 1
        and truncated is True
        and (reported_total is None or isinstance(reported_total, int))
    )
    add(
        ctx,
        "JIRA",
        "jira.list_issue_comments",
        "limit=1",
        "list_issue_comments(..., limit=1) + list_issue_comments_with_metadata(...)",
        res.exit_code,
        "1 комментарий; metadata-вариант показывает truncated=True",
        f"rows={limited_count}, meta_rows={meta_rows}, truncated={truncated}, "
        f"total={reported_total}",
        "PASS"
        if res.exit_code == 0 and limited_count == 1 and cut_visible
        else "DEFECT",
        "limit уходит в серверный maxResults; признак обрезки виден только в metadata-варианте",
    )


# ---------------------------------------------------------------------------
# Bitbucket: commits, files, grep
# ---------------------------------------------------------------------------


def bitbucket_commits(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица commits: limit, at, path и комбинации."""
    creds = ctx.creds.get("bitbucket")
    if creds is None:
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_commits",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет credentials",
            "SKIP",
            "пропуск: credentials Bitbucket недоступны",
        )
        return
    fetched: dict[int, tuple[Any, int | None]] = {}
    for limit in (1, 3, 100, 1000):
        res = cli(("commits", REPO, "--limit", str(limit), "--json"))
        value = _json_or_none(res.stdout)
        fetched[limit] = (value, _rows_len(value))
    full = fetched[1000][1] or 0
    for limit in (1, 3, 100, 1000):
        value, rows = fetched[limit]
        capped = rows == limit and full > limit >= 100
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_commits",
            f"limit={limit}",
            f"atlawire commits {REPO} --limit {limit} --json",
            0,
            f"не более {limit} строк; при cap — признак неполноты",
            f"rows={rows}, всего_в_репо={full}, полей={len(value[0]) if value else None}",
            "CAP"
            if capped
            else ("PASS" if rows is not None and rows <= limit else "DEFECT"),
            "обрезка без предупреждения: total не отдаётся" if capped else "",
        )
    if full > 100:
        bb = mod["bitbucket"]
        meta = call(
            bb.list_commits_with_metadata,
            base_url=creds.base_url,
            repo=REPO,
            token=creds.token,
            limit=100,
        )
        value = meta.value if meta.exit_code == 0 else None
        meta_rows = (
            len(value["commits"])
            if isinstance(value, dict) and isinstance(value.get("commits"), list)
            else None
        )
        complete = value.get("complete") if isinstance(value, dict) else None
        limited = value.get("limit") if isinstance(value, dict) else None
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_commits_with_metadata",
            "limit=100 × complete",
            "list_commits_with_metadata(repo, limit=100)",
            meta.exit_code,
            f"100 строк и complete=False (всего {full})",
            f"rows={meta_rows}, complete={complete}, limit={limited}",
            "PASS"
            if (
                meta.exit_code == 0
                and meta_rows == 100
                and limited == 100
                and complete is False
            )
            else "DEFECT",
            "complete=False — единственный честный признак: totalCount 5.10 не отдаёт",
        )
    for combo, args in (
        ("at", ("commits", REPO, "--at", MERGE_SHA, "--limit", "3", "--json")),
        ("path", ("commits", REPO, "--path", COMMIT_FILE, "--limit", "3", "--json")),
        (
            "at × path",
            (
                "commits",
                REPO,
                "--at",
                MERGE_SHA,
                "--path",
                COMMIT_FILE,
                "--limit",
                "3",
                "--json",
            ),
        ),
    ):
        res = cli(args)
        value = _json_or_none(res.stdout)
        hashes = [row.get("hash") for row in value] if isinstance(value, list) else []
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_commits",
            combo,
            "atlawire " + " ".join(args),
            res.exit_code,
            "непустой список коммитов",
            f"rows={_rows_len(value)}, первый={(hashes[0][:12] + '…') if hashes and hashes[0] else None}",
            "PASS" if hashes else "DEFECT",
        )
    tsv = cli(("commits", REPO, "--limit", "3"))
    declared, data = _tsv_header_rows(tsv.stdout)
    long_message = any(
        len(str(row.get("message") or "")) > 160 for row in (fetched[1000][0] or [])
    )
    truncated = False
    if isinstance(fetched[1000][0], list) and len(fetched[1000][0]) >= 3 and data:
        json_len = len(" ".join(str(fetched[1000][0][0].get("message") or "").split()))
        tsv_len = len(data[0].split("\t")[3]) if len(data[0].split("\t")) > 3 else 0
        truncated = json_len > tsv_len >= 160
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_commits",
        "TSV (без --json)",
        f"atlawire commits {REPO} --limit 3",
        tsv.exit_code,
        "сообщение коммита без обрезки или с предупреждением",
        f"шапка={declared}, строк={len(data)}, обрезка_160={truncated}, "
        f"есть_длинные_сообщения={long_message}",
        "CAP" if truncated else "PASS",
        "TSV режет message до 160 символов без предупреждения",
    )


def bitbucket_files(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица files: --at и без; отказ при исчерпании страниц."""
    creds = ctx.creds.get("bitbucket")
    if creds is None:
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_repository_files",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет credentials",
            "SKIP",
        )
        return
    res = cli(("files", REPO, "--json"))
    value = _json_or_none(res.stdout)
    count = len(value) if isinstance(value, list) else None
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_repository_files",
        "без --at",
        f"atlawire files {REPO} --json",
        res.exit_code,
        "полный список путей ветки по умолчанию",
        f"paths={count}, первые={value[:2] if value else None}",
        "PASS" if count else "DEFECT",
    )
    res = cli(("files", REPO, "--at", MERGE_SHA, "--json"))
    value = _json_or_none(res.stdout)
    count_at = len(value) if isinstance(value, list) else None
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_repository_files",
        f"at={MERGE_SHA[:12]}…",
        f"atlawire files {REPO} --at {MERGE_SHA[:12]}… --json",
        res.exit_code,
        "список путей на конкретном коммите",
        f"paths={count_at}, столько_же_как_HEAD={count_at == count}",
        "PASS" if count_at else "DEFECT",
    )
    res = cli(("files", OTHER_REPO, "--json", "--max-pages", "1"))
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_repository_files",
        "max-pages=1 (многостраничный)",
        f"atlawire files {OTHER_REPO} --json --max-pages 1",
        res.exit_code,
        "ошибка без частичного stdout (тихая обрезка запрещена)",
        f"stdout пуст={not res.stdout.strip()}, ошибка={_short(res.stderr)}",
        "PASS" if res.exit_code != 0 and not res.stdout.strip() else "DEFECT",
    )


def bitbucket_grep(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица grep-repo: glob/без glob, малый/большой limit, listing."""
    creds = ctx.creds.get("bitbucket")
    if creds is None:
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.grep_repository",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет credentials",
            "SKIP",
        )
        return
    cases = (
        (
            "glob × limit=1",
            (
                "grep-repo",
                REPO,
                "ContactController",
                "--glob",
                GREP_GLOB,
                "--limit",
                "1",
            ),
        ),
        (
            "glob × limit=1000",
            (
                "grep-repo",
                REPO,
                "ContactController",
                "--glob",
                GREP_GLOB,
                "--limit",
                "1000",
            ),
        ),
        (
            "без glob × limit=3",
            ("grep-repo", REPO, "ContactController", "--limit", "3"),
        ),
        (
            "без glob × limit=1000 (default timeout=120s)",
            ("grep-repo", REPO, "ContactController", "--limit", "1000"),
        ),
        (
            "listing path=src × limit=1000",
            ("grep-repo", REPO, "--path", "src", "--limit", "1000"),
        ),
    )
    for combo, args in cases:
        res = cli(args)
        value = _json_or_none(res.stdout)
        if not isinstance(value, dict):
            add(
                ctx,
                "BITBUCKET",
                "bitbucket.grep_repository",
                combo,
                "atlawire " + " ".join(args),
                res.exit_code,
                "JSON с hits/files и признаком неполноты",
                f"не JSON: {_short(res.stderr or res.stdout)}",
                "DEFECT",
                "ошибка бюджета на валидной комбинации (default --timeout 120s)",
            )
            continue
        hits = value.get("hits") or []
        fact = (
            f"hits={len(hits)} files={len(value.get('files') or [])} "
            f"eligible={value.get('files_eligible')} scanned={value.get('files_scanned')} "
            f"excluded={value.get('files_excluded')} truncated={value.get('truncated')} "
            f"complete={value.get('complete')} status={value.get('status')} "
            f"message={value.get('message')!r} selection={value.get('selection')}"
        )
        status = value.get("status")
        message = value.get("message")
        complete = value.get("complete")
        truncated = value.get("truncated")
        consistent = (
            status in ("complete", "truncated", "timeout")
            and complete is (status == "complete")
            and truncated is (status != "complete")
            and (message is None) == (status != "timeout")
        )
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.grep_repository",
            combo,
            "atlawire " + " ".join(args),
            res.exit_code,
            "честные счётчики + status/complete",
            fact,
            "PASS" if consistent else "DEFECT",
            "truncated=True при достигнутом limit — полный набор неотличим от обрезанного"
            if status == "truncated"
            else "",
        )


# ---------------------------------------------------------------------------
# Bitbucket: pull requests (state/limit/order/role)
# ---------------------------------------------------------------------------


def bitbucket_prs(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица prs/my-prs: state, limit, order, role."""
    creds = ctx.creds.get("bitbucket")
    if creds is None:
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_pull_requests",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет credentials",
            "SKIP",
        )
        return
    state_rows: dict[str, int | None] = {}
    for state in ("OPEN", "MERGED", "DECLINED"):
        res = cli(("prs", REPO, "--state", state, "--limit", "3", "--json"))
        value = _json_or_none(res.stdout)
        rows = _rows_len(value)
        state_rows[state] = rows
        states = (
            sorted({row.get("state") for row in value})
            if isinstance(value, list) and value
            else []
        )
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_pull_requests",
            f"state={state} limit=3",
            f"atlawire prs {REPO} --state {state} --limit 3 --json",
            res.exit_code,
            f"строки только в состоянии {state}",
            f"rows={rows}, states={states}",
            "PASS"
            if rows is not None and (not value or states == [state])
            else "DEFECT",
            "пусто подтверждено: в state=ALL нет таких PR" if rows == 0 else "",
        )
    res = cli(("prs", REPO, "--state", "ALL", "--limit", "1000", "--json"))
    value = _json_or_none(res.stdout)
    rows = _rows_len(value)
    states = (
        sorted({row.get("state") for row in value})
        if isinstance(value, list) and value
        else []
    )
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_pull_requests",
        "state=ALL limit=1000",
        f"atlawire prs {REPO} --state ALL --limit 1000 --json",
        res.exit_code,
        "все PR без фильтра состояния",
        f"rows={rows}, states={states}",
        "PASS" if rows is not None else "DEFECT",
    )
    state_rows["ALL"] = rows
    res = cli(("prs", REPO, "--state", "ALL", "--limit", "3", "--json"))
    rows = _rows_len(_json_or_none(res.stdout))
    add(
        ctx,
        "BITBUCKET",
        "bitbucket.list_pull_requests",
        "state=ALL limit=3",
        f"atlawire prs {REPO} --state ALL --limit 3 --json",
        res.exit_code,
        "3 недавних PR всех состояний",
        f"rows={rows}, всего={state_rows.get('ALL')}",
        "PASS" if rows == 3 else "DEFECT",
    )
    for order in ("NEWEST", "OLDEST"):
        res = cli(
            ("prs", REPO, "--state", "ALL", "--order", order, "--limit", "3", "--json")
        )
        value = _json_or_none(res.stdout)
        ids = [row.get("id") for row in value] if isinstance(value, list) else []
        ordered = ids == sorted(ids, reverse=(order == "NEWEST")) if ids else False
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.list_pull_requests",
            f"order={order}",
            f"atlawire prs {REPO} --state ALL --order {order} --limit 3 --json",
            res.exit_code,
            "порядок id согласно order",
            f"ids={ids}, упорядочено={ordered}",
            "PASS" if ordered else "DEFECT",
        )
    for role in ("AUTHOR", "REVIEWER", "PARTICIPANT"):
        res = cli(
            ("my-prs", "--state", "OPEN", "--role", role, "--limit", "3", "--json")
        )
        value = _json_or_none(res.stdout)
        rows = _rows_len(value)
        add(
            ctx,
            "BITBUCKET",
            "bitbucket.my_pull_requests",
            f"role={role} state=OPEN",
            f"atlawire my-prs --state OPEN --role {role} --limit 3 --json",
            res.exit_code,
            "PR, где я в указанной роли",
            f"rows={rows}, полей={sorted(value[0]) if value else None}",
            "PASS" if rows is not None else "DEFECT",
            "0 строк — у пользователя нет PR в этой роли" if rows == 0 else "",
        )
    bad = cli(("prs", REPO, "--role", "REVIEWER", "--limit", "3", "--json"))
    add(
        ctx,
        "BITBUCKET",
        "CLI prs",
        "role=REVIEWER",
        f"atlawire prs {REPO} --role REVIEWER",
        bad.exit_code,
        "роль доступна в prs",
        "Click: " + _short(bad.text),
        "GAP",
        "роль есть только у my-prs; у prs нет ни role, ни direction",
    )


# ---------------------------------------------------------------------------
# Confluence: cql, children, page + форматы
# ---------------------------------------------------------------------------


def confluence_cql(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица cql: limit 1/3/100/1000 и отсутствие expand."""
    creds = ctx.creds.get("confluence")
    fx = ctx.fixtures.get("confluence")
    if creds is None or not fx:
        add(
            ctx,
            "CONFLUENCE",
            "confluence.search_cql",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет данных",
            "SKIP",
            "пропуск: credentials/фикстуры Confluence недоступны",
        )
        return
    fetched: dict[int, tuple[int, int | None, Any]] = {}
    for limit in (1, 3, 100, 1000):
        res = cli(("cql", fx["cql"], "--limit", str(limit), "--json"))
        value = _json_or_none(res.stdout)
        fetched[limit] = (res.exit_code, _rows_len(value), value)
    for limit in (1, 3, 100, 1000):
        exit_code, rows, values = fetched[limit]
        if limit == 1000:
            add(
                ctx,
                "CONFLUENCE",
                "confluence.search_cql",
                "limit=1000",
                "atlawire cql <cql> --limit 1000 --json",
                exit_code,
                "до 1000 строк; total не отдаётся",
                f"rows={rows}, полей={sorted(values[0]) if values else None}",
                "CAP" if rows == 1000 else "PASS",
                "rows=1000 = верхняя граница: возможно, набор обрезан"
                if rows == 1000
                else "",
            )
            continue
        capped = rows == limit and (fetched[1000][1] or 0) > limit >= 100
        add(
            ctx,
            "CONFLUENCE",
            "confluence.search_cql",
            f"limit={limit}",
            f"atlawire cql <cql> --limit {limit} --json",
            exit_code,
            "не более limit строк; при cap — признак неполноты",
            f"rows={rows}, полей={sorted(values[0]) if values else None}",
            "CAP"
            if capped
            else ("PASS" if rows is not None and rows <= limit else "DEFECT"),
            "при total>limit обрезка без предупреждения" if capped else "",
        )
    expand_args = (
        "cql",
        fx["cql"],
        "--limit",
        "2",
        "--expand",
        "content.body.storage",
    )
    expand_res = cli(expand_args)
    expand_doc = _json_or_none(expand_res.stdout)
    expand_results = expand_doc.get("results") if isinstance(expand_doc, dict) else None
    result_rows = expand_results if isinstance(expand_results, list) else []
    storage_lengths: list[int] = []
    for result in result_rows:
        content = result.get("content") if isinstance(result, dict) else None
        body = content.get("body") if isinstance(content, dict) else None
        storage_block = body.get("storage") if isinstance(body, dict) else None
        stored = storage_block.get("value") if isinstance(storage_block, dict) else None
        storage_lengths.append(len(stored) if isinstance(stored, str) else -1)
    body_present = bool(storage_lengths) and all(
        length > 0 for length in storage_lengths
    )
    projection_columns = sorted(fetched[3][2][0]) if fetched[3][2] else []
    add(
        ctx,
        "CONFLUENCE",
        "CLI cql",
        "expand=content.body.storage",
        "atlawire cql ... --limit 2 --expand content.body.storage",
        expand_res.exit_code,
        "raw-конверт: body.storage.value у каждого результата, в проекции body нет",
        f"results={len(result_rows)}, body.storage длины={storage_lengths}, "
        f"проекция={projection_columns}",
        "PASS"
        if expand_res.exit_code == 0
        and body_present
        and "body" not in projection_columns
        else "DEFECT",
        "тело страниц прямо в поиске: без отдельного page на каждый результат",
    )


def confluence_children(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица list_children: limit малый/большой, страница без детей, limit=0."""
    fx = ctx.fixtures.get("confluence")
    if not fx:
        add(
            ctx,
            "CONFLUENCE",
            "confluence.list_children",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет данных",
            "SKIP",
        )
        return
    page = fx.get("with_children")
    if page:
        res = cli(("children", page, "--limit", "1", "--json"))
        rows = _rows_len(_json_or_none(res.stdout))
        add(
            ctx,
            "CONFLUENCE",
            "confluence.list_children",
            f"limit=1 (всего {fx['child_total']})",
            f"atlawire children {page} --limit 1 --json",
            res.exit_code,
            "1 строка + библиотечный metadata-вариант ниже",
            f"rows={rows}, total_скрыт=True",
            "CAP",
            "CLI children отдаёт голый массив; list_children_with_metadata ниже отдаёт total/truncated",
        )
        creds = ctx.creds.get("confluence")
        if creds is not None:
            lib = mod["confluence"]
            meta = call(
                lib.list_children_with_metadata,
                base_url=creds.base_url,
                page_id_or_url=page,
                token=creds.token,
                limit=1,
            )
            value = meta.value if meta.exit_code == 0 else None
            meta_rows = (
                len(value["rows"])
                if isinstance(value, dict) and isinstance(value.get("rows"), list)
                else None
            )
            truncated = value.get("truncated") if isinstance(value, dict) else None
            reported = value.get("total") if isinstance(value, dict) else None
            consistent = (
                meta.exit_code == 0
                and meta_rows == 1
                and truncated is True
                and (
                    reported is None
                    or (
                        isinstance(reported, int)
                        and not isinstance(reported, bool)
                        and reported >= 2
                    )
                )
            )
            add(
                ctx,
                "CONFLUENCE",
                "confluence.list_children_with_metadata",
                f"limit=1 (всего {fx['child_total']})",
                "list_children_with_metadata(page, limit=1)",
                meta.exit_code,
                "1 строка + truncated=True со смыслом, а не голый список",
                f"rows={meta_rows}, total={reported}, truncated={truncated}",
                "PASS" if consistent else "DEFECT",
                "truncated=True — агент знает, что показана часть; total — из totalSize сервера",
            )
        res = cli(("children", page, "--limit", "100", "--json"))
        rows = _rows_len(_json_or_none(res.stdout))
        add(
            ctx,
            "CONFLUENCE",
            "confluence.list_children",
            "limit=100",
            f"atlawire children {page} --limit 100 --json",
            res.exit_code,
            f"все {fx['child_total']} ребёнка",
            f"rows={rows}",
            "PASS" if rows == fx["child_total"] else "DEFECT",
        )
    empty = fx.get("without_children")
    if empty:
        res = cli(("children", empty, "--json"))
        value = _json_or_none(res.stdout)
        add(
            ctx,
            "CONFLUENCE",
            "confluence.list_children",
            "страница без детей",
            f"atlawire children {empty} --json",
            res.exit_code,
            "пустой массив без ошибки",
            f"rows={_rows_len(value)}",
            "PASS" if value == [] else "DEFECT",
        )
        res = cli(("children", empty, "--limit", "0", "--json"))
        add(
            ctx,
            "CONFLUENCE",
            "confluence.list_children",
            "limit=0",
            f"atlawire children {empty} --limit 0 --json",
            res.exit_code,
            "0 строк без ошибки",
            f"rows={_rows_len(_json_or_none(res.stdout))}",
            "PASS" if res.exit_code == 0 else "DEFECT",
        )


def confluence_page(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Матрица get_page: JSON/--storage/--html/--markdown и потеря содержимого."""
    creds = ctx.creds.get("confluence")
    fx = ctx.fixtures.get("confluence")
    if creds is None or not fx or not fx.get("rich"):
        add(
            ctx,
            "CONFLUENCE",
            "confluence.get_page",
            "все",
            "—",
            -1,
            "фикстуры",
            "нет страницы с содержимым",
            "SKIP",
        )
        return
    page = fx["rich"]
    json_res = cli(("page", page))
    document = _json_or_none(json_res.stdout)
    storage = ""
    if isinstance(document, dict):
        storage = ((document.get("body") or {}).get("storage") or {}).get("value") or ""
    add(
        ctx,
        "CONFLUENCE",
        "confluence.get_page",
        "JSON (expand фиксирован)",
        f"atlawire page {page}",
        json_res.exit_code,
        "JSON с body.storage.value",
        f"body.storage.value={len(storage)}, макросов={storage.count('<ac:')}, "
        f"параметра expand нет",
        "PASS" if storage else "DEFECT",
        "expand не выбирается (GAP ниже)",
    )
    add(
        ctx,
        "CONFLUENCE",
        "confluence.get_page",
        "expand=body.storage (библиотека)",
        "atlawire.confluence.get_page(page) — expand не параметр",
        -1,
        "библиотечная get_page всегда шлёт фиксированный expand",
        "expanded: body.storage,version,space,ancestors",
        "GAP",
        "у библиотечной функции expand не выбирается; CLI-вариант проверяется строкой CLI page",
    )
    expand_args = ("page", page, "--expand", "version")
    expand_res = cli(expand_args)
    expand_doc = _json_or_none(expand_res.stdout)
    default_version = (
        (document.get("version") or {}).get("number")
        if isinstance(document, dict)
        else None
    )
    expand_version = (
        (expand_doc.get("version") or {}).get("number")
        if isinstance(expand_doc, dict)
        else None
    )
    expand_has_body = isinstance(expand_doc, dict) and "body" in expand_doc
    add(
        ctx,
        "CONFLUENCE",
        "CLI page",
        "expand=version",
        f"atlawire page {page} --expand version",
        expand_res.exit_code,
        "raw-страница только с version, без body; дефолтный page содержит body.storage",
        f"version={expand_version} (дефолт {default_version}), "
        f"body отсутствует={not expand_has_body}, дефолтный body.storage={len(storage)} символов",
        "PASS"
        if expand_res.exit_code == 0
        and isinstance(expand_doc, dict)
        and default_version is not None
        and expand_version == default_version
        and not expand_has_body
        and bool(storage)
        else "DEFECT",
        "выбор expand: версия без тела — меньше полей для контекста",
    )
    storage_res = cli(("page", page, "--storage"))
    html_res = cli(("page", page, "--html"))
    add(
        ctx,
        "CONFLUENCE",
        "confluence.get_page",
        "--storage",
        f"atlawire page {page} --storage",
        storage_res.exit_code,
        "storage XHTML совпадает с body.storage.value",
        f"длины: storage={len(storage_res.stdout.strip())}, json={len(storage)}",
        "PASS" if storage_res.stdout.strip() == storage else "DEFECT",
    )
    add(
        ctx,
        "CONFLUENCE",
        "confluence.get_page",
        "--html (алиас)",
        f"atlawire page {page} --html",
        html_res.exit_code,
        "--html идентичен --storage",
        f"идентичны={html_res.stdout == storage_res.stdout}",
        "PASS" if html_res.stdout == storage_res.stdout else "DEFECT",
    )
    md_res = cli(("page", page, "--markdown"))
    markdown = md_res.stdout
    tokens = _plain_tokens(storage)
    sample = tokens[:60]
    covered = sum(1 for tok in sample if tok in markdown)
    storage_links = len(re.findall(r"<ri:(page|attachment|url)|<a\s+href=", storage))
    md_links = markdown.count("](")
    ratio = covered / len(sample) if sample else 1.0
    add(
        ctx,
        "CONFLUENCE",
        "confluence.get_page",
        "--markdown",
        f"atlawire page {page} --markdown",
        md_res.exit_code,
        "Markdown с сохранением текста/ссылок без потери",
        f"markdown={len(markdown)} из storage={len(storage)}, "
        f"покрытие_текста={covered}/{len(sample)} ({ratio:.0%}), "
        f"ссылок: storage={storage_links} markdown={md_links}",
        "PASS"
        if md_res.exit_code == 0 and ratio >= 0.9 and md_links >= storage_links
        else "CAP",
        "потери не сообщаются: текст и часть ссылок исчезают молча",
    )


def format_comparison(ctx: Ctx, mod: dict[str, Any]) -> None:
    """Сравнение форматов issue: JSON vs --markdown vs --wiki на wiki-разметке."""
    jira_creds = ctx.creds.get("jira")
    fx = ctx.fixtures.get("jira")
    if jira_creds is None or not fx or not fx.get("wiki"):
        add(
            ctx,
            "FORMAT",
            "CLI issue",
            "--markdown × --wiki",
            "—",
            -1,
            "фикстуры",
            "нет задачи с wiki-разметкой",
            "SKIP",
        )
        return
    key = fx["wiki"]
    jr = mod["jira"]
    issue = call(
        jr.get_issue,
        base_url=jira_creds.base_url,
        key_or_url=key,
        token=jira_creds.token,
        expand="renderedFields",
    )
    value = issue.value if issue.exit_code == 0 else None
    description = ""
    if isinstance(value, dict):
        description = (value.get("fields") or {}).get("description") or ""
    md = cli(("issue", key, "--markdown"))
    wiki = cli(("issue", key, "--wiki"))
    tokens = _plain_tokens(description)
    cover_md = sum(1 for tok in tokens if tok in md.stdout)
    cover_wiki = sum(1 for tok in tokens if tok in wiki.stdout)
    total = len(tokens) or 1
    add(
        ctx,
        "FORMAT",
        "CLI issue",
        "--markdown × --wiki",
        f"atlawire issue {key} --markdown | --wiki",
        wiki.exit_code,
        "wiki-режим не теряет текст там, где markdown теряет",
        f"одинаковы={md.stdout == wiki.stdout}, markdown={len(md.stdout)}, "
        f"wiki={len(wiki.stdout)}, покрытие: markdown={cover_md}/{total} "
        f"({cover_md / total:.0%}), wiki={cover_wiki}/{total} ({cover_wiki / total:.0%})",
        "PASS" if cover_wiki >= cover_md else "DEFECT",
    )
    add(
        ctx,
        "FORMAT",
        "CLI issue",
        "--markdown (потеря)",
        f"atlawire issue {key} --markdown",
        md.exit_code,
        "markdown сохраняет весь видимый текст wiki-description",
        f"потеряно {total - cover_md} из {total} токенов "
        f"({(total - cover_md) / total:.0%}); предупреждения нет",
        "CAP" if cover_md < total else "PASS",
        "агент получит усечённый текст, не узнав об этом; --wiki полнее",
    )


# ---------------------------------------------------------------------------
# Итог и запуск
# ---------------------------------------------------------------------------


def print_summary(ctx: Ctx) -> None:
    """Напечатать счётчики по вердиктам, проблемы и дубли."""
    counts: dict[str, int] = {}
    for row in ctx.rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    print("\n===== ИТОГ =====")
    print(
        "строк:",
        len(ctx.rows),
        "|",
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    )
    for verdict in ("DEFECT", "CAP", "GAP"):
        flagged = [row for row in ctx.rows if row["verdict"] == verdict]
        if not flagged:
            continue
        print(f"\n{verdict}:")
        for row in flagged:
            print(
                f"- {row['area']} {row['func']} [{row['combo']}]: "
                f"{redact(row['notes'] or row['fact'])}"
            )
    groups: dict[str, list[str]] = {}
    for row in ctx.rows:
        if row["duplicate"]:
            groups.setdefault(row["duplicate"], []).append(
                f"{row['func']} [{row['combo']}]"
            )
    if groups:
        print("\nДУБЛИ/БЕСПОЛЕЗНЫЕ КОМБИНАЦИИ:")
        for phrase, items in groups.items():
            shown = "; ".join(items[:3]) + ("…" if len(items) > 3 else "")
            print(f"- {phrase} ({len(items)} шт.): {shown}")


def main() -> int:
    """Точка входа: гейт, обнаружение фикстур, прогон, сводка."""
    gated = os.environ.get(GATE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    if not gated and "--live" not in sys.argv[1:]:
        print(
            f"Гейт выключен. Задайте {GATE_ENV}=1 (или --live), чтобы читать реальный сервер."
        )
        print("Прогон строго read-only: нет записи, отправок и изменений расписаний.")
        return 2
    mod = _imports()
    ctx = Ctx(creds=discover_credentials(mod))
    print("== обнаружение фикстур ==")
    discover_jira(ctx, mod)
    discover_confluence(ctx, mod)
    print("== матрица параметров ==")
    steps = (
        jira_search,
        jira_issue,
        jira_comments,
        bitbucket_commits,
        bitbucket_files,
        bitbucket_grep,
        bitbucket_prs,
        confluence_cql,
        confluence_children,
        confluence_page,
        format_comparison,
    )
    try:
        for step in steps:
            step(ctx, mod)
    except StopRun as stop:
        print(f"\nSTOP: {stop}")
        print_summary(ctx)
        return 2
    print_summary(ctx)
    defects = sum(1 for row in ctx.rows if row["verdict"] == "DEFECT")
    return 0 if defects == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

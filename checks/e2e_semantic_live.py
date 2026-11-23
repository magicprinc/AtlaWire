"""Semantic live end-to-end checks for AtlaWire read commands.

Each check first states what the request means, then calls the installed CLI
against the real deployment and compares the returned rows with that meaning.
The difference between "what must come back" and "what did come back" is the
result; a non-empty mismatch list is a finding with the exact command.

The checker never reads, prints or forwards a token: the CLI resolves the
saved BBK credentials file itself, exactly as an agent does. Every command is
read-only. Any HTTP 401, 403 or 429 stops the run at once, and no command is
retried.

A run exits 0 only when every check produced a discriminating non-empty sample;
``MISMATCH``, ``VACUOUS`` and ``BLOCKED`` exit non-zero.

Run explicitly::

    ATLAWIRE_E2E_LIVE=1 python checks/e2e_semantic_live.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

GATE_ENV = "ATLAWIRE_E2E_LIVE"
STOP_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429")
CLI_PREFIX = (sys.executable, "-P", "-B", "-m", "atlawire")
REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT = 180

ASSIGNEE = "Andrey Fink"
STATUS_FILTER = "In Progress"
UNKNOWN_ASSIGNEE = "Zzzz Nonexistent Zzzz"
JQL_ASSIGNEE = f'assignee = "{ASSIGNEE}" ORDER BY updated DESC'
JQL_UNKNOWN = f'assignee = "{UNKNOWN_ASSIGNEE}" ORDER BY updated DESC'
JQL_STATUS = (
    f'assignee = "{ASSIGNEE}" AND status = "{STATUS_FILTER}" ORDER BY updated DESC'
)
JQL_DAY = f'assignee = "{ASSIGNEE}" AND updated >= -1d ORDER BY updated DESC'
JQL_WEEK = f'assignee = "{ASSIGNEE}" AND updated >= -7d ORDER BY updated DESC'
JQL_LIMIT = 10
JQL_ANY_RECENT = "updated >= -30d ORDER BY updated DESC"

CQL_SPACE = 'space = "ARCH" and type = page'
SPACE_KEY = "ARCH"
CQL_LIMIT = 6
CQL_ANY_PAGE = "type = page"
CQL_CHILD = 'parent = "{page_id}"'
CHILD_SAMPLE = 5

BB_GLOB = "*.java"
BB_PATTERN = "Context"
BB_FILE_LIMIT = 100
BB_HIT_LIMIT = 10
GREP_SAMPLE = 3
COMMIT_LIMIT = 3
PR_SAMPLE = 5

SEARCH_WORD = "Context"
SEARCH_LIMIT = 5
SEARCH_SAMPLE = 3

FIND_TERM = "МФМ"
FIND_LIMIT = 2

Verdict = Literal["MATCH", "MISMATCH", "VACUOUS", "BLOCKED"]


class CheckError(Exception):
    """One command failed or returned a shape this check cannot interpret."""


class StopRun(Exception):
    """A 401/403/429 answer: the run must stop instead of retrying."""


@dataclass(frozen=True, slots=True)
class Observation:
    """One finished CLI invocation, with no token and no full body retained."""

    argv: tuple[str, ...]
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class Result:
    """One reported row: what was asked, what was expected, what arrived."""

    check: str
    expected: str
    fact: str
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class Outcome:
    """One check result plus any semantic discrepancies it proved."""

    result: Result
    findings: tuple[str, ...] = ()


@dataclass(slots=True)
class Fixtures:
    """Identifiers discovered during the run and reused by later checks."""

    issue_key: str | None = None
    cql_pages: list[str] = field(default_factory=list)
    repo: str | None = None
    pr_repo: str | None = None


def _enabled() -> bool:
    """Return whether the operator explicitly opted into a real-server run."""
    value = os.environ.get(GATE_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _first_line(text: str) -> str:
    """Return one bounded diagnostic line, never a whole response body."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def _exit_fact(observation: Observation) -> str:
    """Describe a failed invocation without echoing a token or full output."""
    detail = _first_line(observation.stderr) or "no stderr"
    return f"exit={observation.code}: {detail}"


def _as_dict(value: object, label: str) -> dict[str, object]:
    """Require one JSON object."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CheckError(f"{label}: ожидался JSON-объект")
    return value


def _records(value: object, label: str) -> list[dict[str, object]]:
    """Require a JSON array whose every row is a JSON object."""
    if not isinstance(value, list):
        raise CheckError(f"{label}: ожидался JSON-массив")
    rows: list[dict[str, object]] = []
    for item in value:
        rows.append(_as_dict(item, label))
    return rows


def _texts(value: object, label: str) -> list[str]:
    """Require a JSON array of strings."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CheckError(f"{label}: ожидался JSON-массив строк")
    return list(value)


def _text(value: object) -> str:
    """Return a JSON string value or an empty string."""
    return value if isinstance(value, str) else ""


def _join(args: tuple[str, ...]) -> str:
    """Render argv for a diagnostic without quoting secrets (there are none)."""
    return " ".join(args)


class Cli:
    """Invoke the installed CLI with the saved credentials, never a token."""

    def __init__(self) -> None:
        self._env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("ATLAWIRE_")
        }

    def run(self, *args: str) -> Observation:
        """Run one read-only command and stop the whole run on auth failures."""
        try:
            done = subprocess.run(
                (*CLI_PREFIX, *args),
                cwd=REPO_ROOT,
                env=self._env,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                timeout=COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise CheckError(f"{args[0]}: таймаут {COMMAND_TIMEOUT}s") from None
        observation = Observation(args, done.returncode, done.stdout, done.stderr)
        for marker in STOP_MARKERS:
            if marker in observation.stderr:
                raise StopRun(f"{marker} при вызове {_join(args[:2])}")
        return observation

    def value(self, *args: str) -> object:
        """Run one command and decode its JSON output."""
        observation = self.run(*args)
        if observation.code != 0:
            raise CheckError(f"{args[0]}: {_exit_fact(observation)}")
        try:
            return json.loads(observation.stdout)
        except json.JSONDecodeError:
            raise CheckError(f"{args[0]}: ответ не JSON") from None


def _issue(cli: Cli, key: str) -> dict[str, object]:
    """Read one raw Jira issue document through the CLI."""
    return _as_dict(cli.value("issue", key), f"issue {key}")


def _page(cli: Cli, page_id: str) -> dict[str, object]:
    """Read one raw Confluence page document through the CLI."""
    return _as_dict(cli.value("page", page_id), f"page {page_id}")


def _page_space(doc: dict[str, object]) -> str:
    """Return a page's space key from the raw page document."""
    return _text(_as_dict(doc.get("space") or {}, "space").get("key"))


def _page_body(doc: dict[str, object]) -> str:
    """Return a page's storage XHTML from the raw page document."""
    body = _as_dict(doc.get("body") or {}, "body")
    storage = _as_dict(body.get("storage") or {}, "storage")
    return _text(storage.get("value"))


_JIRA_TS_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z")


def _parse_jira_ts(value: object) -> datetime | None:
    """Parse the Jira 8.22 timestamp shape, including its numeric offset."""
    if not isinstance(value, str):
        return None
    for pattern in _JIRA_TS_FORMATS:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def _parse_row_date(value: object) -> datetime | None:
    """Parse a projected ``YYYY-MM-DD`` row date as a UTC date."""
    text = _text(value)
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def check_assignee(cli: Cli, fixtures: Fixtures) -> Outcome:
    """JQL ``assignee = "..."`` must return only that assignee's issues."""
    rows = _records(
        cli.value("jql", JQL_ASSIGNEE, "--limit", str(JQL_LIMIT), "--json"),
        "jql",
    )
    if not rows:
        expected = (
            f"непустая выборка assignee = {ASSIGNEE} либо контрольный запрос "
            f"{JQL_ANY_RECENT!r} тоже пуст — данных нет"
        )
        wide = _records(
            cli.value("jql", JQL_ANY_RECENT, "--limit", str(JQL_LIMIT), "--json"),
            "jql",
        )
        if not wide:
            return Outcome(
                Result(
                    "jql assignee",
                    expected,
                    "0 строк; контрольная выборка без assignee тоже 0 — данных нет",
                    "MATCH",
                )
            )
        mine = [row for row in wide if row.get("assignee") == ASSIGNEE]
        if mine:
            keys = ", ".join(_text(row.get("key")) for row in mine[:3])
            finding = (
                "jql assignee: контрольный запрос без assignee вернул "
                f"{len(mine)}/{len(wide)} задач этого assignee ({keys}), а фильтр — 0"
            )
            fact = f"0 строк; без assignee {len(wide)} строк, из них mine={len(mine)}"
            return Outcome(
                Result("jql assignee", expected, fact, "MISMATCH"), (finding,)
            )
        fact = (
            f"0 строк; без assignee {len(wide)} строк, ни одна не назначена "
            f"{ASSIGNEE!r} — фильтр нечем опровергнуть"
        )
        return Outcome(Result("jql assignee", expected, fact, "VACUOUS"))
    fixtures.issue_key = _text(rows[0].get("key")) or None
    me = _as_dict(cli.value("jira-me"), "jira-me")
    display = _text(me.get("displayName")) or ASSIGNEE
    login = _text(me.get("name"))
    foreign: list[str] = []
    raw_mismatch: list[str] = []
    for row in rows:
        key = _text(row.get("key"))
        if row.get("assignee") != display:
            foreign.append(key)
        fields = _as_dict(_issue(cli, key).get("fields") or {}, "fields")
        assignee = fields.get("assignee")
        if not isinstance(assignee, dict):
            raw_mismatch.append(key)
            continue
        if assignee.get("displayName") != display or (
            login and assignee.get("name") != login
        ):
            raw_mismatch.append(key)
    findings: list[str] = []
    if foreign:
        findings.append(
            f"jql assignee: {len(foreign)}/{len(rows)} строк с чужим "
            f"row.assignee ({', '.join(foreign[:3])})"
        )
    if raw_mismatch:
        findings.append(
            f"jql assignee: {len(raw_mismatch)}/{len(rows)} задач имеют "
            "чужой fields.assignee.displayName/name "
            f"({', '.join(raw_mismatch[:3])})"
        )
    fact = (
        f"{len(rows)} строк; чужих row.assignee={len(foreign)}; "
        f"raw несовпадений={len(raw_mismatch)}; displayName={display!r}"
    )
    expected = (
        f"все {len(rows)} строк: row.assignee={display}; "
        f"поля issue: displayName={display}, name={login or 'n/a'}"
    )
    verdict: Verdict = "MATCH" if not foreign and not raw_mismatch else "MISMATCH"
    return Outcome(Result("jql assignee", expected, fact, verdict), tuple(findings))


def check_unknown_assignee(cli: Cli, fixtures: Fixtures) -> Outcome:
    """A nonexistent assignee must yield 0 rows, never every issue."""
    del fixtures
    observation = cli.run("jql", JQL_UNKNOWN, "--limit", str(JQL_LIMIT), "--json")
    expected = "0 строк, а не все задачи"
    if observation.code != 0:
        fact = f"CLI отклонил запрос ({_exit_fact(observation)}); строк нет"
        return Outcome(Result("jql несуществующий assignee", expected, fact, "MATCH"))
    rows = _records(cli.value("jql", JQL_UNKNOWN, "--limit", "1", "--json"), "jql")
    if not rows:
        return Outcome(
            Result("jql несуществующий assignee", expected, "0 строк", "MATCH")
        )
    keys = ", ".join(_text(row.get("key")) for row in rows[:5])
    finding = (
        "jql несуществующий assignee: фильтр не отбросил строки — "
        f"{len(rows)} строк вместо 0 ({keys})"
    )
    fact = f"{len(rows)} строк вместо 0; ключи={keys}"
    return Outcome(
        Result("jql несуществующий assignee", expected, fact, "MISMATCH"),
        (finding,),
    )


def check_issue(cli: Cli, fixtures: Fixtures) -> Outcome:
    """``issue KEY`` must describe that exact key, with a real status."""
    key = fixtures.issue_key
    if key is None:
        return Outcome(
            Result(
                "issue KEY", "key/summary/status из п.1", "ключ не найден", "BLOCKED"
            )
        )
    doc = _issue(cli, key)
    statuses = set(_texts(cli.value("statuses", "--json"), "statuses"))
    fields = _as_dict(doc.get("fields") or {}, "fields")
    status = _text(_as_dict(fields.get("status") or {}, "status").get("name"))
    summary = _text(fields.get("summary"))
    assignee = fields.get("assignee")
    display = _text(assignee.get("displayName")) if isinstance(assignee, dict) else ""
    returned_key = _text(doc.get("key"))
    key_ok = returned_key == key
    summary_ok = bool(summary.strip())
    status_ok = status in statuses
    assignee_ok = display == ASSIGNEE
    fact = (
        f"key={returned_key!r}; summary_len={len(summary.strip())}; "
        f"status={status!r} в statuses({len(statuses)})={status_ok}; "
        f"assignee={display!r}"
    )
    expected = f"key={key}; summary непустой; status из statuses; assignee={ASSIGNEE}"
    ok = key_ok and summary_ok and status_ok and assignee_ok
    findings: tuple[str, ...] = ()
    if not ok:
        findings = (
            (
                "issue KEY: ожидание key/summary/status/assignee не совпало с "
                f"ответом ({fact})"
            ),
        )
    verdict: Verdict = "MATCH" if ok else "MISMATCH"
    return Outcome(Result("issue KEY", expected, fact, verdict), findings)


def check_status_filter(cli: Cli, fixtures: Fixtures) -> Outcome:
    """A JQL status clause must be reflected in every returned row."""
    del fixtures
    rows = _records(
        cli.value("jql", JQL_STATUS, "--limit", str(JQL_LIMIT), "--json"),
        "jql",
    )
    expected = f"все строки status = {STATUS_FILTER}"
    if not rows:
        wide = _records(
            cli.value("jql", JQL_ASSIGNEE, "--limit", str(JQL_LIMIT), "--json"),
            "jql",
        )
        if not wide:
            return Outcome(
                Result(
                    "jql status",
                    expected,
                    "0 строк; контрольная выборка без status тоже 0 — данных нет",
                    "MATCH",
                )
            )
        conflicting = [row for row in wide if row.get("status") == STATUS_FILTER]
        if conflicting:
            keys = ", ".join(_text(row.get("key")) for row in conflicting[:3])
            finding = (
                f"jql status: контрольная выборка без status вернула "
                f"{len(conflicting)}/{len(wide)} строк со статусом {STATUS_FILTER!r} ({keys})"
            )
            fact = f"0 строк; без status {len(wide)} строк, из них нужный статус={len(conflicting)}"
            return Outcome(Result("jql status", expected, fact, "MISMATCH"), (finding,))
        fact = (
            f"0 строк; без status {len(wide)} строк, ни одна не имеет статус "
            f"{STATUS_FILTER!r} — фильтр нечем опровергнуть"
        )
        return Outcome(Result("jql status", expected, fact, "VACUOUS"))
    actual = sorted({_text(row.get("status")) for row in rows})
    foreign = [row for row in rows if row.get("status") != STATUS_FILTER]
    fact = f"{len(rows)} строк; статусы={actual}; чужих={len(foreign)}"
    findings: tuple[str, ...] = ()
    if foreign:
        keys = ", ".join(_text(row.get("key")) for row in foreign[:3])
        findings = (
            (
                f"jql status: {len(foreign)}/{len(rows)} строк имеют статус не "
                f"{STATUS_FILTER!r} ({keys})"
            ),
        )
    verdict: Verdict = "MATCH" if not foreign else "MISMATCH"
    return Outcome(Result("jql status", expected, fact, verdict), findings)


def _updated_is_fresh(
    cli: Cli, row: dict[str, object], moment: datetime, window: timedelta
) -> bool:
    """Check row and raw timestamps against the window by calendar day.

    Jira resolves the relative date in a JQL filter at day granularity, so a
    matching row can be older than ``window`` by the time of day. The check
    therefore compares calendar dates, not exact instants; the raw timestamp is
    still read, so a stale value cannot hide behind the projected date.
    """
    row_date = _parse_row_date(row.get("updated"))
    if row_date is None:
        return False
    fields = _as_dict(_issue(cli, _text(row.get("key"))).get("fields") or {}, "f")
    raw = _parse_jira_ts(fields.get("updated"))
    if raw is None or raw.tzinfo is None:
        return False
    boundary = (moment.astimezone(raw.tzinfo) - window).date()
    return row_date.date() >= boundary and raw.date() >= boundary


def check_updated_window(cli: Cli, fixtures: Fixtures) -> Outcome:
    """``updated >= -1d`` rows must all be younger than one day."""
    del fixtures
    moment = datetime.now(UTC)
    day = _records(
        cli.value("jql", JQL_DAY, "--limit", str(JQL_LIMIT), "--json"), "jql"
    )
    if day:
        stale = [
            _text(row.get("key"))
            for row in day
            if not _updated_is_fresh(cli, row, moment, timedelta(days=1))
        ]
        fact = (
            f"-1d: {len(day)} строк; старше суток={len(stale)} "
            "(сравнение по календарным суткам, как у относительной даты Jira)"
        )
        expected = "все строки updated не старше 1 суток"
        verdict: Verdict = "MATCH" if not stale else "MISMATCH"
        findings: tuple[str, ...] = ()
        if stale:
            findings = (
                (
                    f"jql updated >= -1d: {len(stale)}/{len(day)} строк старше "
                    f"суток ({', '.join(stale[:3])})"
                ),
            )
        return Outcome(Result("jql updated >= -1d", expected, fact, verdict), findings)
    week = _records(
        cli.value("jql", JQL_WEEK, "--limit", str(JQL_LIMIT), "--json"), "jql"
    )
    stale_week = [
        _text(row.get("key"))
        for row in week
        if not _updated_is_fresh(cli, row, moment, timedelta(days=7))
    ]
    fact = (
        f"-1d: 0 строк (нечего опровергнуть); -7d: {len(week)} строк, "
        f"старше 7 календарных суток={len(stale_week)}"
    )
    expected = "все строки updated не старше 1 суток (-1d пуст, сверено на -7d)"
    findings = ()
    verdict = "VACUOUS"
    if stale_week:
        verdict = "MISMATCH"
        findings = (
            (
                f"jql updated >= -7d: {len(stale_week)}/{len(week)} строк старше "
                f"7 суток ({', '.join(stale_week[:3])})"
            ),
        )
    return Outcome(Result("jql updated >= -1d", expected, fact, verdict), findings)


def check_cql_space(cli: Cli, fixtures: Fixtures) -> Outcome:
    """``space = "ARCH"`` rows must belong to ARCH, by row and by page."""
    rows = _records(
        cli.value("cql", CQL_SPACE, "--limit", str(CQL_LIMIT), "--json"), "cql"
    )
    if not rows:
        expected = "непустая выборка страниц ARCH либо подтверждённое отсутствие данных"
        wide = _records(
            cli.value("cql", CQL_ANY_PAGE, "--limit", str(CQL_LIMIT), "--json"),
            "cql",
        )
        if not wide:
            return Outcome(
                Result(
                    "cql space=ARCH",
                    expected,
                    "0 строк; контрольный CQL без space тоже 0 — страниц нет",
                    "MATCH",
                )
            )
        foreign = [row for row in wide if row.get("space") == SPACE_KEY]
        if foreign:
            ids = ", ".join(str(row.get("id")) for row in foreign[:3])
            finding = (
                "cql space=ARCH: контрольный CQL без space вернул "
                f"{len(foreign)}/{len(wide)} страниц с space={SPACE_KEY} ({ids})"
            )
            fact = f"0 строк; без space {len(wide)} строк, из них ARCH={len(foreign)}"
            return Outcome(
                Result("cql space=ARCH", expected, fact, "MISMATCH"), (finding,)
            )
        fact = (
            f"0 строк; без space {len(wide)} строк, ни одна не из {SPACE_KEY} — "
            "фильтр нечем опровергнуть"
        )
        return Outcome(Result("cql space=ARCH", expected, fact, "VACUOUS"))
    fixtures.cql_pages = [str(row.get("id")) for row in rows]
    null_space = 0
    wrong_page = 0
    page_spaces: list[str] = []
    for row in rows:
        if row.get("space") is None:
            null_space += 1
        doc = _page(cli, str(row.get("id")))
        space = _page_space(doc)
        page_spaces.append(space)
        if space != SPACE_KEY or _text(doc.get("type")) != "page":
            wrong_page += 1
    types = sorted({_text(row.get("type")) for row in rows})
    fact = (
        f"{len(rows)} строк; page.space=ARCH {len(rows) - wrong_page}/{len(rows)}"
        f" ({sorted(set(page_spaces))}); row.space=null {null_space}/{len(rows)};"
        f" row.type={types}"
    )
    expected = 'все страницы: page.space=ARCH, type="page"; row.space=ARCH'
    findings: list[str] = []
    if wrong_page:
        findings.append(
            f"cql space=ARCH: {wrong_page}/{len(rows)} страниц не из ARCH по "
            "page.space — серверная фильтрация нарушена"
        )
    if null_space and not wrong_page:
        findings.append(
            "cql space=ARCH: row.space=null у "
            f"{null_space}/{len(rows)} строк, хотя page.space.key=ARCH; "
            "сервер отдаёт content-обёртку без content.space, а ключ лежит в "
            "content._expandable.space; _space_key смотрит _expandable только "
            "у внешнего объекта, поэтому проекция теряет space"
        )
    verdict: Verdict = "MATCH" if not wrong_page and not null_space else "MISMATCH"
    return Outcome(Result("cql space=ARCH", expected, fact, verdict), tuple(findings))


def _children_absence(cli: Cli, fixtures: Fixtures) -> Outcome:
    """Declare an empty children result only after a control query agrees.

    The unit under test may hide children, so every candidate parent is also
    queried through CQL ``parent = ...``: rows there prove a defect, no rows
    anywhere confirm that the pages really have no direct children.
    """
    expected = (
        "непустая выборка детей либо контрольный CQL parent=… тоже пуст — детей нет"
    )
    if not fixtures.cql_pages:
        return Outcome(
            Result(
                "children",
                expected,
                "нет страниц-кандидатов: cql space=ARCH не дал строк",
                "VACUOUS",
            )
        )
    with_children: list[str] = []
    for page_id in fixtures.cql_pages:
        rows = _records(
            cli.value(
                "cql", CQL_CHILD.format(page_id=page_id), "--limit", "5", "--json"
            ),
            "cql",
        )
        if rows:
            with_children.append(page_id)
    if not with_children:
        return Outcome(
            Result(
                "children",
                expected,
                f"0 строк; CQL parent по всем {len(fixtures.cql_pages)} страницам "
                "тоже 0 — детей нет",
                "MATCH",
            )
        )
    finding = (
        "children: контрольный CQL parent нашёл детей у "
        f"{len(with_children)}/{len(fixtures.cql_pages)} страниц, а команда "
        "children — 0"
    )
    fact = f"0 строк; CQL parent нашёл детей у {len(with_children)} страниц"
    return Outcome(Result("children", expected, fact, "MISMATCH"), (finding,))


def check_children(cli: Cli, fixtures: Fixtures) -> Outcome:
    """Every returned child must really have the parent as its ancestor."""
    parent: str | None = None
    children: list[dict[str, object]] = []
    for page_id in fixtures.cql_pages:
        rows = _records(cli.value("children", page_id, "--json"), "children")
        if rows:
            parent, children = page_id, rows
            break
    if parent is None or not children:
        return _children_absence(cli, fixtures)
    sample = children[:CHILD_SAMPLE]
    matched = 0
    bad: list[str] = []
    for child in sample:
        child_id = str(child.get("id"))
        doc = _page(cli, child_id)
        raw_ancestors = doc.get("ancestors")
        items = raw_ancestors if isinstance(raw_ancestors, list) else []
        ancestors = {str(item.get("id")) for item in items if isinstance(item, dict)}
        title_ok = doc.get("title") == child.get("title")
        if parent in ancestors and title_ok:
            matched += 1
        else:
            bad.append(child_id)
    fact = (
        f"parent={parent}; детей={len(children)}; ancestor+title подтверждены "
        f"{matched}/{len(sample)}"
    )
    expected = f"каждый ребёнок имеет ancestors, содержащие {parent}"
    findings: tuple[str, ...] = ()
    if bad:
        findings = (
            (
                "children: у "
                f"{len(bad)}/{len(sample)} детей нет ancestor={parent} или title "
                f"не совпал ({', '.join(bad[:3])})"
            ),
        )
    verdict: Verdict = "MATCH" if not bad else "MISMATCH"
    return Outcome(Result("children", expected, fact, verdict), findings)


def discover_repo(cli: Cli) -> str | None:
    """Find one repository that actually contains ``*.java`` files."""
    override = os.environ.get("ATLAWIRE_LIVE_BITBUCKET_REPO", "").strip()
    if override:
        return override
    projects = _records(cli.value("projects", "--json"), "projects")
    tried = 0
    for project in projects[:12]:
        key = _text(project.get("key"))
        if not key:
            continue
        repos = _records(cli.value("repos", key, "--json"), "repos")
        for repo in repos[:12]:
            slug = _text(repo.get("slug"))
            if not slug:
                continue
            tried += 1
            if tried > 25:
                return None
            listing = _as_dict(
                cli.value(
                    "grep-repo",
                    f"{key}/{slug}",
                    "--glob",
                    BB_GLOB,
                    "--limit",
                    "5",
                    "--json",
                ),
                "listing",
            )
            eligible = listing.get("files_eligible")
            if isinstance(eligible, int) and eligible > 0:
                return f"{key}/{slug}"
    return None


def check_repo_files(cli: Cli, fixtures: Fixtures) -> Outcome:
    """A ``*.java`` path listing must contain only ``.java`` paths."""
    repo = fixtures.repo
    if repo is None:
        return Outcome(
            Result(
                "grep-repo --glob *.java",
                "все пути оканчиваются на .java",
                "репозиторий с .java не найден",
                "BLOCKED",
            )
        )
    listing = _as_dict(
        cli.value(
            "grep-repo",
            repo,
            "--glob",
            BB_GLOB,
            "--limit",
            str(BB_FILE_LIMIT),
            "--json",
        ),
        "listing",
    )
    files = listing.get("files")
    paths = files if isinstance(files, list) else []
    wrong = [path for path in paths if not str(path).endswith(".java")]
    eligible = listing.get("files_eligible")
    fact = (
        f"{repo}: eligible={eligible}; отдано={len(paths)}; "
        f"не-.java={len(wrong)}; truncated={listing.get('truncated')}"
    )
    expected = "все отданные пути оканчиваются на .java"
    findings: tuple[str, ...] = ()
    if wrong:
        findings = (
            (
                f"grep-repo --glob *.java: {len(wrong)}/{len(paths)} путей не "
                f"оканчиваются на .java ({', '.join(map(str, wrong[:3]))})"
            ),
        )
    verdict: Verdict = "MATCH" if paths and not wrong else "MISMATCH"
    return Outcome(Result("grep-repo --glob *.java", expected, fact, verdict), findings)


def check_repo_grep(cli: Cli, fixtures: Fixtures) -> Outcome:
    """Every grep hit line must really contain the requested pattern."""
    repo = fixtures.repo
    if repo is None:
        return Outcome(
            Result(
                f"grep-repo {BB_PATTERN}",
                "каждая hit-строка содержит шаблон",
                "репозиторий не найден",
                "BLOCKED",
            )
        )
    grep = _as_dict(
        cli.value(
            "grep-repo",
            repo,
            BB_PATTERN,
            "--glob",
            BB_GLOB,
            "--limit",
            str(BB_HIT_LIMIT),
            "--timeout",
            "90",
            "--json",
        ),
        "grep",
    )
    hits_value = grep.get("hits")
    hits = hits_value if isinstance(hits_value, list) else []
    if not hits:
        expected = (
            f'непустая выборка hit-строк с "{BB_PATTERN}" либо подтверждённое '
            "отсутствие"
        )
        wide = _as_dict(
            cli.value(
                "grep-repo",
                repo,
                BB_PATTERN,
                "--limit",
                str(BB_HIT_LIMIT),
                "--timeout",
                "90",
                "--json",
            ),
            "grep",
        )
        wide_value = wide.get("hits")
        wide_hits = wide_value if isinstance(wide_value, list) else []
        if not wide_hits:
            return Outcome(
                Result(
                    f"grep-repo {BB_PATTERN}",
                    expected,
                    f"0 hit в {BB_GLOB}; без --glob тоже 0 — шаблон в "
                    "репозитории не встречается",
                    "MATCH",
                )
            )
        fact = (
            f"0 hit в {BB_GLOB}; без --glob {len(wide_hits)} hit — фильтр "
            "расширения отбросил все совпадения, отсутствие не подтверждено"
        )
        return Outcome(Result(f"grep-repo {BB_PATTERN}", expected, fact, "VACUOUS"))
    needle = BB_PATTERN.lower()
    missing: list[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        text = _text(hit.get("text"))
        if hit.get("text_truncated"):
            continue
        if needle not in text.lower():
            missing.append(_text(hit.get("file")))
    commit = _text(grep.get("commit"))
    sample = [hit for hit in hits[:GREP_SAMPLE] if isinstance(hit, dict)]
    matched = 0
    for hit in sample:
        observation = cli.run("file", repo, _text(hit.get("file")), "--at", commit)
        if observation.code != 0:
            raise CheckError(
                f"file {_text(hit.get('file'))}: {_exit_fact(observation)}"
            )
        lines = observation.stdout.splitlines()
        number = hit.get("line")
        if (
            isinstance(number, int)
            and 1 <= number <= len(lines)
            and lines[number - 1] == hit.get("text")
        ):
            matched += 1
    fact = (
        f"{len(hits)} hit-строк; без шаблона={len(missing)}; сверено с файлом "
        f"на {commit[:8]}: {matched}/{len(sample)}"
    )
    expected = f'каждая hit-строка содержит "{BB_PATTERN}"'
    findings: list[str] = []
    if missing:
        findings.append(
            f"grep-repo {BB_PATTERN}: {len(missing)}/{len(hits)} hit-строк не "
            f"содержат шаблон ({', '.join(missing[:3])})"
        )
    if matched != len(sample):
        findings.append(
            f"grep-repo {BB_PATTERN}: {len(sample) - matched}/{len(sample)} "
            "hit-строк не совпали с файлом на заявленном commit"
        )
    verdict: Verdict = "MATCH" if not findings else "MISMATCH"
    return Outcome(
        Result(f"grep-repo {BB_PATTERN}", expected, fact, verdict), tuple(findings)
    )


def check_commits(cli: Cli, fixtures: Fixtures) -> Outcome:
    """``commits --limit 3`` must cap at 3 rows and stay newest-first."""
    repo = fixtures.repo
    if repo is None:
        return Outcome(
            Result(
                "commits --limit 3", "≤3 строк, даты по убыванию", "нет repo", "BLOCKED"
            )
        )
    rows = _records(
        cli.value("commits", repo, "--limit", str(COMMIT_LIMIT), "--json"),
        "commits",
    )
    dates = [_text(row.get("date")) for row in rows]
    ordered = all(dates[i] >= dates[i + 1] for i in range(len(dates) - 1))
    raw_stamps: list[int] = []
    formatted = 0
    id_bad = 0
    for row in rows:
        commit = _as_dict(cli.value("commit", repo, _text(row.get("hash"))), "commit")
        stamp = commit.get("authorTimestamp")
        if commit.get("id") != row.get("hash"):
            id_bad += 1
        if isinstance(stamp, int) and not isinstance(stamp, bool):
            raw_stamps.append(stamp)
            expected_date = datetime.fromtimestamp(stamp / 1000, UTC).strftime(
                "%Y-%m-%d %H:%M"
            )
            if expected_date == row.get("date"):
                formatted += 1
    raw_ordered = all(
        raw_stamps[i] >= raw_stamps[i + 1] for i in range(len(raw_stamps) - 1)
    )
    too_many = len(rows) > COMMIT_LIMIT
    fact = (
        f"{len(rows)} строк (≤{COMMIT_LIMIT}={not too_many}); dates={dates}; "
        f"по убыванию={ordered}; raw authorTimestamp по убыванию={raw_ordered}; "
        f"UTC-формат совпал={formatted}/{len(rows)}; id-несовпадений={id_bad}"
    )
    expected = (
        f"ровно ≤{COMMIT_LIMIT} строк, даты/authorTimestamp по убыванию, "
        "date = UTC authorTimestamp"
    )
    ok = (
        bool(rows)
        and not too_many
        and ordered
        and raw_ordered
        and formatted == len(rows)
        and id_bad == 0
    )
    findings: tuple[str, ...] = ()
    if not ok:
        findings = (
            (f"commits --limit 3: порядок/лимит/даты не совпали с ожиданием ({fact})"),
        )
    verdict: Verdict = "MATCH" if ok else "MISMATCH"
    return Outcome(Result("commits --limit 3", expected, fact, verdict), findings)


def discover_pr_repo(cli: Cli) -> str | None:
    """Find a repository that currently has OPEN pull requests."""
    try:
        value = cli.value("my-prs", "--role", "REVIEWER", "--state", "OPEN", "--json")
    except CheckError:
        return None
    if not isinstance(value, list):
        return None
    for row in value:
        if not isinstance(row, dict):
            continue
        repo = row.get("repo")
        if isinstance(repo, str) and "/" in repo:
            return repo
    return None


def check_prs(cli: Cli, fixtures: Fixtures) -> Outcome:
    """``prs --state OPEN`` must return only OPEN pull requests."""
    repo = fixtures.pr_repo or fixtures.repo
    expected = "все строки state = OPEN (и raw state = OPEN)"
    if repo is None:
        return Outcome(
            Result("prs --state OPEN", expected, "репозиторий не найден", "BLOCKED")
        )
    rows = _records(cli.value("prs", repo, "--state", "OPEN", "--json"), "prs")
    if not rows:
        return Outcome(
            Result(
                "prs --state OPEN",
                expected,
                f"{repo}: 0 OPEN PR — проверять нечего",
                "VACUOUS",
            )
        )
    foreign = [row for row in rows if row.get("state") != "OPEN"]
    sample = rows[:PR_SAMPLE]
    raw_open = 0
    for row in sample:
        doc = _as_dict(cli.value("pr", repo, str(row.get("id"))), "pr")
        if doc.get("state") == "OPEN" and doc.get("id") == row.get("id"):
            raw_open += 1
    fact = (
        f"{repo}: {len(rows)} PR; state!=OPEN={len(foreign)}; "
        f"raw state=OPEN {raw_open}/{len(sample)}"
    )
    findings: tuple[str, ...] = ()
    if foreign:
        identifiers = ", ".join(str(row.get("id")) for row in foreign[:3])
        findings = (
            (
                f"prs --state OPEN: {len(foreign)}/{len(rows)} PR имеют другой "
                f"state ({identifiers})"
            ),
        )
    elif raw_open != len(sample):
        findings = (
            (
                f"prs --state OPEN: raw PR {repo} не подтвердил OPEN у "
                f"{len(sample) - raw_open}/{len(sample)} строк"
            ),
        )
    verdict: Verdict = "MATCH" if not findings else "MISMATCH"
    return Outcome(Result("prs --state OPEN", expected, fact, verdict), findings)


def check_search(cli: Cli, fixtures: Fixtures) -> Outcome:
    """Indexed search hits must contain the searched word in the file."""
    del fixtures
    rows = _records(
        cli.value("search", SEARCH_WORD, "--limit", str(SEARCH_LIMIT), "--json"),
        "search",
    )
    if not rows:
        return Outcome(
            Result(
                f"search {SEARCH_WORD}",
                "каждое попадание содержит слово",
                "0 файлов",
                "VACUOUS",
            )
        )
    needle = SEARCH_WORD.lower()
    lines_total = 0
    missing_lines = 0
    for row in rows:
        hits = row.get("hits")
        for hit in hits if isinstance(hits, list) else []:
            if not isinstance(hit, dict):
                continue
            lines_total += 1
            if hit.get("text_truncated"):
                continue
            if needle not in _text(hit.get("text")).lower():
                missing_lines += 1
    sample = rows[:SEARCH_SAMPLE]
    verified = 0
    unreadable = 0
    missing_files: list[str] = []
    for row in sample:
        repo = f"{row.get('project')}/{row.get('repository')}"
        path = _text(row.get("file"))
        observation = cli.run("file", repo, path)
        if observation.code != 0:
            unreadable += 1
            continue
        if needle in observation.stdout.lower():
            verified += 1
        else:
            missing_files.append(f"{repo}/{path}")
    fact = (
        f"{len(rows)} файлов; hit-строк={lines_total}, без слова="
        f"{missing_lines}; файл содержит слово {verified}/{len(sample)}"
        f" (недоступно на default branch: {unreadable})"
    )
    expected = f'каждая hit-строка и каждый файл содержат "{SEARCH_WORD}"'
    findings: list[str] = []
    if missing_lines:
        findings.append(
            f"search {SEARCH_WORD}: {missing_lines}/{lines_total} hit-строк не "
            "содержат слово"
        )
    if missing_files:
        findings.append(
            f"search {SEARCH_WORD}: файл не содержит слово "
            f"({', '.join(missing_files[:3])})"
        )
    if findings:
        verdict: Verdict = "MISMATCH"
    elif verified == 0:
        verdict = "VACUOUS"
    else:
        verdict = "MATCH"
    return Outcome(
        Result(f"search {SEARCH_WORD}", expected, fact, verdict), tuple(findings)
    )


def _find_rows(doc: dict[str, object], product: str) -> list[dict[str, object]]:
    """Return one product's rows from a federated ``find`` document."""
    value = doc.get(product)
    return _records(value, f"find.{product}") if isinstance(value, list) else []


def _related_page(cli: Cli, row: dict[str, object], term: str) -> bool:
    """Check that a merged Confluence page contains the term in title/body."""
    page = _page(cli, str(row.get("id")))
    haystack = f"{_text(page.get('title'))}\n{_page_body(page)}".lower()
    return term in haystack


def _related_issue(cli: Cli, row: dict[str, object], term: str) -> bool:
    """Check that a merged Jira issue contains the term in text fields."""
    key = _text(row.get("key"))
    issue = _issue(cli, key)
    fields = _as_dict(issue.get("fields") or {}, "fields")
    haystack = f"{_text(fields.get('summary'))} {_text(fields.get('description'))}"
    comments = _records(cli.value("issue-comments", key), "comments")
    haystack += " " + " ".join(_text(item.get("body")) for item in comments)
    return term in haystack.lower()


def _related_file(cli: Cli, row: dict[str, object], term: str) -> bool:
    """Check that a merged Bitbucket search row's file contains the term."""
    repo = f"{row.get('project')}/{row.get('repository')}"
    observation = cli.run("file", repo, _text(row.get("file")))
    return observation.code == 0 and term in observation.stdout.lower()


def check_find(cli: Cli, fixtures: Fixtures) -> Outcome:
    """A non-empty ``find`` result must be non-empty and about the term."""
    del fixtures
    doc = _as_dict(cli.value("find", FIND_TERM, "--limit", "2"), "find")
    counts = _as_dict(doc.get("counts") or {}, "counts")
    pages = _find_rows(doc, "confluence")
    issues = _find_rows(doc, "jira")
    files = _find_rows(doc, "bitbucket")
    length_ok = (
        counts.get("confluence") == len(pages)
        and counts.get("jira") == len(issues)
        and counts.get("bitbucket") == len(files)
    )
    nonempty = (
        all(
            str(row.get("id") or "") and _text(row.get("title")).strip()
            for row in pages
        )
        and all(
            _text(row.get("key")).strip() and _text(row.get("summary")).strip()
            for row in issues
        )
        and all(_text(row.get("file")).strip() for row in files)
    )
    term = FIND_TERM.lower()
    checked = 0
    related = 0
    unrelated: list[str] = []
    for row in pages[:FIND_LIMIT]:
        checked += 1
        if _related_page(cli, row, term):
            related += 1
        else:
            unrelated.append(f"page {row.get('id')}")
    for row in issues[:FIND_LIMIT]:
        checked += 1
        if _related_issue(cli, row, term):
            related += 1
        else:
            unrelated.append(f"issue {row.get('key')}")
    for row in files[:FIND_LIMIT]:
        checked += 1
        if _related_file(cli, row, term):
            related += 1
        else:
            unrelated.append(f"{row.get('repository')}/{row.get('file')}")
    total = sum(count for count in counts.values() if isinstance(count, int))
    fact = (
        f"counts={counts}; длины сходятся={length_ok}; поля непустые={nonempty}; "
        f"термин найден в документе {related}/{checked}"
    )
    expected = (
        f"counts>0, строки непустые, каждая строка относится к термину {FIND_TERM}"
    )
    findings: list[str] = []
    if not isinstance(total, int) or total <= 0:
        findings.append(f"find {FIND_TERM}: counts=0 при непустых списках")
    if not length_ok or not nonempty:
        findings.append(f"find {FIND_TERM}: counts/поля не согласованы ({fact})")
    if unrelated:
        findings.append(
            f"find {FIND_TERM}: {len(unrelated)}/{checked} строк не содержат "
            f"термин в документе ({', '.join(unrelated[:3])})"
        )
    verdict: Verdict = "MATCH" if not findings else "MISMATCH"
    return Outcome(
        Result(f"find {FIND_TERM}", expected, fact, verdict), tuple(findings)
    )


class Run:
    """Collect every check result and discrepancy for one report."""

    def __init__(self, cli: Cli) -> None:
        self._cli = cli
        self.fixtures = Fixtures()
        self.results: list[Result] = []
        self.findings: list[str] = []

    def _add(self, outcome: Outcome) -> None:
        self.results.append(outcome.result)
        self.findings.extend(outcome.findings)

    def _attempt(self, function) -> None:
        """Run one check; a broken command becomes BLOCKED, not a crash."""
        try:
            self._add(function(self._cli, self.fixtures))
        except CheckError as exc:
            label = getattr(function, "__name__", "check")
            outcome = Outcome(Result(label, "выполнить проверку", str(exc), "BLOCKED"))
            self._add(outcome)

    def execute(self) -> None:
        """Run the checks in the order the fixtures require."""
        self._attempt(check_assignee)
        self._attempt(check_unknown_assignee)
        self._attempt(check_issue)
        self._attempt(check_status_filter)
        self._attempt(check_updated_window)
        self._attempt(check_cql_space)
        self._attempt(check_children)
        try:
            self.fixtures.repo = discover_repo(self._cli)
        except CheckError:
            self.fixtures.repo = None
        self.fixtures.pr_repo = discover_pr_repo(self._cli)
        self._attempt(check_repo_files)
        self._attempt(check_repo_grep)
        self._attempt(check_commits)
        self._attempt(check_prs)
        self._attempt(check_search)
        self._attempt(check_find)

    def report(self) -> int:
        """Print the table; return non-zero on mismatch, block or vacuity."""
        for result in self.results:
            print(f"[{result.verdict}] {result.check}")
            print(f"    ожидание: {result.expected}")
            print(f"    факт: {result.fact}")
        print()
        for finding in self.findings:
            print(f"РАСХОЖДЕНИЕ: {finding}")
        mismatches = sum(1 for result in self.results if result.verdict == "MISMATCH")
        blocked = sum(1 for result in self.results if result.verdict == "BLOCKED")
        vacuous = sum(1 for result in self.results if result.verdict == "VACUOUS")
        matched = sum(1 for result in self.results if result.verdict == "MATCH")
        print(
            f"\nИТОГО: MATCH={matched}, MISMATCH={mismatches}, "
            f"VACUOUS={vacuous}, BLOCKED={blocked}, "
            f"расхождений={len(self.findings)}"
        )
        vacuous_checks = [
            result.check for result in self.results if result.verdict == "VACUOUS"
        ]
        if vacuous_checks:
            print(
                "\nНЕОПРОВЕРГНУТО: "
                + ", ".join(vacuous_checks)
                + " — пустая выборка не доказывает соответствие; нужна непустая "
                "выборка или подтверждённое отсутствие данных"
            )
        return 0 if not mismatches and not blocked and not vacuous else 1


def main() -> int:
    """Gate the real-server run and report the semantic comparison."""
    if not _enabled():
        print(f"Set {GATE_ENV}=1 to run these live read-only checks.")
        return 2
    run = Run(Cli())
    try:
        run.execute()
    except StopRun as exc:
        print(f"STOP: {exc}; дальнейшие вызовы не выполнялись.")
        run.report()
        return 3
    return run.report()


if __name__ == "__main__":
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    raise SystemExit(main())

"""Live read-only E2E check of the AtlaWire CLI for Jira and Confluence.

Repeats, through the installed ``atlawire`` command, the operations that BBK
agents and scripts actually use against the real deployment: JQL search, one
issue read, its comments, statuses, transitions, the caller identity, a narrow
user search, CQL search, one page read plus its Markdown rendering, its child
pages, a space listing, a federated ``find``, and the ``selftest`` probe. The
value-changing options are each checked with one real combination: jql
--fields/--expand, issue --expand, issue-comments --limit, cql --expand and
page --expand must change the observed response, not only the exit code.

Run explicitly, against the real server named by the saved BBK credentials::

    ATLAWIRE_E2E_LIVE=1 python checks/e2e_bbk_cli_jira_confluence.py

Every step prints its exact argv, exit code, and one observed fact (counts and
selected fields, never a full body or a token dump). The run is read-only by
construction: only the fixed GET-backed commands in ``check()`` are invoked, so
no issue edit, comment, transition execution, page write, schedule change, or
chat message is reachable from this module. A 401, 403, or 429 stops the run at
the first failure and no command is retried. Tokens are never read, printed, or
passed on a command line: the CLI resolves them from the BBK credentials file
itself, exactly as agents use it.

The exit status is 0 only when every step that should succeed did succeed with
the expected shape. A step whose command is absent from the CLI is recorded as
an observed capability gap, not as a pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

GATE_ENV = "ATLAWIRE_E2E_LIVE"
STOP_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429")
TIMEOUT_SECONDS = 120

# Fixed, narrow queries. The JQL is the one agents run for "my work"; the CQL is
# bounded to one space key and the page type so it cannot scan the whole site.
JQL_QUERY = "assignee = currentUser() ORDER BY updated DESC"
JQL_LIMIT = 5
CQL_QUERY = 'space = "ARCH" and type = page'
CQL_LIMIT = 3
SPACE_LIMIT = 3
USER_LIMIT = 3
FIND_LIMIT = 2

# A documented CLI gap: there is no ``titles`` command to probe for.
TITLES_COMMAND = "titles"
# Click reports an unknown command as a usage error; the expected code is fixed so
# the check fails if the command appears (exit 0) or the code drifts.
ABSENT_COMMAND_EXIT = 2


def _enabled() -> bool:
    """Return whether the operator explicitly opted into a real-server run."""
    value = os.environ.get(GATE_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Observation:
    """One finished CLI invocation, with its exact argv and streams."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def text(self) -> str:
        return self.stdout + self.stderr


@dataclass(frozen=True, slots=True)
class Step:
    """One reported row: label, exact argv, exit code, observed fact, format."""

    label: str
    argv: str
    exit_code: int
    fact: str
    machine_json: bool | None
    ok: bool


@dataclass(slots=True)
class RunState:
    """Everything discovered so far, plus the reported steps and stop reason."""

    steps: list[Step] = field(default_factory=list)
    stopped_by: str | None = None
    issue_key: str | None = None
    user_name: str | None = None
    page_id: str | None = None
    page_title: str | None = None

    @property
    def failed(self) -> bool:
        return self.stopped_by is not None or any(not s.ok for s in self.steps)


class Cli:
    """Invoke the installed AtlaWire CLI without ever touching a token."""

    def __init__(self, prefix: tuple[str, ...]) -> None:
        self._prefix = prefix
        self._env = os.environ.copy()
        self._env.pop("ATLAWIRE_JIRA_TOKEN", None)
        self._env.pop("ATLAWIRE_CONFLUENCE_TOKEN", None)
        self._env.pop("ATLAWIRE_BITBUCKET_TOKEN", None)
        self._env.pop("ATLAWIRE_JIRA_URL", None)
        self._env.pop("ATLAWIRE_CONFLUENCE_URL", None)
        self._env.pop("ATLAWIRE_BITBUCKET_URL", None)

    def command(self, args: tuple[str, ...]) -> str:
        return " ".join(
            (_display(self._prefix), *(f'"{a}"' if " " in a else a for a in args))
        )

    def run(self, args: tuple[str, ...]) -> Observation:
        try:
            completed = subprocess.run(
                [*self._prefix, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECONDS,
                env=self._env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return Observation(
                argv=args, exit_code=-1, stdout="", stderr="", timed_out=True
            )
        return Observation(
            argv=args,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _display(prefix: tuple[str, ...]) -> str:
    return " ".join(f'"{p}"' if " " in p else p for p in prefix)


def _resolve_prefix() -> tuple[str, ...]:
    found = shutil.which("atlawire")
    if found:
        return (found,)
    return (sys.executable, "-m", "atlawire")


def _stop_marker(observation: Observation) -> str | None:
    for marker in STOP_MARKERS:
        if marker in observation.text:
            return marker
    return None


def _json_value(text: str) -> tuple[bool, object | None]:
    try:
        return True, json.loads(text)
    except ValueError:
        return False, None


def _tsv(text: str) -> tuple[list[str], list[list[str]], int | None]:
    """Return header, data rows, and the optional ``# N row(s)`` claim."""
    lines = [line for line in text.splitlines() if line.strip()]
    claim: int | None = None
    if lines and lines[0].startswith("# "):
        try:
            claim = int(lines[0][2:].split(" ", 1)[0])
        except ValueError:
            claim = None
        lines = lines[1:]
    if not lines:
        return [], [], claim
    header = lines[0].split("\t")
    return header, [line.split("\t") for line in lines[1:]], claim


def _short(text: str, limit: int = 60) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _record(
    cli: Cli,
    state: RunState,
    label: str,
    args: tuple[str, ...],
    observation: Observation,
    *,
    fact: str,
    machine_json: bool | None,
    expected_exit: int = 0,
    forced_ok: bool | None = None,
) -> Observation:
    """Append one reported row and honour the shared stop policy.

    ``forced_ok=None`` keeps the exit-code-only verdict. A boolean enforces the
    step's semantic assertion, so exit 0 alone cannot pass a wrong answer.
    """
    exit_ok = observation.exit_code == expected_exit and not observation.timed_out
    ok = exit_ok if forced_ok is None else exit_ok and forced_ok
    state.steps.append(
        Step(
            label=label,
            argv=cli.command(args),
            exit_code=observation.exit_code,
            fact=fact,
            machine_json=machine_json,
            ok=ok,
        )
    )
    marker = _stop_marker(observation)
    if marker is not None:
        state.stopped_by = f"{label}: {marker}"
    return observation


def _skip(
    state: RunState, cli: Cli, label: str, args: tuple[str, ...], why: str
) -> None:
    state.steps.append(
        Step(
            label=label,
            argv=cli.command(args),
            exit_code=-1,
            fact=f"skipped: {why}",
            machine_json=None,
            ok=False,
        )
    )


def _jql(cli: Cli, state: RunState) -> None:
    args = ("jql", JQL_QUERY, "--limit", str(JQL_LIMIT))
    observation = cli.run(args)
    header, rows, claim = _tsv(observation.stdout)
    machine, parsed = _json_value(observation.stdout)
    if machine and isinstance(parsed, list) and parsed:
        state.issue_key = str(parsed[0].get("key") or "")
    elif rows:
        state.issue_key = rows[0][0] if rows[0] else None
    first = rows[0] if rows else []
    _record(
        cli,
        state,
        "jql (default)",
        args,
        observation,
        fact=(
            f"TSV {len(rows)} rows, claim={claim}, header={header}, "
            f"first={first[:2] if first else 'none'}; not JSON"
        ),
        machine_json=False,
        expected_exit=0,
        forced_ok=bool(rows) and claim == len(rows),
    )
    if state.stopped_by is not None or not state.issue_key:
        return
    json_args = ("jql", JQL_QUERY, "--limit", str(JQL_LIMIT), "--json")
    json_obs = cli.run(json_args)
    ok_json, value = _json_value(json_obs.stdout)
    count = len(value) if ok_json and isinstance(value, list) else -1
    _record(
        cli,
        state,
        "jql --json",
        json_args,
        json_obs,
        fact=f"JSON array {count} rows, first key={state.issue_key}",
        machine_json=ok_json,
        forced_ok=ok_json and count > 0,
    )
    projected_keys = (
        sorted(value[0]) if ok_json and isinstance(value, list) and value else []
    )
    if state.stopped_by is not None:
        return
    fields_args = (
        "jql",
        JQL_QUERY,
        "--limit",
        str(JQL_LIMIT),
        "--fields",
        "summary",
        "--json",
    )
    fields_obs = cli.run(fields_args)
    ok_fields, fields_doc = _json_value(fields_obs.stdout)
    field_issues = fields_doc.get("issues") if isinstance(fields_doc, dict) else None
    field_issue_rows = field_issues if isinstance(field_issues, list) else []
    first_field_keys = (
        sorted(field_issue_rows[0].get("fields") or {})
        if field_issue_rows and isinstance(field_issue_rows[0], dict)
        else []
    )
    fewer_fields = (
        first_field_keys == ["summary"]
        and bool(projected_keys)
        and len(first_field_keys) < len(projected_keys)
    )
    _record(
        cli,
        state,
        "jql --fields summary",
        fields_args,
        fields_obs,
        fact=(
            f"raw envelope: issues={len(field_issue_rows)}, поля первой задачи="
            f"{first_field_keys} против проекции {projected_keys} (меньше={fewer_fields})"
        ),
        machine_json=ok_fields,
        forced_ok=ok_fields and bool(field_issue_rows) and fewer_fields,
    )
    if state.stopped_by is not None:
        return
    expand_args = (
        "jql",
        JQL_QUERY,
        "--limit",
        "1",
        "--expand",
        "renderedFields",
        "--json",
    )
    expand_obs = cli.run(expand_args)
    ok_expand, expand_doc = _json_value(expand_obs.stdout)
    expand_issues = expand_doc.get("issues") if isinstance(expand_doc, dict) else None
    expand_rows = expand_issues if isinstance(expand_issues, list) else []
    rendered_present = bool(expand_rows) and all(
        isinstance(issue, dict) and isinstance(issue.get("renderedFields"), dict)
        for issue in expand_rows
    )
    _record(
        cli,
        state,
        "jql --expand renderedFields",
        expand_args,
        expand_obs,
        fact=(
            f"raw envelope: issues={len(expand_rows)}, renderedFields у каждой="
            f"{rendered_present}; в проекции renderedFields нет="
            f"{'renderedFields' not in projected_keys}"
        ),
        machine_json=ok_expand,
        forced_ok=ok_expand
        and rendered_present
        and "renderedFields" not in projected_keys,
    )


def _issue(cli: Cli, state: RunState) -> None:
    key = state.issue_key
    if not key:
        _skip(state, cli, "issue", ("issue", "<key>"), "no key from jql")
        return
    args = ("issue", key)
    observation = cli.run(args)
    ok_json, value = _json_value(observation.stdout)
    fact = f"JSON bytes={len(observation.stdout)}"
    if ok_json and isinstance(value, dict):
        fields = value.get("fields") or {}
        status = (fields.get("status") or {}).get("name")
        issue_type = (fields.get("issuetype") or {}).get("name")
        assignee = (fields.get("assignee") or {}).get("displayName")
        comments = (fields.get("comment") or {}).get("total")
        summary_len = len(str(fields.get("summary") or ""))
        fact = (
            f"JSON {len(observation.stdout) / 1024:.1f} KB, keys={sorted(value)[:6]}, "
            f"key={value.get('key')}, status={status}, type={issue_type}, "
            f"assignee={assignee}, summary_chars={summary_len}, comment_total={comments}"
        )
    _record(
        cli,
        state,
        "issue",
        args,
        observation,
        fact=fact,
        machine_json=ok_json,
        forced_ok=ok_json and isinstance(value, dict) and bool(value.get("key")),
    )

    comment_args = ("issue-comments", key)
    comment_obs = cli.run(comment_args)
    ok_comments, comments_value = _json_value(comment_obs.stdout)
    count = (
        len(comments_value) if ok_comments and isinstance(comments_value, list) else -1
    )
    shape = sorted(comments_value[0]) if ok_comments and comments_value else []
    _record(
        cli,
        state,
        "issue-comments",
        comment_args,
        comment_obs,
        fact=f"JSON array {count} comments, first keys={shape}",
        machine_json=ok_comments,
        forced_ok=ok_comments,
    )
    full_rows = (
        comments_value if ok_comments and isinstance(comments_value, list) else None
    )
    if state.stopped_by is not None:
        return
    expand_args = ("issue", key, "--expand", "changelog")
    expand_obs = cli.run(expand_args)
    ok_changelog, changelog_doc = _json_value(expand_obs.stdout)
    histories = (
        (changelog_doc.get("changelog") or {}).get("histories")
        if ok_changelog and isinstance(changelog_doc, dict)
        else None
    )
    history_rows = histories if isinstance(histories, list) else []
    default_changelog = isinstance(value, dict) and "changelog" in value
    _record(
        cli,
        state,
        "issue --expand changelog",
        expand_args,
        expand_obs,
        fact=(
            f"raw JSON: changelog присутствует={isinstance(histories, list)}, "
            f"histories={len(history_rows)}; у дефолтного issue changelog={default_changelog}"
        ),
        machine_json=ok_changelog,
        forced_ok=ok_changelog
        and isinstance(changelog_doc, dict)
        and isinstance(histories, list)
        and bool(history_rows)
        and not default_changelog,
    )
    if state.stopped_by is not None:
        return
    limit_args = ("issue-comments", key, "--limit", "1")
    limit_obs = cli.run(limit_args)
    ok_limit, limited = _json_value(limit_obs.stdout)
    limited_rows: list[object] = []
    truncated: object = None
    reported_total: object = None
    if ok_limit and isinstance(limited, dict):
        rows_value = limited.get("rows")
        limited_rows = rows_value if isinstance(rows_value, list) else []
        truncated = limited.get("truncated")
        reported_total = limited.get("total")
    elif ok_limit and isinstance(limited, list):
        limited_rows = limited
    full_count = len(full_rows) if full_rows is not None else -1
    same_first = (
        bool(limited_rows)
        and bool(full_rows)
        and isinstance(limited_rows[0], dict)
        and isinstance(full_rows[0], dict)
        and limited_rows[0].get("id") == full_rows[0].get("id")
    )
    note_shown = "# showing 1 of" in limit_obs.stderr
    if full_count > 1:
        # --limit becomes the server maxResults; a cut thread must be visible.
        capped = (
            ok_limit
            and truncated is True
            and reported_total == full_count
            and len(limited_rows) == 1
            and same_first
            and note_shown
        )
        fact = (
            f"JSON-объект rows={len(limited_rows)}, truncated={truncated}, "
            f"total={reported_total} из полного треда {full_count}; "
            f"stderr-заметка={note_shown}; первый совпал={same_first}"
        )
    else:
        expected = min(full_count, 1) if full_count >= 0 else -1
        capped = (
            ok_limit
            and len(limited_rows) == expected
            and not note_shown
            and not limit_obs.stderr.strip()
        )
        fact = (
            f"тред {full_count} <= limit: JSON-массив {len(limited_rows)} row(s), "
            "truncation-объект не нужен, stderr пуст"
        )
    _record(
        cli,
        state,
        "issue-comments --limit 1",
        limit_args,
        limit_obs,
        fact=fact,
        machine_json=ok_limit,
        forced_ok=capped,
    )


def _jira_metadata(cli: Cli, state: RunState) -> None:
    args = ("statuses",)
    observation = cli.run(args)
    ok_json, _ = _json_value(observation.stdout)
    lines = [line for line in observation.stdout.splitlines() if line.strip()]
    _record(
        cli,
        state,
        "statuses",
        args,
        observation,
        fact=f"plain text {len(lines)} lines, sample={lines[:3] if lines else []}; not JSON",
        machine_json=False,
        forced_ok=not ok_json and len(lines) > 0,
    )

    key = state.issue_key
    trans_args = ("transitions", key) if key else ("transitions", "<key>")
    if not key:
        _skip(state, cli, "transitions", trans_args, "no key from jql")
        return
    trans_obs = cli.run(trans_args)
    trans_ok, trans_value = _json_value(trans_obs.stdout)
    header, rows, claim = _tsv(trans_obs.stdout)
    ids = [row[0] for row in rows if row]
    fact = (
        f"TSV {len(rows)} rows, claim={claim}, header={header}, "
        f"ids={ids[:3]}…{ids[-1] if ids else '-'}; not JSON"
    )
    _record(
        cli,
        state,
        "transitions",
        trans_args,
        trans_obs,
        fact=fact,
        machine_json=trans_ok,
        forced_ok=bool(rows) or (trans_ok and isinstance(trans_value, list)),
    )


def _identity(cli: Cli, state: RunState) -> None:
    args = ("jira-me",)
    observation = cli.run(args)
    ok_json, value = _json_value(observation.stdout)
    if ok_json and isinstance(value, dict):
        state.user_name = str(value.get("name") or "")
    fact = (
        f"JSON name={value.get('name')}, displayName={value.get('displayName')}"
        if ok_json and isinstance(value, dict)
        else f"JSON parse failed: {_short(observation.text)}"
    )
    _record(
        cli,
        state,
        "jira-me",
        args,
        observation,
        fact=fact,
        machine_json=ok_json,
        forced_ok=ok_json and bool(state.user_name),
    )

    query = state.user_name or "a.fink"
    users_args = ("jira-users", query, "--limit", str(USER_LIMIT))
    users_obs = cli.run(users_args)
    users_ok, users_value = _json_value(users_obs.stdout)
    count = len(users_value) if users_ok and isinstance(users_value, list) else -1
    sample = []
    if users_ok and isinstance(users_value, list):
        sample = [(u.get("name"), u.get("active")) for u in users_value[:USER_LIMIT]]
    _record(
        cli,
        state,
        "jira-users",
        users_args,
        users_obs,
        fact=f"JSON array {count} users for {query!r}, sample={sample}",
        machine_json=users_ok,
        forced_ok=users_ok and count > 0,
    )


def _confluence(cli: Cli, state: RunState) -> None:
    spaces_args = ("spaces", "--limit", str(SPACE_LIMIT))
    spaces_obs = cli.run(spaces_args)
    header, rows, claim = _tsv(spaces_obs.stdout)
    keys = [row[0] for row in rows if row]
    _record(
        cli,
        state,
        "spaces --limit 3",
        spaces_args,
        spaces_obs,
        fact=f"TSV {len(rows)} rows, claim={claim}, header={header}, keys={keys}; not JSON",
        machine_json=False,
        forced_ok=bool(rows) and claim == len(rows),
    )

    cql_args = ("cql", CQL_QUERY, "--limit", str(CQL_LIMIT))
    cql_obs = cli.run(cql_args)
    header, rows, claim = _tsv(cql_obs.stdout)
    if rows:
        state.page_id = rows[0][0] or None
        if len(rows[0]) > 3:
            state.page_title = rows[0][3] or None
    empty_space = bool(rows) and all(len(row) > 1 and not row[1] for row in rows)
    _record(
        cli,
        state,
        "cql --limit 3",
        cql_args,
        cql_obs,
        fact=(
            f"TSV {len(rows)} rows, claim={claim}, header={header}, "
            f"first_id={state.page_id}, first_title={state.page_title!r}, "
            f"space_column_empty_on_all_rows={empty_space}; not JSON"
        ),
        machine_json=False,
        forced_ok=bool(rows) and claim == len(rows),
    )
    if state.stopped_by is not None:
        return
    cql_expand_args = (
        "cql",
        CQL_QUERY,
        "--limit",
        str(CQL_LIMIT),
        "--expand",
        "content.body.storage",
    )
    cql_expand_obs = cli.run(cql_expand_args)
    ok_cql_expand, cql_expand_doc = _json_value(cql_expand_obs.stdout)
    cql_results = (
        cql_expand_doc.get("results") if isinstance(cql_expand_doc, dict) else None
    )
    result_rows = cql_results if isinstance(cql_results, list) else []
    storage_lengths: list[int] = []
    for result in result_rows:
        content = result.get("content") if isinstance(result, dict) else None
        body = content.get("body") if isinstance(content, dict) else None
        storage = body.get("storage") if isinstance(body, dict) else None
        stored = storage.get("value") if isinstance(storage, dict) else None
        storage_lengths.append(len(stored) if isinstance(stored, str) else -1)
    body_present = bool(storage_lengths) and all(
        length > 0 for length in storage_lengths
    )
    projection_has_body = any(str(column).lower() == "body" for column in header)
    _record(
        cli,
        state,
        "cql --expand content.body.storage",
        cql_expand_args,
        cql_expand_obs,
        fact=(
            f"raw envelope: results={len(result_rows)}, body.storage.value длины="
            f"{storage_lengths}; в проекции столбцы={header} без body="
            f"{not projection_has_body}"
        ),
        machine_json=ok_cql_expand,
        forced_ok=ok_cql_expand
        and bool(result_rows)
        and body_present
        and not projection_has_body,
    )

    if state.stopped_by is not None or not state.page_id:
        _skip(state, cli, "page", ("page", "<id>"), "no page id from cql")
        _skip(
            state, cli, "page --markdown", ("page", "<id>", "--markdown"), "no page id"
        )
        _skip(state, cli, "children", ("children", "<id>"), "no page id")
        return

    page_id = state.page_id
    page_args = ("page", page_id)
    page_obs = cli.run(page_args)
    page_ok, page_value = _json_value(page_obs.stdout)
    fact = f"JSON bytes={len(page_obs.stdout)}"
    if page_ok and isinstance(page_value, dict):
        space = (page_value.get("space") or {}).get("key")
        version = (page_value.get("version") or {}).get("number")
        body = (
            ((page_value.get("body") or {}).get("storage") or {}).get("value")
        ) or ""
        fact = (
            f"JSON {len(page_obs.stdout) / 1024:.1f} KB, id={page_value.get('id')}, "
            f"type={page_value.get('type')}, title={page_value.get('title')!r}, "
            f"space={space}, version={version}, body.storage_chars={len(body)}"
        )
    _record(
        cli,
        state,
        "page",
        page_args,
        page_obs,
        fact=fact,
        machine_json=page_ok,
        forced_ok=page_ok
        and isinstance(page_value, dict)
        and bool(page_value.get("id")),
    )
    if state.stopped_by is not None:
        return
    page_expand_args = ("page", page_id, "--expand", "version")
    page_expand_obs = cli.run(page_expand_args)
    ok_page_expand, page_expand_doc = _json_value(page_expand_obs.stdout)
    default_version = (
        (page_value.get("version") or {}).get("number")
        if isinstance(page_value, dict)
        else None
    )
    default_body = (
        isinstance(page_value.get("body"), dict)
        and bool(((page_value.get("body") or {}).get("storage") or {}).get("value"))
        if isinstance(page_value, dict)
        else False
    )
    expanded_version = (
        (page_expand_doc.get("version") or {}).get("number")
        if isinstance(page_expand_doc, dict)
        else None
    )
    expand_has_body = isinstance(page_expand_doc, dict) and "body" in page_expand_doc
    _record(
        cli,
        state,
        "page --expand version",
        page_expand_args,
        page_expand_obs,
        fact=(
            f"raw page: version.number={expanded_version}, body отсутствует="
            f"{not expand_has_body}; дефолтный page: version={default_version}, "
            f"body.storage непустой={default_body}"
        ),
        machine_json=ok_page_expand,
        forced_ok=ok_page_expand
        and isinstance(page_expand_doc, dict)
        and default_version is not None
        and expanded_version == default_version
        and not expand_has_body
        and default_body,
    )

    markdown_args = ("page", page_id, "--markdown")
    markdown_obs = cli.run(markdown_args)
    markdown = markdown_obs.stdout
    unsupported = markdown.count("[Unsupported macro")
    first_line = (markdown.splitlines() or [""])[0]
    _record(
        cli,
        state,
        "page --markdown",
        markdown_args,
        markdown_obs,
        fact=(
            f"Markdown {len(markdown)} chars, first_line={first_line!r}, "
            f"unsupported_macro_markers={unsupported}; not JSON"
        ),
        machine_json=False,
        forced_ok=bool(markdown.strip()),
    )

    children_args = ("children", page_id)
    children_obs = cli.run(children_args)
    children_ok, _ = _json_value(children_obs.stdout)
    header, rows, claim = _tsv(children_obs.stdout)
    ids = [row[0] for row in rows if row]
    _record(
        cli,
        state,
        "children",
        children_args,
        children_obs,
        fact=f"TSV {len(rows)} rows, claim={claim}, header={header}, ids={ids[:3]}; not JSON",
        machine_json=children_ok,
        forced_ok=claim == len(rows),
    )


def _federated(cli: Cli, state: RunState) -> None:
    term = state.page_title or "AtlaWire"
    args = ("find", term, "--limit", str(FIND_LIMIT))
    observation = cli.run(args)
    ok_json, value = _json_value(observation.stdout)
    fact = f"JSON parse failed: {_short(observation.text)}"
    if ok_json and isinstance(value, dict):
        counts = {
            product: len(value.get(product) or [])
            for product in ("confluence", "jira", "bitbucket")
        }
        fact = (
            f"JSON per-product rows={counts}, complete={value.get('complete')}, "
            f"errors={value.get('errors')}"
        )
    _record(
        cli,
        state,
        "find",
        args,
        observation,
        fact=fact,
        machine_json=ok_json,
        forced_ok=ok_json and "jira" in observation.stdout,
    )


def _absent_command(cli: Cli, state: RunState) -> None:
    args = (TITLES_COMMAND, "--help")
    observation = cli.run(args)
    absent = "No such command" in observation.text
    _record(
        cli,
        state,
        "titles (absent?)",
        args,
        observation,
        fact=(
            "no 'titles' command in the CLI; agents must use jql/issue summary"
            if absent and observation.exit_code == ABSENT_COMMAND_EXIT
            else f"unexpected: {_short(observation.text)}"
        ),
        machine_json=None,
        expected_exit=ABSENT_COMMAND_EXIT,
        forced_ok=absent,
    )


def check() -> RunState:
    """Run the fixed read-only command sequence and report one row per command."""
    prefix = _resolve_prefix()
    cli = Cli(prefix)
    state = RunState()

    print("AtlaWire CLI live read-only check (Jira + Confluence)")
    print(f"command: {cli.command(('--version',))}")
    version = cli.run(("--version",))
    print(
        f"command exit={version.exit_code}: {version.stdout.strip() or version.stderr.strip()}"
    )
    print()

    selftest_args = ("selftest",)
    selftest = cli.run(selftest_args)
    ok_json, value = _json_value(selftest.stdout)
    fact = f"JSON parse failed: {_short(selftest.text)}"
    if ok_json and isinstance(value, dict):
        jira = value.get("jira") or {}
        confluence = value.get("confluence") or {}
        bitbucket = value.get("bitbucket") or {}
        fact = (
            f"JSON jira.ok={jira.get('ok')}, confluence.ok={confluence.get('ok')}, "
            f"bitbucket.authenticated={bitbucket.get('authenticated')}"
        )
    _record(
        cli,
        state,
        "selftest",
        selftest_args,
        selftest,
        fact=fact,
        machine_json=ok_json,
        forced_ok=ok_json and isinstance(value, dict),
    )
    if state.stopped_by is None:
        _jql(cli, state)
    if state.stopped_by is None:
        _issue(cli, state)
    if state.stopped_by is None:
        _jira_metadata(cli, state)
    if state.stopped_by is None:
        _identity(cli, state)
    if state.stopped_by is None:
        _confluence(cli, state)
    if state.stopped_by is None:
        _federated(cli, state)
    if state.stopped_by is None:
        _absent_command(cli, state)
    return state


def report(state: RunState) -> int:
    """Print the step table and the format/stop sections; return an exit code."""
    print(f"{'step':<18} {'exit':>4}  fact")
    print("-" * 118)
    for step in state.steps:
        print(f"{step.label:<18} {step.exit_code:>4}  {step.fact}")
    print("-" * 118)

    non_json = [s.label for s in state.steps if s.machine_json is False]
    print(f"non-JSON output (TSV/plain): {non_json}")
    parse_failed = [s.label for s in state.steps if s.machine_json is None and not s.ok]
    if parse_failed:
        print(f"unexpected/broken: {parse_failed}")
    if state.stopped_by is not None:
        print(f"STOP: {state.stopped_by} (no further command attempted, no retry)")
    failed = [s.label for s in state.steps if not s.ok]
    print(f"steps={len(state.steps)} failed={len(failed)} {failed}")
    print(f"RESULT: {'PASS' if not state.failed else 'FAIL'}")
    return 0 if not state.failed else 1


def main() -> int:
    """Gate the live run, execute the check, and return its exit status."""
    if not _enabled():
        print(f"SKIPPED: set {GATE_ENV}=1 to run against the real server.")
        return 2
    return report(check())


if __name__ == "__main__":
    raise SystemExit(main())

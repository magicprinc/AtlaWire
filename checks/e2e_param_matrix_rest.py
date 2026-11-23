"""Live parameter-matrix checks for the remaining AtlaWire read surface.

Covers the functions left outside the main-command matrix: Confluence page
reads and subresources, Bitbucket pull-request/commit/ref/file reads, Jira
reference and issue subresource reads, and the federated / identity / grep /
scan helpers. Each row exercises one live combination and compares the result
with the meaning of the request: a requested row count is neither zero when
data exists nor above the cap, a requested PR or commit owns the returned
fields, a requested diff belongs to that commit or PR, a requested expansion
is present and non-empty, and a cap that hides more rows is visible in the
result.

Usage::

    C:/Python315/python.exe -B checks/e2e_param_matrix_rest.py --live [--timeout 60]

Read-only: only GET reads and the read-only Jira search are used. The owner's
saved BBK credentials file is the only credential source. Tokens, base URLs,
response bodies and raw text are never printed; rows carry counts, booleans,
identifiers and fixed error categories only. Any 401/403/429 stops the run
immediately with a STOP row. Exit 0 means every row matched its expectation, 1
means a row failed, 2 means usage or configuration failed.

Columns: FUNC | COMBO | EXIT | FACT | VERDICT | APPLIES. ``APPLIES`` names the
agent task that needs the combination: ``freshness`` (is the page/ref current
before quoting it), ``scope`` (how large a change is), ``trace`` (who touched
these lines/paths and when), ``bound`` (bounded list read under a real cap),
``fields`` (one field group of one object), ``review`` (PR review context),
``discover`` (find candidate material), ``audit`` (change history),
``coverage`` (where an extension/ref exists), ``cross`` (independent
cross-check of two reads), ``dup`` (duplicates another row), ``low`` (rarely
useful in agent work).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from atlawire import (
    bitbucket,
    confluence,
    federated,
    identity,
    jira,
    repo_grep,
    repo_scan,
)
from atlawire.confluence_markdown import render_page_markdown
from atlawire.credentials import load_saved_credentials
from atlawire.federated import ProductTarget
from atlawire.http import AtlaWireError

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
CLI = (sys.executable, "-P", "-B", "-m", "atlawire")
_TIMEOUT_DEFAULT = 60
_TIMEOUT_MIN, _TIMEOUT_MAX = 5, 300
_AUTH_STOP = frozenset({401, 403, 429})
_SHA = re.compile(r"[0-9a-f]{40}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_HELP = """\
Usage: python -B checks/e2e_param_matrix_rest.py --live [--timeout SECONDS]

Live read-only parameter-matrix checks for the remaining AtlaWire functions.
--live is required; the saved BBK credentials file supplies all three
products. SECONDS is 5-300 (default 60) per CLI child process. Output rows are
FUNC | COMBO | EXIT | FACT | VERDICT | APPLIES; tokens, URLs and response
bodies are never printed. 401/403/429 stops the run. Exit 0 all rows matched,
1 a row failed, 2 usage or configuration.
"""


class Divergence(Exception):
    """Expected behaviour violated; the message is the sanitized fact."""


class StopRun(Exception):
    """Credential or rate-limit stop carrying only the HTTP status."""

    def __init__(self, status: int) -> None:
        super().__init__(str(status))
        self.status = status


@dataclass(slots=True)
class Ctx:
    """Resolved credentials and the discovered fixture values."""

    confluence: ProductTarget
    jira: ProductTarget
    bitbucket: ProductTarget
    fixtures: dict[str, object] = field(default_factory=dict)

    @property
    def timeout(self) -> int:
        value = self.fixtures.get("timeout", _TIMEOUT_DEFAULT)
        return value if isinstance(value, int) else _TIMEOUT_DEFAULT


@dataclass(slots=True)
class Check:
    func: str
    combo: str
    applies: str
    run: Callable[[Ctx], str]
    expect_error: str | None = None


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Divergence(f"{name} not a non-empty string")
    return value


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Divergence(f"{name} not an object")
    return value


def _objects(value: object, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise Divergence(f"{name} not an array of objects")
    return value


def _results(document: object) -> list[dict[str, object]]:
    return _objects(_mapping(document, "page").get("results"), "results")


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Divergence(f"{name} not an integer")
    return value


def _bounded(rows: Sequence[object], limit: int, name: str) -> None:
    if len(rows) > limit:
        raise Divergence(f"{name} {len(rows)} > limit {limit}")


def _sha(value: object, name: str) -> str:
    text = _text(value, name)
    if _SHA.fullmatch(text) is None:
        raise Divergence(f"{name} not 40-hex")
    return text


def _fixture(ctx: Ctx, name: str) -> object:
    value = ctx.fixtures.get(name)
    if value is None:
        raise Divergence(f"fixture {name} unavailable")
    return value


def _fixture_int(ctx: Ctx, name: str) -> int:
    return _int(_fixture(ctx, name), name)


def _cli(args: Sequence[str], timeout: int) -> tuple[int, str]:
    completed = subprocess.run(
        [*CLI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return completed.returncode, completed.stdout


def _cli_json(args: Sequence[str], timeout: int) -> object:
    code, stdout = _cli(args, timeout)
    if code != 0:
        raise Divergence(f"cli exit {code}")
    try:
        return json.loads(stdout)
    except ValueError:
        raise Divergence("cli output not JSON") from None


# ---------------------------------------------------------------------------
# Fixture discovery: bounded read-only probes, no writes, no full scans.
# ---------------------------------------------------------------------------


def _discover_confluence(ctx: Ctx) -> None:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    spaces = confluence.list_spaces(base, token=token, limit=3)
    pages = confluence.search_cql(
        base, "type=page order by lastmodified desc", token=token, limit=10
    )
    if not spaces or not pages:
        raise StopRun(-1)
    candidates: list[dict[str, object]] = []
    page_main: dict[str, object] | None = None
    for row in pages:
        page = confluence.get_page(base, row["id"], token=token)
        candidates.append(page)
        body = page.get("body")
        storage = body.get("storage") if isinstance(body, dict) else None
        value = storage.get("value") if isinstance(storage, dict) else None
        version = page.get("version")
        if (
            page_main is None
            and isinstance(value, str)
            and len(value) > 500
            and isinstance(version, dict)
            and isinstance(version.get("number"), int)
            and version["number"] > 1
            and page.get("ancestors")
        ):
            page_main = page
    if page_main is None:
        page_main = candidates[0]
    ctx.fixtures["conf_page"] = page_main["id"]
    ctx.fixtures["conf_space"] = spaces[0]["key"]

    def pick(key: str, probe: Callable[[object], int], total_key: str) -> None:
        best: tuple[object, int] | None = None
        for page in candidates:
            try:
                count = probe(page["id"])
            except AtlaWireError:
                continue
            if best is None or count > best[1]:
                best = (page["id"], count)
            if count >= 3:
                break
        page_id, count = best if best is not None else (page_main["id"], 0)
        ctx.fixtures[key] = page_id
        ctx.fixtures[total_key] = count

    pick(
        "conf_children_page",
        lambda pid: len(confluence.list_children(base, pid, token=token, limit=100)),
        "conf_children_total",
    )
    pick(
        "conf_comments_page",
        lambda pid: len(
            _results(confluence.get_page_comments(base, pid, token=token, limit=100))
        ),
        "conf_comments_total",
    )
    pick(
        "conf_attachments_page",
        lambda pid: len(
            _results(confluence.get_page_attachments(base, pid, token=token, limit=100))
        ),
        "conf_attachments_total",
    )
    pick(
        "conf_labels_page",
        lambda pid: len(
            _results(confluence.get_page_labels(base, pid, token=token, limit=100))
        ),
        "conf_labels_total",
    )
    if ctx.fixtures.get("conf_labels_total") == 0:
        # docs/API.md uses page 7307751 as its Confluence sample fixture.
        try:
            fallback = _results(
                confluence.get_page_labels(base, 7307751, token=token, limit=100)
            )
        except AtlaWireError:
            fallback = []
        if fallback:
            ctx.fixtures["conf_labels_page"] = 7307751
            ctx.fixtures["conf_labels_total"] = len(fallback)


def _discover_jira(ctx: Ctx) -> None:
    base, token = ctx.jira.base_url, ctx.jira.token
    me = jira.get_current_user(base, token=token)
    ctx.fixtures["jira_user_query"] = me["name"]
    recent = jira.search_issues(base, "order by updated DESC", token=token, limit=5)
    if not recent:
        raise StopRun(-1)
    ctx.fixtures["jira_issue"] = recent[0]["key"]
    ctx.fixtures["jira_title_keys"] = [row["key"] for row in recent[:3]]
    links_issue = recent[0]["key"]
    for row in recent[:3]:
        if jira.list_issue_remote_links(base, row["key"], token=token):
            links_issue = row["key"]
            break
    ctx.fixtures["jira_links_issue"] = links_issue
    worklogged = jira.search_issues(
        base, "timespent > 0 order by updated DESC", token=token, limit=1
    )
    ctx.fixtures["jira_worklog_issue"] = (
        worklogged[0]["key"] if worklogged else recent[0]["key"]
    )


def _discover_bitbucket(ctx: Ctx) -> None:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    projects = bitbucket.list_projects(base, token=token, max_pages=1)
    repo_name: str | None = None
    pr_id: object = None
    for project in projects[:3]:
        repos = bitbucket.list_repositories(
            base, project["key"], token=token, max_pages=1
        )
        for repository in repos[:3]:
            candidate = f"{project['key']}/{repository['slug']}"
            pull_requests = bitbucket.list_pull_requests(
                base, candidate, token=token, state="ALL", limit=3
            )
            if not pull_requests:
                continue
            if not (
                bitbucket.list_tags(base, candidate, token=token, limit=1)
                and bitbucket.list_branches(base, candidate, token=token)
                and bitbucket.list_commits(base, candidate, token=token, limit=3)
            ):
                continue
            repo_name, pr_id = candidate, pull_requests[0]["id"]
            break
        if repo_name is not None:
            break
    if repo_name is None or pr_id is None:
        raise StopRun(-1)
    ctx.fixtures["bb_repo"] = repo_name
    ctx.fixtures["bb_pr"] = pr_id
    ctx.fixtures["bb_project"] = repo_name.split("/", 1)[0]
    branches = bitbucket.list_branches(base, repo_name, token=token)
    default_branch = next(
        (row for row in branches if row.get("default")), branches[0]
    )
    ctx.fixtures["bb_branch"] = str(default_branch["name"])
    ctx.fixtures["bb_default_commit"] = str(default_branch["commit"])
    tags = bitbucket.list_tags(base, repo_name, token=token, limit=3)
    if not tags:
        raise StopRun(-1)
    ctx.fixtures["bb_tag"] = tags[0]["displayId"]
    files = bitbucket.list_repository_files(base, repo_name, token=token)
    if not files:
        raise StopRun(-1)
    java = [path for path in files if path.endswith(".java")]
    ctx.fixtures["bb_java_path"] = java[0] if java else files[0]
    ctx.fixtures["bb_java_dir"] = (java[0] if java else files[0]).rsplit("/", 1)[0]
    commits = bitbucket.list_commits(base, repo_name, token=token, limit=5)
    if not commits:
        raise StopRun(-1)
    changed: tuple[str, list[dict[str, object]]] | None = None
    for commit in commits[1:4]:
        try:
            changes = bitbucket.list_commit_changes(
                base, repo_name, commit["hash"], token=token
            )
        except AtlaWireError:
            continue
        usable = [row for row in changes if row["type"] != "DELETE"]
        if usable:
            changed = (commit["hash"], usable)
            break
    if changed is None:
        raise StopRun(-1)
    ctx.fixtures["bb_commit_sha"] = changed[0]
    ctx.fixtures["bb_commit_paths"] = [row["path"] for row in changed[1][:2]]
    ctx.fixtures["bb_commit_path"] = ctx.fixtures["bb_commit_paths"][0]
    pr_files = bitbucket.list_pull_request_files(base, repo_name, pr_id, token=token)
    if not pr_files:
        raise StopRun(-1)
    ctx.fixtures["bb_pr_path"] = pr_files[0]["path"]


def _discover(ctx: Ctx) -> None:
    _discover_confluence(ctx)
    _discover_jira(ctx)
    _discover_bitbucket(ctx)


# ---------------------------------------------------------------------------
# Confluence rows
# ---------------------------------------------------------------------------


def _conf_page(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    page = confluence.get_page(base, _fixture(ctx, "conf_page"), token=token)
    page_id = str(page.get("id"))
    _text(page.get("title"), "title")
    storage = _mapping(
        _mapping(page.get("body"), "body").get("storage"), "body.storage"
    )
    value = _text(storage.get("value"), "body.storage.value")
    version = _mapping(page.get("version"), "version")
    _int(version.get("number"), "version.number")
    space = _mapping(page.get("space"), "space")
    _text(space.get("key"), "space.key")
    ancestors = page.get("ancestors")
    if not isinstance(ancestors, list) or not ancestors:
        raise Divergence("ancestors absent or empty")
    return f"id={page_id} storage={len(value)} chars, version/space/ancestors present"


def _conf_expand(expand: str) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        document = _cli_json(
            (
                "api-get",
                "confluence",
                f"/rest/api/content/{_fixture(ctx, 'conf_page')}",
                "--params",
                json.dumps({"expand": expand}),
            ),
            ctx.timeout,
        )
        doc = _mapping(document, "document")
        if expand == "body.storage":
            storage = _mapping(
                _mapping(doc.get("body"), "body").get("storage"), "storage"
            )
            return f"body.storage -> {len(_text(storage.get('value'), 'value'))} chars"
        if expand == "version":
            version = _mapping(doc.get("version"), "version")
            return f"version -> number={_int(version.get('number'), 'number')}"
        if expand == "space":
            space = _mapping(doc.get("space"), "space")
            return f"space -> key={_text(space.get('key'), 'key')}"
        ancestors = doc.get("ancestors")
        if not isinstance(ancestors, list) or not ancestors:
            raise Divergence("ancestors absent/empty")
        return f"ancestors -> {len(ancestors)} rows"

    return run


def _conf_formats(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    page_id = _fixture(ctx, "conf_page")
    page = confluence.get_page(base, page_id, token=token)
    storage = _mapping(_mapping(page.get("body"), "body").get("storage"), "storage")
    raw = _text(storage.get("value"), "storage.value")
    code, out = _cli(("page", str(page_id), "--storage"), ctx.timeout)
    if code != 0:
        raise Divergence(f"page --storage exit {code}")
    if out.strip() != raw.strip():
        raise Divergence("storage format differs from body.storage.value")
    code_md, markdown = _cli(("page", str(page_id), "--markdown"), ctx.timeout)
    if code_md != 0 or not markdown.strip():
        raise Divergence("page --markdown empty or failed")
    if markdown.strip() == raw.strip():
        raise Divergence("markdown format equals storage")
    local = render_page_markdown(page)
    if local.strip() != markdown.strip():
        raise Divergence("CLI markdown differs from render_page_markdown")
    document = _cli_json(("page", str(page_id)), ctx.timeout)
    if not isinstance(document, dict) or "body" not in document:
        raise Divergence("page JSON format has no body")
    return f"storage==body.storage, markdown {len(markdown)} chars, json has body"


def _conf_children(limit: int | None) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        page = _fixture(ctx, "conf_children_page")
        kwargs = {} if limit is None else {"limit": limit}
        rows = confluence.list_children(base, page, token=token, **kwargs)  # type: ignore[arg-type]
        total = _fixture_int(ctx, "conf_children_total")
        cap = 100 if limit is None else limit
        expected = min(cap, total) if total else 0
        _bounded(rows, cap, "children")
        if limit is None:
            return f"default cap 100 -> {len(rows)} rows (total {total})"
        if len(rows) != expected:
            raise Divergence(f"limit={cap} of {total} -> {len(rows)} rows")
        return f"limit={cap} of total {total} -> {len(rows)} rows"

    return run


def _conf_children_truncation(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    total = _fixture_int(ctx, "conf_children_total")
    if total < 2:
        return f"fixture page has {total} child, cap not observable"
    listing = confluence.list_children_with_metadata(
        base, _fixture(ctx, "conf_children_page"), token=token, limit=1
    )
    rows = listing["rows"]
    if len(rows) != 1:
        raise Divergence(f"limit=1 of {total} -> {len(rows)} rows")
    if listing["truncated"] is not True:
        raise Divergence("limit=1 under cap not reported as truncated")
    reported = listing["total"]
    if reported is not None and reported < 2:
        raise Divergence(f"metadata total {reported} contradicts a non-empty cap")
    return f"limit=1 of {total} -> truncated=True, total={reported}"

def _conf_spaces(limit: int | None) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        kwargs = {} if limit is None else {"limit": limit}
        rows = confluence.list_spaces(base, token=token, **kwargs)  # type: ignore[arg-type]
        cap = 100 if limit is None else limit
        _bounded(rows, cap, "spaces")
        if rows:
            _text(rows[0].get("key"), "space.key")
        return f"limit={cap} -> {len(rows)} rows"

    return run


def _conf_comments(start: int, limit: int, replies: bool) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        document = confluence.get_page_comments(
            base,
            _fixture(ctx, "conf_comments_page"),
            token=token,
            start=start,
            limit=limit,
            include_replies=replies,
        )
        rows = _results(document)
        _bounded(rows, limit, "comments")
        echo = _mapping(document, "page").get("start")
        if echo is not None and _int(echo, "start") != start:
            raise Divergence(f"start echo {echo} != {start}")
        return f"start={start} limit={limit} replies={replies} -> {len(rows)} rows"

    return run


def _conf_comments_truncation(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    total = _fixture_int(ctx, "conf_comments_total")
    if total < 2:
        return f"page has {total} comments, cap not observable"
    listing = confluence.get_page_comments_with_metadata(
        base, _fixture(ctx, "conf_comments_page"), token=token, limit=1
    )
    if len(listing["rows"]) != 1:
        return f"page has {total} comments, cap not observable"
    if listing["truncated"] is not True:
        raise Divergence("limit=1 under cap not reported as truncated")
    reported = listing["total"]
    if reported is not None and reported < 2:
        raise Divergence(f"metadata total {reported} contradicts a non-empty cap")
    return (
        f"limit=1 of {total} -> truncated=True, total={reported}, "
        f"next={'yes' if listing['next'] else 'no'}"
    )


def _conf_labels(limit: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        document = confluence.get_page_labels(
            base, _fixture(ctx, "conf_labels_page"), token=token, limit=limit
        )
        rows = _results(document)
        _bounded(rows, limit, "labels")
        if rows:
            _text(rows[0].get("name"), "label.name")
            if "prefix" not in rows[0]:
                raise Divergence("label row has no prefix")
        return f"limit={limit} -> {len(rows)} labels"

    return run


def _conf_attachments(start: int, limit: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        document = confluence.get_page_attachments(
            base,
            _fixture(ctx, "conf_attachments_page"),
            token=token,
            start=start,
            limit=limit,
        )
        rows = _results(document)
        _bounded(rows, limit, "attachments")
        echo = _mapping(document, "page").get("limit")
        if echo is not None and _int(echo, "limit") != limit:
            raise Divergence(f"limit echo {echo} != {limit}")
        return f"start={start} limit={limit} -> {len(rows)} attachments"

    return run


def _conf_attachments_truncation(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    total = _fixture_int(ctx, "conf_attachments_total")
    if total < 2:
        return f"page has {total} attachments, cap not observable"
    listing = confluence.get_page_attachments_with_metadata(
        base, _fixture(ctx, "conf_attachments_page"), token=token, limit=1
    )
    if len(listing["rows"]) != 1:
        return f"page has {total} attachments, cap not observable"
    if listing["truncated"] is not True:
        raise Divergence("limit=1 under cap not reported as truncated")
    reported = listing["total"]
    if reported is not None and reported < 2:
        raise Divergence(f"metadata total {reported} contradicts a non-empty cap")
    return (
        f"limit=1 of {total} -> truncated=True, total={reported}, "
        f"next={'yes' if listing['next'] else 'no'}"
    )


def _conf_history(ctx: Ctx) -> str:
    base, token = ctx.confluence.base_url, ctx.confluence.token
    page = _fixture(ctx, "conf_page")
    document = confluence.get_page_history(base, page, token=token)
    if document.get("latest") is not True:
        raise Divergence("history has no latest=true")
    current = _int(
        _mapping(
            confluence.get_page(base, page, token=token).get("version"), "version"
        ).get("number"),
        "number",
    )
    version = document.get("version")
    number = (
        _int(_mapping(version, "version").get("number"), "number")
        if isinstance(version, dict)
        else None
    )
    if number is not None and number != current:
        raise Divergence(f"history version {number} != page {current}")
    return f"latest=true, version {number if number is not None else 'absent'}"


def _conf_version(kind: str) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.confluence.base_url, ctx.confluence.token
        page = _fixture(ctx, "conf_page")
        current = _int(
            _mapping(
                confluence.get_page(base, page, token=token).get("version"), "version"
            ).get("number"),
            "number",
        )
        version = {"first": 1, "previous": current - 1, "current": current}[kind]
        document = confluence.get_page_version(base, page, version, token=token)
        returned = _int(
            _mapping(document.get("version"), "version").get("number"), "number"
        )
        if returned != version:
            raise Divergence(f"requested {version} got {returned}")
        storage = _mapping(
            _mapping(document.get("body"), "body").get("storage"), "storage"
        )
        value = storage.get("value")
        if not isinstance(value, str):
            raise Divergence("storage.value not a string")
        if kind != "first" and not value:
            raise Divergence(f"storage.value empty for version {version}")
        return f"v={version} -> number={returned} status={document.get('status')} storage={len(value)}"

    return run


# ---------------------------------------------------------------------------
# Bitbucket rows
# ---------------------------------------------------------------------------


def _bb_pr(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, pr_id = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_pr")
    pr = bitbucket.get_pull_request(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    if pr.get("id") != pr_id:
        raise Divergence(f"requested PR {pr_id} got id {pr.get('id')}")
    _text(pr.get("title"), "title")
    state = _text(pr.get("state"), "state")
    for side in ("fromRef", "toRef"):
        ref = _mapping(pr.get(side), side)
        _sha(ref.get("latestCommit"), "commit")
    return f"PR {pr_id} state={state}, refs pin 40-hex commits"


def _bb_pr_files(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, pr_id = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_pr")
    files = bitbucket.list_pull_request_files(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    if not files:
        raise Divergence("PR files empty")
    diff = bitbucket.get_pull_request_diff(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    diffs = diff.get("diffs")
    if not isinstance(diffs, list):
        raise Divergence("diff has no diffs array")
    paths = {row["path"] for row in files}
    diff_paths = {
        _mapping(_mapping(row, "diff row").get("destination"), "destination").get(
            "toString"
        )
        for row in diffs
    }
    if paths != diff_paths:
        raise Divergence(f"files {len(paths)} vs diff paths {len(diff_paths)}")
    return f"{len(files)} files equal PR diff paths"


def _bb_pr_comments(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, pr_id = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_pr")
    rows = bitbucket.list_pull_request_comments(
        base,
        repo,
        pr_id,
        token=token,
        max_pages=1,  # type: ignore[arg-type]
    )
    if not rows:
        return "max_pages=1 -> 0 comments (PR activity has none)"
    for row in rows:
        identifier = row.get("id")
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
            raise Divergence("comment has no string/int id")
        if not isinstance(row.get("text"), str):
            raise Divergence("comment has no text")
    return f"max_pages=1 -> {len(rows)} comments with id/text"


def _bb_pr_commits(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, pr_id = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_pr")
    rows = bitbucket.list_pull_request_commits(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    if not rows:
        raise Divergence("PR commits empty")
    for row in rows:
        _sha(row.get("hash"), "commit.hash")
    return f"{len(rows)} commits with 40-hex hashes"


def _bb_diff_whole(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, pr_id = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_pr")
    pr = bitbucket.get_pull_request(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    diff = bitbucket.get_pull_request_diff(base, repo, pr_id, token=token)  # type: ignore[arg-type]
    diffs = diff.get("diffs")
    if not isinstance(diffs, list) or not diffs:
        raise Divergence("whole diff empty")
    heads = {
        _sha(_mapping(pr.get("fromRef"), "fromRef").get("latestCommit"), "fromRef"),
        _sha(_mapping(pr.get("toRef"), "toRef").get("latestCommit"), "toRef"),
    }
    from_hash = _sha(diff.get("fromHash"), "fromHash")
    to_hash = _sha(diff.get("toHash"), "toHash")
    if from_hash not in heads and to_hash not in heads:
        raise Divergence("diff hashes match no PR ref head")
    if diff.get("contextLines") != 3:
        raise Divergence(f"default contextLines {diff.get('contextLines')} != 3")
    bound = "fromHash" if from_hash in heads else "toHash"
    return f"{len(diffs)} diffs, context=3, {bound} equals a PR ref head"


def _bb_diff_path(context: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        path = _fixture(ctx, "bb_pr_path")
        diff = bitbucket.get_pull_request_diff(
            base,
            _fixture(ctx, "bb_repo"),
            _fixture(ctx, "bb_pr"),
            token=token,
            context=context,
            path=path,  # type: ignore[arg-type]
        )
        diffs = diff.get("diffs")
        if not isinstance(diffs, list) or len(diffs) != 1:
            raise Divergence(
                f"path filter -> {len(diffs) if isinstance(diffs, list) else '?'} diffs"
            )
        if diff.get("contextLines") != context:
            raise Divergence(f"context {context} got {diff.get('contextLines')}")
        returned = _mapping(
            _mapping(diffs[0], "diff").get("destination"), "destination"
        ).get("toString")
        if returned != path:
            raise Divergence("diff path != requested path")
        return f"1 diff for requested path, context={context}"

    return run


def _bb_diff_triple(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    path = _fixture(ctx, "bb_pr_path")
    diff = bitbucket.get_pull_request_diff(
        base,
        _fixture(ctx, "bb_repo"),
        _fixture(ctx, "bb_pr"),
        token=token,
        path=path,
        source_path=path,
        context=1,  # type: ignore[arg-type]
    )
    if diff.get("contextLines") != 1:
        raise Divergence("triple lost context=1")
    diffs = diff.get("diffs")
    if not isinstance(diffs, list) or len(diffs) != 1:
        raise Divergence("triple lost the path filter")
    return "path+source_path+context=1 -> 1 diff"


def _bb_diff_source_without_path(ctx: Ctx) -> str:
    bitbucket.get_pull_request_diff(
        ctx.bitbucket.base_url,
        _fixture(ctx, "bb_repo"),
        _fixture(ctx, "bb_pr"),
        token=ctx.bitbucket.token,
        source_path="src/Main.java",  # type: ignore[arg-type]
    )
    return "source_path without path accepted"


def _bb_diff_fallback(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    result = bitbucket.get_pull_request_diff_with_fallback(
        base,
        _fixture(ctx, "bb_repo"),
        _fixture(ctx, "bb_pr"),
        token=token,  # type: ignore[arg-type]
    )
    if result.get("fallback") is not False:
        return (
            f"fallback={result.get('fallback')} reason={result.get('fallback_reason')}"
        )
    diffs = _mapping(result.get("diff"), "diff").get("diffs")
    if not isinstance(diffs, list) or not diffs:
        raise Divergence("fallback carries no diffs")
    return f"fallback=false, {len(diffs)} diffs"


def _bb_commit_diff(window: bool) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        repo, sha = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_commit_sha")
        paths = _fixture(ctx, "bb_commit_paths")
        assert isinstance(paths, list)
        if window:
            result = bitbucket.get_commit_diff(
                base,
                repo,
                sha,
                token=token,
                paths=paths,
                context=1,  # type: ignore[arg-type]
            )
            if not isinstance(result, list) or len(result) != len(paths):
                raise Divergence(
                    f"paths request -> {len(result) if isinstance(result, list) else '?'} objects"
                )
            for index, row in enumerate(result):
                diffs = _mapping(row, "diff object").get("diffs")
                if not isinstance(diffs, list) or not diffs:
                    raise Divergence("path diff object has no diffs")
                returned = _mapping(
                    _mapping(diffs[0], "diff").get("destination"), "destination"
                ).get("toString")
                if returned != paths[index]:
                    raise Divergence("path diff order/content mismatch")
            return f"paths={len(paths)} context=1 -> {len(result)} diff objects"
        result = bitbucket.get_commit_diff(base, repo, sha, token=token)  # type: ignore[arg-type]
        diffs = _mapping(result, "diff").get("diffs")
        if not isinstance(diffs, list) or not diffs:
            raise Divergence("whole commit diff empty")
        return f"whole commit {str(sha)[:8]} -> {len(diffs)} diffs"

    return run


def _bb_branches(filtered: bool) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs = {"filter_text": "feature"} if filtered else {}
        rows = bitbucket.list_branches(
            base, _fixture(ctx, "bb_repo"), token=token, **kwargs
        )  # type: ignore[arg-type]
        if not rows:
            raise Divergence("branches empty")
        defaults = [row for row in rows if row.get("default")]
        if len(defaults) > 1:
            raise Divergence(f"{len(defaults)} default branches")
        if not filtered and len(defaults) != 1:
            raise Divergence("unfiltered branch list has no default")
        if filtered and not all(
            str(row.get("name", "")).startswith("feature") for row in rows
        ):
            raise Divergence("filter_text leaked non-matching branches")
        return f"{'filter' if filtered else 'all'} -> {len(rows)} branches, {len(defaults)} default"

    return run


def _bb_tag(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    name = _fixture(ctx, "bb_tag")
    tag = bitbucket.get_tag(base, _fixture(ctx, "bb_repo"), name, token=token)  # type: ignore[arg-type]
    if tag.get("displayId") != name:
        raise Divergence(f"requested tag {name} got {tag.get('displayId')}")
    _sha(tag.get("latestCommit"), "tag.latestCommit")
    return f"tag {name} -> pinned 40-hex commit"


def _bb_tags(limit: int, order_by: str | None, filtered: bool) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs: dict[str, object] = {"limit": limit}
        if order_by is not None:
            kwargs["order_by"] = order_by
        if filtered:
            kwargs["filter_text"] = "rc."
        rows = bitbucket.list_tags(
            base, _fixture(ctx, "bb_repo"), token=token, **kwargs
        )  # type: ignore[arg-type]
        _bounded(rows, limit, "tags")
        if not rows:
            raise Divergence("tags empty")
        names = [str(row.get("displayId")) for row in rows]
        if filtered and not all("rc." in name for name in names):
            raise Divergence("filter_text leaked non-matching tags")
        if order_by == "ALPHABETICAL" and names != sorted(names):
            raise Divergence("ALPHABETICAL order violated")
        return f"limit={limit} order={order_by or 'default'} filter={filtered} -> {len(names)} tags"

    return run


def _bb_tags_truncation(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo = _fixture(ctx, "bb_repo")
    limited = bitbucket.list_tags_with_metadata(base, repo, token=token, limit=2)
    if limited["limit"] != 2 or len(limited["tags"]) != 2 or limited["complete"] is not False:
        return (
            f"limit=2 -> rows={len(limited['tags'])} complete={limited['complete']}; "
            "cap not observable"
        )
    full = bitbucket.list_tags_with_metadata(base, repo, token=token, limit=1000)
    if full["complete"] is not True or len(full["tags"]) <= 2:
        return f"repo has {len(full['tags'])} tags, cap not observable"
    return (
        f"limit=2 of {len(full['tags'])} tags -> complete=False (truncated); "
        f"limit=1000 -> complete=True"
    )

def _bb_blame(pinned: bool) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs = {"at": _fixture(ctx, "bb_commit_sha")} if pinned else {}
        rows = bitbucket.get_file_blame(
            base,
            _fixture(ctx, "bb_repo"),
            _fixture(ctx, "bb_java_path"),
            token=token,
            **kwargs,  # type: ignore[arg-type]
        )
        if not rows:
            raise Divergence("blame empty")
        for index, row in enumerate(rows, start=1):
            if _int(row.get("line"), "line") != index:
                raise Divergence(f"blame line {index} != {row.get('line')}")
            _sha(row.get("commit"), "blame commit")
            if _DATE.fullmatch(str(row.get("date"))) is None:
                raise Divergence("blame date not YYYY-MM-DD")
        return f"{'at=commit' if pinned else 'at=default'} -> {len(rows)} lines 1..n"

    return run


def _bb_last_modified(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    document = bitbucket.get_last_modified(
        base,
        _fixture(ctx, "bb_repo"),
        token=token,
        at=_fixture(ctx, "bb_commit_sha"),  # type: ignore[arg-type]
    )
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise Divergence("repo last-modified has no files object")
    for commit in files.values():
        _sha(_mapping(commit, "file commit").get("id"), "file commit")
    _sha(
        _mapping(document.get("latestCommit"), "latestCommit").get("id"), "latestCommit"
    )
    return f"at=commit -> files={len(files)} latestCommit 40-hex"


def _bb_last_modified_path(ctx: Ctx) -> str:
    """Directory path form: the documented request answers 200 on this server."""
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    document = bitbucket.get_last_modified(
        base,
        _fixture(ctx, "bb_repo"),
        path=_fixture(ctx, "bb_java_dir"),  # type: ignore[arg-type]
        token=token,
        at=_fixture(ctx, "bb_commit_sha"),  # type: ignore[arg-type]
    )
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise Divergence("directory last-modified has no files object")
    latest = _sha(
        _mapping(document.get("latestCommit"), "latestCommit").get("id"),
        "latestCommit",
    )
    return (
        f"directory+at=commit -> 200, files={len(files)}, "
        f"latestCommit={latest[:10]}… 40-hex"
    )


def _bb_last_modified_file(ctx: Ctx) -> str:
    """File path form: a server-side 500 becomes a readable hint, not raw HTTP 500."""
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    try:
        bitbucket.get_last_modified(
            base,
            _fixture(ctx, "bb_repo"),
            path=_fixture(ctx, "bb_java_path"),  # type: ignore[arg-type]
            token=token,
            at=_fixture(ctx, "bb_commit_sha"),  # type: ignore[arg-type]
        )
    except AtlaWireError as exc:
        message = str(exc)
        if exc.category != "upstream" or exc.http_status != 500:
            raise Divergence(f"file path error category {exc.category}/{exc.http_status}") from None
        if "path names a file" not in message or "repository-root" not in message:
            raise Divergence("file path error does not name the workaround") from None
        if "HTTP 500" in message:
            raise Divergence("raw HTTP 500 leaked to the caller") from None
        return "file path -> readable upstream error with root/directory hint"
    raise Divergence("file path last-modified unexpectedly succeeded")


def _bb_last_modified_default(ctx: Ctx) -> str:
    """Omitted at: the function resolves the default branch tip itself."""
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    document = bitbucket.get_last_modified(base, _fixture(ctx, "bb_repo"), token=token)
    files = document.get("files")
    if not isinstance(files, dict) or not files:
        raise Divergence("default last-modified has no files object")
    latest = _sha(
        _mapping(document.get("latestCommit"), "latestCommit").get("id"),
        "latestCommit",
    )
    expected = _sha(_fixture(ctx, "bb_default_commit"), "default branch commit")
    if latest != expected:
        raise Divergence("default last-modified did not resolve the default branch tip")
    return f"default at -> files={len(files)} latestCommit == default branch tip"

def _bb_commits(at: bool, path_fixture: str | None, limit: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs: dict[str, object] = {"limit": limit}
        if at:
            kwargs["at"] = _fixture(ctx, "bb_commit_sha")
        if path_fixture is not None:
            kwargs["path"] = _fixture(ctx, path_fixture)
        rows = bitbucket.list_commits(
            base, _fixture(ctx, "bb_repo"), token=token, **kwargs
        )  # type: ignore[arg-type]
        _bounded(rows, limit, "commits")
        if not rows:
            raise Divergence("commits empty")
        for row in rows:
            _sha(row.get("hash"), "commit.hash")
        if at and rows[0]["hash"] != _fixture(ctx, "bb_commit_sha"):
            raise Divergence("at=commit did not put that commit first")
        return f"at={at} path={path_fixture is not None} limit={limit} -> {len(rows)} commits"

    return run


def _bb_commit(ctx: Ctx) -> str:
    base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
    repo, sha = _fixture(ctx, "bb_repo"), _fixture(ctx, "bb_commit_sha")
    assert isinstance(sha, str)
    whole = bitbucket.get_commit(base, repo, sha, token=token)
    short = bitbucket.get_commit(base, repo, sha[:10], token=token)
    if whole.get("id") != short.get("id") or not str(whole.get("id", "")).startswith(
        sha[:10]
    ):
        raise Divergence("abbreviated SHA resolved to another commit")
    return f"full and {sha[:10]} resolve to the same 40-hex commit"


# ---------------------------------------------------------------------------
# Jira rows
# ---------------------------------------------------------------------------


def _jira_transitions(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    rows = jira.list_transitions(base, _fixture(ctx, "jira_issue"), token=token)  # type: ignore[arg-type]
    if not rows:
        raise Divergence("transitions empty")
    for row in rows:
        _text(row.get("id"), "transition.id")
        _text(row.get("name"), "transition.name")
        _text(row.get("to_status"), "transition.to_status")
    return f"{len(rows)} transitions with id/name/to_status"


def _jira_statuses(ctx: Ctx) -> str:
    rows = jira.list_statuses(ctx.jira.base_url, token=ctx.jira.token)
    if not rows:
        raise Divergence("statuses empty")
    if rows != sorted(rows) or len(set(rows)) != len(rows):
        raise Divergence("statuses not sorted unique")
    return f"{len(rows)} sorted unique status names"


def _jira_reference(name: str, keywords: tuple[str, ...]) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        rows = getattr(jira, name)(ctx.jira.base_url, token=ctx.jira.token)
        if not isinstance(rows, list) or not rows:
            raise Divergence(f"{name} empty")
        for row in rows:
            if not isinstance(row, dict):
                raise Divergence(f"{name} row not an object")
            for keyword in keywords:
                if keyword not in row:
                    raise Divergence(f"{name} row lacks {keyword}")
        return f"{len(rows)} rows with {', '.join(keywords)}"

    return run


def _jira_projects(ctx: Ctx) -> str:
    rows = jira.list_jira_projects(ctx.jira.base_url, token=ctx.jira.token)
    if not rows:
        raise Divergence("projects empty")
    for row in rows:
        _text(row.get("key"), "project.key")
        _text(row.get("name"), "project.name")
    return f"{len(rows)} projects with key/name"


def _jira_users(start_at: int, max_results: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.jira.base_url, ctx.jira.token
        query = _fixture(ctx, "jira_user_query")
        rows = jira.search_users(
            base,
            query,  # type: ignore[arg-type]
            token=token,
            start_at=start_at,
            max_results=max_results,
        )
        _bounded(rows, max_results, "users")
        if rows:
            _text(rows[0].get("name"), "user.name")
        if start_at == 1 and rows:
            page_one = jira.search_users(base, query, token=token, max_results=1)  # type: ignore[arg-type]
            if page_one and page_one[0]["name"] == rows[0]["name"]:
                raise Divergence("start_at=1 repeated the first row")
        return f"start={start_at} max={max_results} -> {len(rows)} users"

    return run


def _jira_titles(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    keys = _fixture(ctx, "jira_title_keys")
    titles = jira.titles(base, keys, token=token)  # type: ignore[arg-type]
    if not isinstance(titles, dict):
        raise Divergence("titles not a mapping")
    known = jira.search_issues(base, "order by updated DESC", token=token, limit=5)
    expected = {
        row["key"]: row["summary"]
        for row in known
        if row["key"] in set(keys)  # type: ignore[arg-type]
    }
    if titles != expected:
        raise Divergence("titles differ from search_issues summaries")
    return f"{len(keys)} keys -> {len(titles)} titles equal search summaries"


def _jira_titles_duplicates(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    keys = _fixture(ctx, "jira_title_keys")
    assert isinstance(keys, list)
    doubled = [keys[0], keys[0], keys[1]] if len(keys) > 1 else [keys[0], keys[0]]
    titles = jira.titles(base, doubled, token=token)
    if len(titles) != len(set(doubled)):
        raise Divergence("duplicate keys produced duplicate titles")
    return f"{len(doubled)} keys ({len(set(doubled))} unique) -> {len(titles)} titles"


def _jira_changelog(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    document = jira.get_issue_changelog(base, _fixture(ctx, "jira_issue"), token=token)  # type: ignore[arg-type]
    histories = document.get("histories")
    if not isinstance(histories, list) or not histories:
        raise Divergence("changelog histories empty")
    total = _int(document.get("total"), "total")
    cap = _int(document.get("maxResults"), "maxResults")
    if total < len(histories) or cap < len(histories):
        raise Divergence("histories exceed total/maxResults")
    return f"{len(histories)} histories, total={total}, cap={cap}"


def _jira_worklogs(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    document = jira.get_issue_worklogs(
        base, _fixture(ctx, "jira_worklog_issue"), token=token
    )  # type: ignore[arg-type]
    rows = _objects(document.get("worklogs"), "worklogs")
    if _int(document.get("total"), "total") != len(rows):
        raise Divergence("total != returned worklogs (page cap?)")
    for row in rows:
        _text(row.get("id"), "worklog.id")
        if "started" not in row or "timeSpentSeconds" not in row:
            raise Divergence("worklog lacks started/timeSpentSeconds")
    return f"{len(rows)} worklogs with total/started/timeSpentSeconds"


def _jira_links(ctx: Ctx) -> str:
    base, token = ctx.jira.base_url, ctx.jira.token
    rows = jira.list_issue_remote_links(
        base, _fixture(ctx, "jira_links_issue"), token=token
    )  # type: ignore[arg-type]
    if not rows:
        return "remote links empty for fixture issue"
    for row in rows:
        if "globalId" not in row and "id" not in row:
            raise Divergence("remote link has no id/globalId")
        _mapping(row.get("object"), "remote link object")
    return f"{len(rows)} remote links with object/id"


# ---------------------------------------------------------------------------
# Federated, identity, grep, scan rows
# ---------------------------------------------------------------------------


def _whoami(ctx: Ctx) -> str:
    checks = identity.whoami(
        confluence=ctx.confluence, jira=ctx.jira, bitbucket=ctx.bitbucket
    )
    for product in ("confluence", "jira"):
        entry = _mapping(checks.get(product), product)
        if entry.get("ok") is not True or not isinstance(entry.get("identity"), dict):
            raise Divergence(f"{product} identity not ok")
    if _mapping(checks.get("bitbucket"), "bitbucket").get("authenticated") is not True:
        raise Divergence("bitbucket not authenticated")
    return "confluence+jira identity ok, bitbucket authenticated"


def _federated(terms: list[str], limit: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        result = federated.federated_search(
            terms,
            confluence=ctx.confluence,
            jira=ctx.jira,
            bitbucket=ctx.bitbucket,
            limit=limit,
        )
        counts = _mapping(result.get("counts"), "counts")
        cap = limit * len(terms)
        for product in ("confluence", "jira", "bitbucket"):
            if _int(counts.get(product), f"counts.{product}") > cap:
                raise Divergence(f"{product} count > per-term cap {cap}")
        budget = _mapping(result.get("budget"), "budget")
        if _int(budget.get("limit"), "budget.limit") < limit:
            raise Divergence("budget below requested limit")
        errors = result.get("errors")
        if isinstance(errors, dict) and errors:
            raise Divergence(f"federated errors: {sorted(errors)}")
        return f"terms={len(terms)} limit={limit} -> " + "/".join(
            str(counts.get(product)) for product in ("confluence", "jira", "bitbucket")
        )

    return run


def _grep(
    pattern: str | None, at: bool, path: bool, limit: int
) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs: dict[str, object] = {"limit": limit}
        if at:
            kwargs["at"] = _fixture(ctx, "bb_commit_sha")
        if pattern is not None:
            kwargs["glob"] = "*.java"
            if path:
                kwargs["path"] = _fixture(ctx, "bb_java_dir")
        result = repo_grep.grep_repository(
            base,
            _fixture(ctx, "bb_repo"),
            pattern,
            token=token,
            **kwargs,  # type: ignore[arg-type]
        )
        _sha(result.get("commit"), "grep.commit")
        hits = result.get("hits")
        files = result.get("files")
        if not isinstance(hits, list) or not isinstance(files, list):
            raise Divergence("grep result lacks hits/files arrays")
        if pattern is None:
            _bounded(files, limit, "listed files")
            if hits:
                raise Divergence("listing mode returned hits")
            expected_engine = "listing"
        else:
            _bounded(hits, limit, "hits")
            expected_engine = "fanout"
            if not all(str(hit["file"]).endswith(".java") for hit in hits):
                raise Divergence("glob filter leaked non-java files")
            if path:
                directory = str(_fixture(ctx, "bb_java_dir"))
                if not all(
                    str(hit["file"]).startswith(directory + "/") for hit in hits
                ):
                    raise Divergence("path filter leaked other directories")
        if result.get("engine") != expected_engine:
            raise Divergence(f"engine {result.get('engine')} != {expected_engine}")
        truncated = result.get("truncated")
        complete = result.get("complete")
        if not isinstance(truncated, bool) or not isinstance(complete, bool):
            raise Divergence("truncated/complete not booleans")
        if complete == truncated:
            raise Divergence("complete and truncated contradict")
        status = result.get("status")
        message = result.get("message")
        if status not in ("complete", "truncated", "timeout"):
            raise Divergence(f"grep status {status!r} outside the contract")
        if complete is not (status == "complete"):
            raise Divergence("grep status contradicts complete")
        if status == "complete" and message is not None:
            raise Divergence("complete grep carries a budget message")
        count = len(files) if pattern is None else len(hits)
        return (
            f"{expected_engine} at={at} path={path} limit={limit} -> {count} rows, "
            f"status={status}"
        )

    return run


def _scan(project: str | None, workers: int) -> Callable[[Ctx], str]:
    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        kwargs: dict[str, object] = {"workers": workers}
        if project is not None:
            kwargs["project"] = project
        rows = repo_scan.scan_repository_extensions(base, "java", token=token, **kwargs)  # type: ignore[arg-type]
        if not rows:
            raise Divergence("scan returned no repository")
        for row in rows:
            files = _int(row.get("files"), "files")
            matched = _int(row.get("matched"), "matched")
            if matched > files:
                raise Divergence("matched > files")
            sample = row.get("sample")
            if not isinstance(sample, list) or not sample:
                raise Divergence("no sample paths")
            if not all(str(path).endswith(".java") for path in sample):
                raise Divergence("sample has non-java path")
            if project is not None and row.get("project") != project:
                raise Divergence("project filter leaked another project")
        return (
            f"project={project} workers={workers} -> {len(rows)} repos with java files"
        )

    return run


def _scan_report(max_pages: int) -> Callable[[Ctx], str]:
    """A page-budget cut must publish counters and the rows read so far."""

    def run(ctx: Ctx) -> str:
        base, token = ctx.bitbucket.base_url, ctx.bitbucket.token
        report = repo_scan.scan_repository_extensions_report(
            base,
            "java",
            token=token,
            max_pages=max_pages,
        )
        if report.get("complete") is not False:
            raise Divergence("partial scan reported complete")
        scanned = _int(report.get("repositories_scanned"), "repositories_scanned")
        total = _int(report.get("repositories_total"), "repositories_total")
        if not 0 <= scanned < total:
            raise Divergence(f"scanned {scanned} not below total {total}")
        reason = _text(report.get("reason"), "reason")
        if "page limit" not in reason.lower():
            raise Divergence(f"reason is not a page-budget stop: {reason[:80]}")
        rows = _objects(report.get("rows"), "rows")
        if not rows:
            raise Divergence("partial scan kept no rows although walks finished")
        for row in rows:
            files = _int(row.get("files"), "files")
            matched = _int(row.get("matched"), "matched")
            if not 0 <= matched <= files:
                raise Divergence("matched > files")
            sample = row.get("sample")
            if not isinstance(sample, list) or not sample:
                raise Divergence("no sample paths")
            if not all(str(path).endswith(".java") for path in sample):
                raise Divergence("sample has a non-java path")
        return (
            f"complete=False scanned={scanned} < total={total}, rows={len(rows)}, "
            "reason=page limit"
        )

    return run


# ---------------------------------------------------------------------------
# Plan, runner and CLI
# ---------------------------------------------------------------------------


def build_plan(project: str) -> tuple[Check, ...]:
    path_file = "bb_commit_path"
    return (
        # Confluence: page reads, expansions and formats.
        Check("confluence.get_page", "single page", "fields", _conf_page),
        Check(
            "confluence.get_page",
            "expand=body.storage",
            "dup",
            _conf_expand("body.storage"),
        ),
        Check(
            "confluence.get_page",
            "expand=version",
            "freshness",
            _conf_expand("version"),
        ),
        Check("confluence.get_page", "expand=space", "dup", _conf_expand("space")),
        Check(
            "confluence.get_page", "expand=ancestors", "dup", _conf_expand("ancestors")
        ),
        Check(
            "confluence.get_page",
            "format storage/markdown/json",
            "cross",
            _conf_formats,
        ),
        Check("confluence.list_children", "limit=1", "bound", _conf_children(1)),
        Check("confluence.list_children", "limit=3", "bound", _conf_children(3)),
        Check("confluence.list_children", "limit=0", "low", _conf_children(0)),
        Check(
            "confluence.list_children", "default limit", "bound", _conf_children(None)
        ),
        Check(
            "confluence.list_children",
            "limit=1 under cap",
            "bound",
            _conf_children_truncation,
        ),
        Check("confluence.list_spaces", "limit=1", "bound", _conf_spaces(1)),
        Check("confluence.list_spaces", "limit=5", "bound", _conf_spaces(5)),
        Check("confluence.list_spaces", "limit=0", "low", _conf_spaces(0)),
        Check(
            "confluence.list_spaces", "default limit", "discover", _conf_spaces(None)
        ),
        Check(
            "confluence.get_page_comments",
            "limit=1",
            "bound",
            _conf_comments(0, 1, True),
        ),
        Check(
            "confluence.get_page_comments",
            "limit=5",
            "bound",
            _conf_comments(0, 5, True),
        ),
        Check(
            "confluence.get_page_comments",
            "include_replies=false",
            "scope",
            _conf_comments(0, 5, False),
        ),
        Check(
            "confluence.get_page_comments",
            "start=1 limit=2 replies=false",
            "low",
            _conf_comments(1, 2, False),
        ),
        Check(
            "confluence.get_page_comments",
            "limit=1 under cap",
            "bound",
            _conf_comments_truncation,
        ),
        Check("confluence.get_page_labels", "limit=1", "bound", _conf_labels(1)),
        Check(
            "confluence.get_page_labels", "default limit", "discover", _conf_labels(200)
        ),
        Check(
            "confluence.get_page_attachments",
            "limit=1",
            "bound",
            _conf_attachments(0, 1),
        ),
        Check(
            "confluence.get_page_attachments",
            "limit=10",
            "bound",
            _conf_attachments(0, 10),
        ),
        Check(
            "confluence.get_page_attachments",
            "start=1 limit=2",
            "low",
            _conf_attachments(1, 2),
        ),
        Check(
            "confluence.get_page_attachments",
            "limit=1 under cap",
            "bound",
            _conf_attachments_truncation,
        ),
        Check("confluence.get_page_history", "single page", "freshness", _conf_history),
        Check(
            "confluence.get_page_version",
            "version=1",
            "freshness",
            _conf_version("first"),
        ),
        Check(
            "confluence.get_page_version",
            "version=previous",
            "audit",
            _conf_version("previous"),
        ),
        Check(
            "confluence.get_page_version",
            "version=current",
            "dup",
            _conf_version("current"),
        ),
        # Bitbucket: PR, diff, commit, ref and file reads.
        Check("bitbucket.get_pull_request", "single PR", "review", _bb_pr),
        Check("bitbucket.list_pull_request_files", "single PR", "review", _bb_pr_files),
        Check(
            "bitbucket.list_pull_request_comments",
            "max_pages=1",
            "review",
            _bb_pr_comments,
        ),
        Check(
            "bitbucket.list_pull_request_commits", "single PR", "review", _bb_pr_commits
        ),
        Check("bitbucket.get_pull_request_diff", "whole PR", "scope", _bb_diff_whole),
        Check(
            "bitbucket.get_pull_request_diff", "path=file", "scope", _bb_diff_path(3)
        ),
        Check(
            "bitbucket.get_pull_request_diff", "context=0", "scope", _bb_diff_path(0)
        ),
        Check(
            "bitbucket.get_pull_request_diff",
            "path+source_path+context=1",
            "low",
            _bb_diff_triple,
        ),
        Check(
            "bitbucket.get_pull_request_diff",
            "source_path without path",
            "low",
            _bb_diff_source_without_path,
            expect_error="any",
        ),
        Check(
            "bitbucket.get_pull_request_diff_with_fallback",
            "whole PR",
            "scope",
            _bb_diff_fallback,
        ),
        Check(
            "bitbucket.get_commit_diff", "whole commit", "scope", _bb_commit_diff(False)
        ),
        Check(
            "bitbucket.get_commit_diff",
            "paths+context=1",
            "scope",
            _bb_commit_diff(True),
        ),
        Check("bitbucket.list_branches", "all", "discover", _bb_branches(False)),
        Check(
            "bitbucket.list_branches",
            "filter_text=feature",
            "discover",
            _bb_branches(True),
        ),
        Check("bitbucket.get_tag", "exact name", "freshness", _bb_tag),
        Check("bitbucket.list_tags", "limit=2", "bound", _bb_tags(2, None, False)),
        Check(
            "bitbucket.list_tags",
            "limit=5 order=ALPHABETICAL",
            "bound",
            _bb_tags(5, "ALPHABETICAL", False),
        ),
        Check(
            "bitbucket.list_tags",
            "filter_text=rc. + limit=3",
            "discover",
            _bb_tags(3, None, True),
        ),
        Check(
            "bitbucket.list_tags",
            "limit=3 order=MODIFICATION filter=rc.",
            "low",
            _bb_tags(3, "MODIFICATION", True),
        ),
        Check("bitbucket.list_tags", "limit=2 under cap", "bound", _bb_tags_truncation),
        Check("bitbucket.get_file_blame", "at=default", "trace", _bb_blame(False)),
        Check("bitbucket.get_file_blame", "at=commit", "trace", _bb_blame(True)),
        Check(
            "bitbucket.get_last_modified", "repo at=commit", "trace", _bb_last_modified
        ),
        Check(
            "bitbucket.get_last_modified",
            "directory+at=commit",
            "trace",
            _bb_last_modified_path,
        ),
        Check(
            "bitbucket.get_last_modified",
            "file+at=commit",
            "trace",
            _bb_last_modified_file,
        ),
        Check(
            "bitbucket.get_last_modified",
            "default at",
            "trace",
            _bb_last_modified_default,
        ),
        Check(
            "bitbucket.list_commits", "limit=3", "audit", _bb_commits(False, None, 3)
        ),
        Check(
            "bitbucket.list_commits", "at=commit", "audit", _bb_commits(True, None, 3)
        ),
        Check(
            "bitbucket.list_commits",
            "path+limit=3",
            "audit",
            _bb_commits(False, path_file, 3),
        ),
        Check(
            "bitbucket.list_commits",
            "at+path+limit=1",
            "trace",
            _bb_commits(True, path_file, 1),
        ),
        Check("bitbucket.get_commit", "full and abbreviated SHA", "dup", _bb_commit),
        # Jira reference and issue subresources.
        Check("jira.list_transitions", "single issue", "fields", _jira_transitions),
        Check("jira.list_statuses", "no parameters", "discover", _jira_statuses),
        Check(
            "jira.list_priorities",
            "no parameters",
            "discover",
            _jira_reference("list_priorities", ("id", "name")),
        ),
        Check(
            "jira.list_issue_types",
            "no parameters",
            "discover",
            _jira_reference("list_issue_types", ("id", "name")),
        ),
        Check(
            "jira.list_resolutions",
            "no parameters",
            "discover",
            _jira_reference("list_resolutions", ("id", "name")),
        ),
        Check(
            "jira.list_status_categories",
            "no parameters",
            "discover",
            _jira_reference("list_status_categories", ("id", "key")),
        ),
        Check("jira.list_jira_projects", "no parameters", "discover", _jira_projects),
        Check("jira.search_users", "max_results=5", "discover", _jira_users(0, 5)),
        Check("jira.search_users", "max_results=1", "bound", _jira_users(0, 1)),
        Check(
            "jira.search_users", "start_at=1 max_results=2", "low", _jira_users(1, 2)
        ),
        Check("jira.titles", "three known keys", "cross", _jira_titles),
        Check("jira.titles", "duplicate keys", "dup", _jira_titles_duplicates),
        Check("jira.get_issue_changelog", "single issue", "audit", _jira_changelog),
        Check("jira.get_issue_worklogs", "single issue", "fields", _jira_worklogs),
        Check("jira.list_issue_remote_links", "single issue", "fields", _jira_links),
        # Federated, identity, grep, scan.
        Check("identity.whoami", "all three products", "freshness", _whoami),
        Check(
            "federated_search",
            "1 term limit=10",
            "discover",
            _federated(["address-book"], 10),
        ),
        Check(
            "federated_search",
            "2 terms limit=2",
            "discover",
            _federated(["address-book", "billing"], 2),
        ),
        Check(
            "repo_grep.grep_repository",
            "pattern+glob limit=5",
            "coverage",
            _grep("ContactGroup", False, False, 5),
        ),
        Check(
            "repo_grep.grep_repository",
            "path+pattern+limit=10",
            "coverage",
            _grep("ContactGroup", False, True, 10),
        ),
        Check(
            "repo_grep.grep_repository",
            "at+path+pattern+limit=10",
            "low",
            _grep("ContactGroup", True, True, 10),
        ),
        Check(
            "repo_grep.grep_repository",
            "listing pattern=None limit=5",
            "bound",
            _grep(None, False, False, 5),
        ),
        Check(
            "repo_scan.scan_repository_extensions_report",
            "extension=java max_pages=1 (partial)",
            "coverage",
            _scan_report(1),
        ),
        Check(
            "repo_scan.scan_repository_extensions",
            "extension+project",
            "coverage",
            _scan(project, 8),
        ),
        Check(
            "repo_scan.scan_repository_extensions",
            "extension+project+workers=2",
            "low",
            _scan(project, 2),
        ),
    )


def _run_check(check: Check, ctx: Ctx) -> tuple[int, str]:
    try:
        fact = check.run(ctx)
    except Divergence as exc:
        return 2, str(exc)
    except AtlaWireError as exc:
        status = exc.http_status
        if status in _AUTH_STOP:
            raise StopRun(status) from None
        category = exc.category or "-"
        if check.expect_error == "any":
            return 0, f"err={category}/{status} (expected)"
        if check.expect_error == category:
            return 0, f"err={category} (expected)"
        return 1, f"err={category}/{status}"
    except (TimeoutError, OSError) as exc:
        return 1, f"transport={type(exc).__name__}"
    return 0, fact


def _parse(argv: Sequence[str]) -> tuple[bool, int, bool] | None:
    live, timeout, help_seen, seen, index = False, _TIMEOUT_DEFAULT, False, False, 0
    while index < len(argv):
        token = argv[index]
        if token in {"--help", "-h"}:
            help_seen, index = True, index + 1
        elif token == "--live":
            if live:
                return None
            live, index = True, index + 1
        elif token == "--timeout" or token.startswith("--timeout="):
            if seen:
                return None
            seen = True
            if token == "--timeout":
                if index + 1 >= len(argv):
                    return None
                value = argv[index + 1]
                index += 2
            else:
                value = token.partition("=")[2]
                index += 1
            if len(value) > 3 or not value.isascii() or not value.isdigit():
                return None
            seconds = int(value)
            if not _TIMEOUT_MIN <= seconds <= _TIMEOUT_MAX:
                return None
            timeout = seconds
        else:
            return None
    return live, timeout, help_seen


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the matrix; without ``--live`` nothing starts."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    stdout = sys.stdout if out is None else out
    stderr = sys.stderr if err is None else err
    parsed = _parse(arguments)
    if parsed is None:
        print("e2e-param-matrix: invalid arguments; use --help", file=stderr)
        return EXIT_USAGE
    live, timeout, help_seen = parsed
    if help_seen:
        print(_HELP, file=stdout)
        return EXIT_OK
    if not live:
        print("e2e-param-matrix: opt-in required; pass --live", file=stderr)
        return EXIT_USAGE
    try:
        products = {
            product: load_saved_credentials(product, allow_http_loopback=False)
            for product in ("confluence", "jira", "bitbucket")
        }
    except AtlaWireError as exc:
        print(f"e2e-param-matrix: FAIL configuration ({exc.category})", file=stderr)
        return EXIT_USAGE
    ctx = Ctx(
        confluence=ProductTarget(
            base_url=products["confluence"].base_url, token=products["confluence"].token
        ),
        jira=ProductTarget(
            base_url=products["jira"].base_url, token=products["jira"].token
        ),
        bitbucket=ProductTarget(
            base_url=products["bitbucket"].base_url, token=products["bitbucket"].token
        ),
    )
    ctx.fixtures["timeout"] = timeout
    try:
        _discover(ctx)
    except StopRun as exc:
        print(f"STOP http={exc.status} during fixture discovery", file=stdout)
        return EXIT_FAIL
    except AtlaWireError as exc:
        print(f"e2e-param-matrix: FAIL fixture discovery ({exc.category})", file=stdout)
        return EXIT_FAIL
    print(
        "fixtures: "
        f"confluence page={ctx.fixtures.get('conf_page')} "
        f"space={ctx.fixtures.get('conf_space')} "
        f"children={ctx.fixtures.get('conf_children_page')}/{ctx.fixtures.get('conf_children_total')} "
        f"comments={ctx.fixtures.get('conf_comments_page')}/{ctx.fixtures.get('conf_comments_total')} "
        f"labels={ctx.fixtures.get('conf_labels_page')}/{ctx.fixtures.get('conf_labels_total')} "
        f"attachments={ctx.fixtures.get('conf_attachments_page')}/{ctx.fixtures.get('conf_attachments_total')}",
        file=stdout,
    )
    print(
        "fixtures: "
        f"jira issue={ctx.fixtures.get('jira_issue')} "
        f"worklogs={ctx.fixtures.get('jira_worklog_issue')} "
        f"links={ctx.fixtures.get('jira_links_issue')}",
        file=stdout,
    )
    print(
        "fixtures: "
        f"bitbucket repo={ctx.fixtures.get('bb_repo')} "
        f"pr={ctx.fixtures.get('bb_pr')} project={ctx.fixtures.get('bb_project')}",
        file=stdout,
    )
    project = str(ctx.fixtures.get("bb_project", ""))
    failures = 0
    plan = build_plan(project)
    for check in plan:
        try:
            exit_code, fact = _run_check(check, ctx)
        except StopRun as exc:
            print(
                f"STOP http={exc.status}; {failures} rows failed before stop",
                file=stdout,
            )
            print("e2e-param-matrix: FAIL", file=stdout)
            return EXIT_FAIL
        verdict = (
            "OK" if exit_code == 0 else ("DIVERGENCE" if exit_code == 2 else "ERROR")
        )
        if exit_code != 0:
            failures += 1
        print(
            f"{check.func} | {check.combo} | {exit_code} | {fact} | {verdict} | {check.applies}",
            file=stdout,
        )
    print(
        f"e2e-param-matrix: {'PASS' if not failures else 'FAIL'} "
        f"({len(plan)} rows, {failures} failed)",
        file=stdout,
    )
    return EXIT_OK if not failures else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())

"""Command-line entry point for AtlaWire."""

import json
import os
import re
import sys
from io import TextIOWrapper
from typing import cast

import click

from atlawire import __version__
from atlawire.bitbucket import (
    Branch,
    Commit,
    PullRequestComment,
    PullRequestFile,
    get_pull_request,
    get_pull_request_diff,
    get_pull_request_diff_text,
    get_pull_request_file,
    get_repository_file,
    list_branches,
    list_commits,
    list_projects,
    list_pull_request_comments,
    list_pull_request_files,
    list_repositories,
)
from atlawire.confluence import (
    CHILD_LIMIT_DEFAULT,
    CHILD_LIMIT_MAX,
    CHILD_LIMIT_MIN,
    CQL_LIMIT_MAX,
    CQL_LIMIT_MIN,
    SPACE_LIMIT_DEFAULT,
    SPACE_LIMIT_MAX,
    SPACE_LIMIT_MIN,
    get_page,
    list_children,
    list_spaces,
    search_cql,
)
from atlawire.confluence_markdown import render_page_markdown
from atlawire.http import AtlaWireError
from atlawire.issue_markdown import render_issue_markdown
from atlawire.jira import (
    SEARCH_LIMIT_MAX,
    SEARCH_LIMIT_MIN,
    get_issue,
    search_issues,
)

_TSV_CONTROLS = re.compile(r"[\\\x00-\x1f\x7f-\x9f\u2028\u2029]")
_TSV_ESCAPES = {"\\": r"\\", "\t": r"\t", "\r": r"\r", "\n": r"\n"}
_JQL_COLUMNS = "key\tstatus\ttype\tpriority\tassignee\tupdated\tsummary"
_CQL_COLUMNS = "id\tspace\ttype\ttitle\turl"
_SPACE_COLUMNS = "key\tname\ttype"
_CHILD_COLUMNS = "id\ttitle\tversion"
_PROJECT_COLUMNS = "key\tname\tpublic"
_FILE_COLUMNS = "path\ttype\tnode"
_COMMENT_COLUMNS = "id\tauthor\tpath\tline\ttext"
_BRANCH_COLUMNS = "name\tcommit\tdefault"
_COMMIT_COLUMNS = "hash\tdate\tauthor\tmessage"
_COMMIT_MESSAGE_MAX = 160


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="atlawire")
@click.pass_context
def cli(context: click.Context) -> None:
    """Work with self-hosted Jira, Confluence, and Bitbucket."""
    if context.invoked_subcommand is None:
        click.echo(context.get_help())


def _tsv_cell(value: str | int | bool | None) -> str:
    text = "" if value is None else str(value)
    return _TSV_CONTROLS.sub(
        lambda match: _TSV_ESCAPES.get(match[0], ascii(match[0])[1:-1]), text
    )


def _write_exact_text(text: str) -> None:
    """Write UTF-8 bytes without newline translation or an added newline."""
    stream = cast(TextIOWrapper, sys.stdout).buffer
    stream.write(text.encode("utf-8"))


def _environment_token(name: str, enabled: bool) -> str:
    if not enabled:
        raise click.UsageError(f"Select --token-from-env to use {name}.")
    return os.environ.get(name, "")


@cli.command()
@click.argument("project")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def repos(
    project: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repositories in a Bitbucket project."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_repositories(
            base_url,
            project,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\nslug\tname\tstate\tpublic")
    for row in rows:
        values = (row["slug"], row["name"], row["state"], row["public"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def projects(
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List visible projects."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_projects(
            base_url,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_PROJECT_COLUMNS}")
    for row in rows:
        values = (row["key"], row["name"], row["public"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.argument("repo")
@click.option("--filter", "filter_text", default=None, help="Branch text to match.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def branches(
    repo: str,
    filter_text: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repository branches in server order."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_branches(
            base_url,
            repo,
            token=token,
            filter_text=filter_text,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_branches(rows, as_json=as_json)


@cli.command()
@click.argument("repo")
@click.option("--at", default=None, help="Commit ID or ref to list commits up to.")
@click.option("--path", default=None, help="Only commits affecting this path.")
@click.option(
    "--limit",
    type=click.IntRange(1, 1000),
    default=15,
    show_default=True,
    help="Maximum commits to return (1-1000).",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def commits(
    repo: str,
    at: str | None,
    path: str | None,
    limit: int,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repository commits newest first."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_commits(
            base_url,
            repo,
            token=token,
            at=at,
            path=path,
            limit=limit,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_commits(rows, as_json=as_json)


@cli.command("file")
@click.argument("repo")
@click.argument("path")
@click.option("--at", default="master", show_default=True, help="Revision to read.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def file_command(
    repo: str,
    path: str,
    at: str,
    base_url: str,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one Bitbucket repository file exactly as stored."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        text = get_repository_file(
            base_url,
            repo,
            path,
            token=token,
            at=at,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _write_exact_text(text)


def _print_pull_request_files(rows: list[PullRequestFile], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_FILE_COLUMNS}")
    for row in rows:
        values = (row["path"], row["type"], row["node"])
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_pull_request_comments(
    rows: list[PullRequestComment], *, as_json: bool
) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_COMMENT_COLUMNS}")
    for row in rows:
        text = " ".join(row["text"].split())
        values = (row["id"], row["author"], row["path"], row["line"], text)
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_branches(rows: list[Branch], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_BRANCH_COLUMNS}")
    for row in rows:
        values = (row["name"], row["commit"], row["default"])
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_commits(rows: list[Commit], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_COMMIT_COLUMNS}")
    for row in rows:
        # Legacy text view: collapse whitespace, then cut, then escape.
        message = " ".join(row["message"].split())[:_COMMIT_MESSAGE_MAX]
        values = (row["hash"], row["date"], row["author"], message)
        click.echo("\t".join(map(_tsv_cell, values)))


def _run_pr_diff_action(
    repo: str,
    pr_id: str,
    *,
    base_url: str,
    token: str,
    as_json: bool,
    context: int,
    allow_http_loopback: bool,
) -> None:
    read = get_pull_request_diff if as_json else get_pull_request_diff_text
    result = read(
        base_url,
        repo,
        pr_id,
        token=token,
        context=context,
        allow_http_loopback=allow_http_loopback,
    )
    if isinstance(result, str):
        click.echo(result, nl=False)
    else:
        click.echo(json.dumps(result))


def _run_pr_action(
    selected: str,
    repo: str,
    pr_id: str,
    *,
    base_url: str,
    token: str,
    as_json: bool,
    page_limit: int,
    context: int,
    allow_http_loopback: bool,
) -> None:
    if selected == "show":
        result = get_pull_request(
            base_url,
            repo,
            pr_id,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        click.echo(json.dumps(result))
    elif selected == "files":
        files = list_pull_request_files(
            base_url,
            repo,
            pr_id,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        _print_pull_request_files(files, as_json=as_json)
    elif selected == "diff":
        _run_pr_diff_action(
            repo,
            pr_id,
            base_url=base_url,
            token=token,
            as_json=as_json,
            context=context,
            allow_http_loopback=allow_http_loopback,
        )
    else:
        comments = list_pull_request_comments(
            base_url,
            repo,
            pr_id,
            token=token,
            max_pages=page_limit,
            allow_http_loopback=allow_http_loopback,
        )
        _print_pull_request_comments(comments, as_json=as_json)


def _pr_arguments(
    action: str | None,
    path: str | None,
    side: str | None,
    *,
    as_json: bool,
    max_pages: int | None,
    context: int | None,
) -> tuple[str, str]:
    """Validate the selected PR action and return it with the file side."""
    selected = "show" if action is None else action
    if selected not in {"show", "files", "comments", "diff", "file"}:
        raise click.UsageError(
            'The optional third argument must be "show", "files", "comments", '
            '"diff", or "file".'
        )
    if selected != "file" and path is not None:
        raise click.UsageError('PATH is only supported with "file".')
    if selected != "file" and side is not None:
        raise click.UsageError('"--side" is only supported with "file".')
    if selected == "file" and path is None:
        raise click.UsageError('The "file" action requires PATH.')
    if selected == "file" and as_json:
        raise click.UsageError('"--json" is not supported with "file".')
    if max_pages is not None and selected != "comments":
        raise click.UsageError('"--max-pages" is only supported with "comments".')
    if context is not None and selected != "diff":
        raise click.UsageError('"--context" is only supported with "diff".')
    return selected, "new" if side is None else side


def _run_pr_file_action(
    repo: str,
    pr_id: str,
    path: str,
    *,
    base_url: str,
    token: str,
    side: str,
    allow_http_loopback: bool,
) -> None:
    text = get_pull_request_file(
        base_url,
        repo,
        pr_id,
        path,
        token=token,
        side=side,
        allow_http_loopback=allow_http_loopback,
    )
    _write_exact_text(text)


@cli.command()
@click.argument("repo")
@click.argument("pr_id")
@click.argument("action", required=False)
@click.argument("path", required=False)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print files, comments, or the raw diff as JSON.",
)
@click.option(
    "--side",
    type=click.Choice(["new", "old"]),
    default=None,
    help='PR file side ("new" or "old"; default new).',
)
@click.option(
    "--max-pages",
    type=click.IntRange(1, 1000),
    default=None,
    help="Maximum comment activity pages (1-1000; default 100).",
)
@click.option(
    "--context",
    type=click.IntRange(0, 100),
    default=None,
    help="Diff context lines (0-100; default 3).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def pr(
    repo: str,
    pr_id: str,
    action: str | None,
    path: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    side: str | None,
    max_pages: int | None,
    context: int | None,
    allow_http_loopback: bool,
) -> None:
    """Get one pull request, its changed files, comments, diff, or one file.

    The optional third argument is "show" (default raw JSON), "files",
    "comments", "diff", or "file". "--max-pages" and "--context" apply only to
    "comments" and "diff"; PATH and "--side" apply only to "file".
    """
    selected, selected_side = _pr_arguments(
        action,
        path,
        side,
        as_json=as_json,
        max_pages=max_pages,
        context=context,
    )
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        if selected == "file" and path is not None:
            _run_pr_file_action(
                repo,
                pr_id,
                path,
                base_url=base_url,
                token=token,
                side=selected_side,
                allow_http_loopback=allow_http_loopback,
            )
            return
        _run_pr_action(
            selected,
            repo,
            pr_id,
            base_url=base_url,
            token=token,
            as_json=as_json,
            page_limit=100 if max_pages is None else max_pages,
            context=3 if context is None else context,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None


@cli.command()
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option("--markdown", is_flag=True, help="Print Markdown instead of JSON.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue(
    key_or_url: str,
    base_url: str,
    token_from_env: bool,
    markdown: bool,
    allow_http_loopback: bool,
) -> None:
    """Get a Jira issue as JSON or Markdown by key or browse URL."""
    token = _environment_token("ATLAWIRE_JIRA_TOKEN", token_from_env)
    try:
        result = get_issue(
            base_url, key_or_url, token=token, allow_http_loopback=allow_http_loopback
        )
        rendered = render_issue_markdown(result) if markdown else None
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if rendered is not None:
        click.echo(rendered, nl=False)
        return
    click.echo(json.dumps(result))


@cli.command()
@click.argument("query")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--limit",
    type=click.IntRange(SEARCH_LIMIT_MIN, SEARCH_LIMIT_MAX),
    default=50,
    show_default=True,
    help=f"Maximum rows to return ({SEARCH_LIMIT_MIN}-{SEARCH_LIMIT_MAX}).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jql(
    query: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """Search Jira with JQL and print short issue rows."""
    if not query.strip():
        raise click.UsageError("Provide a non-empty JQL query.")
    token = _environment_token("ATLAWIRE_JIRA_TOKEN", token_from_env)
    try:
        rows = search_issues(
            base_url,
            query,
            token=token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_JQL_COLUMNS}")
    for row in rows:
        values = (
            row["key"],
            row["status"],
            row["type"],
            row["priority"],
            row["assignee"],
            row["updated"],
            row["summary"],
        )
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.argument("query")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--limit",
    type=click.IntRange(CQL_LIMIT_MIN, CQL_LIMIT_MAX),
    default=25,
    show_default=True,
    help=f"Maximum rows to return ({CQL_LIMIT_MIN}-{CQL_LIMIT_MAX}).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def cql(
    query: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """Search Confluence with CQL and print short content rows."""
    if not query.strip():
        raise click.UsageError("Provide a non-empty CQL query.")
    token = _environment_token("ATLAWIRE_CONFLUENCE_TOKEN", token_from_env)
    try:
        rows = search_cql(
            base_url,
            query,
            token=token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_CQL_COLUMNS}")
    for row in rows:
        values = (row["id"], row["space"], row["type"], row["title"], row["url"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--limit",
    type=click.IntRange(SPACE_LIMIT_MIN, SPACE_LIMIT_MAX),
    default=SPACE_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum spaces to return ({SPACE_LIMIT_MIN}-{SPACE_LIMIT_MAX}).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def spaces(
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List Confluence spaces and print short space rows."""
    token = _environment_token("ATLAWIRE_CONFLUENCE_TOKEN", token_from_env)
    try:
        rows = list_spaces(
            base_url,
            token=token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_SPACE_COLUMNS}")
    for row in rows:
        values = (row["key"], row["name"], row["type"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.argument("page_id_or_url")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--limit",
    type=click.IntRange(CHILD_LIMIT_MIN, CHILD_LIMIT_MAX),
    default=CHILD_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum child pages to return ({CHILD_LIMIT_MIN}-{CHILD_LIMIT_MAX}).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def children(
    page_id_or_url: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List direct child pages of a Confluence page by ID or page link."""
    token = _environment_token("ATLAWIRE_CONFLUENCE_TOKEN", token_from_env)
    try:
        rows = list_children(
            base_url,
            page_id_or_url,
            token=token,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_CHILD_COLUMNS}")
    for row in rows:
        values = (row["id"], row["title"], row["version"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.argument("page_id_or_url")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option("--markdown", is_flag=True, help="Print Markdown instead of JSON.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page(
    page_id_or_url: str,
    base_url: str,
    token_from_env: bool,
    markdown: bool,
    allow_http_loopback: bool,
) -> None:
    """Get a Confluence page as JSON or Markdown by numeric ID or page link."""
    token = _environment_token("ATLAWIRE_CONFLUENCE_TOKEN", token_from_env)
    try:
        result = get_page(
            base_url,
            page_id_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        rendered = render_page_markdown(result) if markdown else None
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if rendered is not None:
        click.echo(rendered, nl=False)
        return
    click.echo(json.dumps(result))


def main() -> None:
    """Run the AtlaWire command-line interface."""
    cli()

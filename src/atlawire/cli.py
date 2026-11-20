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
    BlameLine,
    Branch,
    ChangedFile,
    Commit,
    DirectoryEntry,
    MyPullRequest,
    PullRequest,
    PullRequestComment,
    find_repositories,
    get_commit,
    get_commit_diff,
    get_commit_diff_text,
    get_file_blame,
    get_pull_request,
    get_pull_request_diff,
    get_pull_request_diff_text,
    get_pull_request_file,
    get_repository_file,
    list_branches,
    list_commit_changes,
    list_commits,
    list_directory,
    list_my_pull_requests,
    list_projects,
    list_pull_request_comments,
    list_pull_request_commits,
    list_pull_request_files,
    list_pull_requests,
    list_repositories,
    list_repository_files,
)
from atlawire.bitbucket_search import (
    SEARCH_LIMIT_DEFAULT as BB_SEARCH_LIMIT_DEFAULT,
)
from atlawire.bitbucket_search import (
    SEARCH_LIMIT_MAX as BB_SEARCH_LIMIT_MAX,
)
from atlawire.bitbucket_search import (
    SEARCH_LIMIT_MIN as BB_SEARCH_LIMIT_MIN,
)
from atlawire.bitbucket_search import (
    SearchLine,
    SearchRow,
    search_code,
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
    list_my_issues,
    list_statuses,
    search_issues,
)

_TSV_CONTROLS = re.compile(r"[\\\x00-\x1f\x7f-\x9f\u2028\u2029]")
_TSV_ESCAPES = {"\\": r"\\", "\t": r"\t", "\r": r"\r", "\n": r"\n"}
_JQL_COLUMNS = "key\tstatus\ttype\tpriority\tassignee\tupdated\tsummary"
_MINE_COLUMNS = "key\tstatus\ttype\tpriority\tupdated\tsummary"
_CQL_COLUMNS = "id\tspace\ttype\ttitle\turl"
_SPACE_COLUMNS = "key\tname\ttype"
_CHILD_COLUMNS = "id\ttitle\tversion"
_PROJECT_COLUMNS = "key\tname\tpublic"
_FIND_REPOS_COLUMNS = "project\tslug\tname\tstate"
_FILE_COLUMNS = "path\ttype\tnode"
_DIRECTORY_COLUMNS = "path\ttype\tsize"
_COMMENT_COLUMNS = "id\tauthor\tpath\tline\ttext"
_PULL_REQUEST_COLUMNS = "id\ttitle\tstate\tauthor\tfrom\tto\tupdated"
_MY_PULL_REQUEST_COLUMNS = "repo\tid\ttitle\tstate\tauthor\treviewers_inactive\tcreated"
_BRANCH_COLUMNS = "name\tcommit\tdefault"
_COMMIT_COLUMNS = "hash\tdate\tauthor\tmessage"
_BLAME_COLUMNS = "line\tauthor\tdate\tcommit"
_COMMIT_MESSAGE_MAX = 160
_SEARCH_SNIPPET_MAX = 110
_SEARCH_UNSAFE = re.compile(
    r"[\\\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069"
    r"\ud800-\udfff]"
)


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


@cli.command("find-repos")
@click.argument("name")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--limit",
    type=click.IntRange(1, 1000),
    default=25,
    show_default=True,
    help="Maximum repositories to return (1-1000).",
)
@click.option(
    "--max-pages",
    type=click.IntRange(1, 1000),
    default=100,
    show_default=True,
    help="Total page budget across projects and repositories (1-1000).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def find_repos_command(
    name: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """Find repositories across visible projects by name or slug substring."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = find_repositories(
            base_url,
            name,
            token=token,
            limit=limit,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_FIND_REPOS_COLUMNS}")
    for row in rows:
        values = (row["project"], row["slug"], row["name"], row["state"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command("search")
@click.argument("query")
@click.option("--project", default=None, help="Limit results to one project key.")
@click.option("--repo", default=None, help="Limit results to one KEY/slug.")
@click.option(
    "--limit",
    type=click.IntRange(BB_SEARCH_LIMIT_MIN, BB_SEARCH_LIMIT_MAX),
    default=None,
    help=(
        f"Rows to return ({BB_SEARCH_LIMIT_MIN}-{BB_SEARCH_LIMIT_MAX}; "
        f"{BB_SEARCH_LIMIT_DEFAULT}, or {BB_SEARCH_LIMIT_MAX} with --all)."
    ),
)
@click.option(
    "--all",
    "every_page",
    is_flag=True,
    help="Follow result pages up to the row limit instead of one page.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of a summary."
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def search_command(
    query: str,
    project: str | None,
    repo: str | None,
    limit: int | None,
    every_page: bool,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """Search indexed Bitbucket code, optionally scoped to a project or repo.

    Without --all only the first result page is read. With --all the call
    follows pages up to the row limit or the server's terminal page.
    """
    if project is not None and repo is not None:
        raise click.UsageError("Use --project or --repo, not both.")
    if not query.strip():
        raise click.UsageError("Provide a non-empty search query.")
    row_limit = (
        BB_SEARCH_LIMIT_MAX
        if every_page and limit is None
        else (BB_SEARCH_LIMIT_DEFAULT if limit is None else limit)
    )
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = search_code(
            base_url,
            query,
            project=project,
            repo=repo,
            limit=row_limit,
            every_page=every_page,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    _print_search_results(rows, every_page=every_page)


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


@cli.command()
@click.argument("repo")
@click.argument("sha")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def commit_command(
    repo: str,
    sha: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """Get one commit as JSON by full or abbreviated hexadecimal SHA."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        result = get_commit(
            base_url,
            repo,
            sha,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("commit-changes")
@click.argument("repo")
@click.argument("sha")
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
def commit_changes_command(
    repo: str,
    sha: str,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List the files changed by one commit (SHA is 7-40 hex characters)."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_commit_changes(
            base_url,
            repo,
            sha,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_changed_files(rows, as_json=as_json)


@cli.command("commit-diff")
@click.argument("repo")
@click.argument("sha")
@click.argument("paths", nargs=-1)
@click.option(
    "--context",
    type=click.IntRange(0, 100),
    default=3,
    show_default=True,
    help="Diff context lines (0-100; default 3).",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Print raw JSON instead of review text."
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def commit_diff_command(
    repo: str,
    sha: str,
    paths: tuple[str, ...],
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    context: int,
    allow_http_loopback: bool,
) -> None:
    """Show a commit diff, whole or for explicit relative paths."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        _run_commit_diff_action(
            repo,
            sha,
            paths,
            base_url=base_url,
            token=token,
            as_json=as_json,
            context=context,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None


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


@cli.command("files")
@click.argument("repo")
@click.option("--at", default=None, help="Revision to list files at.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of plain paths."
)
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def files_command(
    repo: str,
    at: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List every file path in a Bitbucket repository recursively."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        paths = list_repository_files(
            base_url,
            repo,
            token=token,
            at=at,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_repository_files(paths, as_json=as_json)


@cli.command("ls")
@click.argument("repo")
@click.argument("path", required=False, default="")
@click.option("--at", default=None, help="Revision to list at.")
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
def ls_command(
    repo: str,
    path: str,
    at: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List the direct children of a Bitbucket repository directory."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_directory(
            base_url,
            repo,
            path,
            token=token,
            at=at,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_directory_entries(rows, as_json=as_json)


@cli.command("blame")
@click.argument("repo")
@click.argument("path")
@click.option("--at", default=None, help="Revision to blame.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def blame_command(
    repo: str,
    path: str,
    at: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """Show one line per file line with its author, date, and commit."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = get_file_blame(
            base_url,
            repo,
            path,
            token=token,
            at=at,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_blame(rows, as_json=as_json)


def _print_changed_files(rows: list[ChangedFile], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_FILE_COLUMNS}")
    for row in rows:
        values = (row["path"], row["type"], row["node"])
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_repository_files(paths: list[str], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(paths))
        return
    for path in paths:
        click.echo(_tsv_cell(path))


def _print_directory_entries(rows: list[DirectoryEntry], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_DIRECTORY_COLUMNS}")
    for row in rows:
        values = (row["path"], row["type"], row["size"])
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_blame(rows: list[BlameLine], *, as_json: bool) -> None:
    """Print the legacy TSV view without email, or every projected field as JSON."""
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_BLAME_COLUMNS}")
    for row in rows:
        values = (row["line"], row["author"], row["date"], row["commit"])
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


def _print_pull_requests(rows: list[PullRequest], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_PULL_REQUEST_COLUMNS}")
    for row in rows:
        values = (
            row["id"],
            row["title"],
            row["state"],
            row["author"],
            row["from"],
            row["to"],
            row["updated"],
        )
        click.echo("\t".join(map(_tsv_cell, values)))


def _print_my_pull_requests(rows: list[MyPullRequest], *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_MY_PULL_REQUEST_COLUMNS}")
    for row in rows:
        # The inactive-reviewer cell is already JSON, so escaping it again as
        # TSV text would corrupt the array; text columns still use _tsv_cell.
        cells = (
            _tsv_cell(row["repo"]),
            _tsv_cell(row["id"]),
            _tsv_cell(row["title"]),
            _tsv_cell(row["state"]),
            _tsv_cell(row["author"]),
            json.dumps(row["reviewers_inactive"]),
            _tsv_cell(row["created"]),
        )
        click.echo("\t".join(cells))


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


def _print_search_results(rows: list[SearchRow], *, every_page: bool) -> None:
    suffix = "" if every_page else " (first page only; use --all for every page)"
    click.echo(f"# {len(rows)} file(s){suffix}")
    for row in rows:
        where = f"{row['project']}/{row['repository']}:{row['file']}"
        count = "unknown hits" if row["hitCount"] is None else f"{row['hitCount']} hits"
        click.echo(f"{_search_cell(where)} ({count}) {_search_evidence(row)}")


def _search_evidence(row: SearchRow) -> str:
    """Label one highlighted line or one context line; never treat it as proof."""
    if row["hits"]:
        return _search_line("highlighted", row["hits"][0])
    for group in row["context"]:
        for line in group:
            return _search_line("context", line)
    return "no context"


def _search_line(label: str, line: SearchLine) -> str:
    location = "line unknown" if line["line"] is None else f"L{line['line']}"
    text = _search_cell(" ".join(line["text"].split())[:_SEARCH_SNIPPET_MAX])
    prefix = f"{label} {location}"
    return f"{prefix}: {text}" if text else prefix


def _search_cell(value: str) -> str:
    """Escape controls, bidi formatting, and backslashes for one terminal line."""
    return _SEARCH_UNSAFE.sub(lambda match: ascii(match[0])[1:-1], value)


def _run_pr_diff_action(
    repo: str,
    pr_id: str,
    *,
    base_url: str,
    token: str,
    as_json: bool,
    context: int,
    path: str | None,
    source_path: str | None,
    allow_http_loopback: bool,
) -> None:
    read = get_pull_request_diff if as_json else get_pull_request_diff_text
    result = read(
        base_url,
        repo,
        pr_id,
        token=token,
        context=context,
        path=path,
        source_path=source_path,
        allow_http_loopback=allow_http_loopback,
    )
    if isinstance(result, str):
        click.echo(result, nl=False)
    else:
        click.echo(json.dumps(result))


def _run_commit_diff_action(
    repo: str,
    sha: str,
    paths: tuple[str, ...],
    *,
    base_url: str,
    token: str,
    as_json: bool,
    context: int,
    allow_http_loopback: bool,
) -> None:
    """Fetch and print a whole or per-path commit diff after it fully succeeds."""
    selected_paths = paths or None
    if as_json:
        result = get_commit_diff(
            base_url,
            repo,
            sha,
            token=token,
            paths=selected_paths,
            context=context,
            allow_http_loopback=allow_http_loopback,
        )
        click.echo(json.dumps(result))
        return
    text = get_commit_diff_text(
        base_url,
        repo,
        sha,
        token=token,
        paths=selected_paths,
        context=context,
        allow_http_loopback=allow_http_loopback,
    )
    click.echo(text, nl=False)


def _run_pr_list_action(
    selected: str,
    repo: str,
    pr_id: str,
    *,
    base_url: str,
    token: str,
    as_json: bool,
    page_limit: int,
    allow_http_loopback: bool,
) -> None:
    """Read and print one paged pull request list (comments or commits)."""
    if selected == "commits":
        commits = list_pull_request_commits(
            base_url,
            repo,
            pr_id,
            token=token,
            max_pages=page_limit,
            allow_http_loopback=allow_http_loopback,
        )
        _print_commits(commits, as_json=as_json)
        return
    comments = list_pull_request_comments(
        base_url,
        repo,
        pr_id,
        token=token,
        max_pages=page_limit,
        allow_http_loopback=allow_http_loopback,
    )
    _print_pull_request_comments(comments, as_json=as_json)


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
    path: str | None,
    source_path: str | None,
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
        _print_changed_files(files, as_json=as_json)
    elif selected == "diff":
        _run_pr_diff_action(
            repo,
            pr_id,
            base_url=base_url,
            token=token,
            as_json=as_json,
            context=context,
            path=path,
            source_path=source_path,
            allow_http_loopback=allow_http_loopback,
        )
    else:
        _run_pr_list_action(
            selected,
            repo,
            pr_id,
            base_url=base_url,
            token=token,
            as_json=as_json,
            page_limit=page_limit,
            allow_http_loopback=allow_http_loopback,
        )


def _pr_arguments(
    action: str | None,
    path: str | None,
    side: str | None,
    source_path: str | None,
    *,
    as_json: bool,
    max_pages: int | None,
    context: int | None,
) -> tuple[str, str]:
    """Validate the selected PR action and return it with the file side."""
    selected = "show" if action is None else action
    if selected not in {"show", "files", "comments", "commits", "diff", "file"}:
        raise click.UsageError(
            'The optional third argument must be "show", "files", "comments", '
            '"commits", "diff", or "file".'
        )
    if selected not in {"file", "diff"} and path is not None:
        raise click.UsageError('PATH is only supported with "file" or "diff".')
    if selected != "file" and side is not None:
        raise click.UsageError('"--side" is only supported with "file".')
    if selected == "file" and path is None:
        raise click.UsageError('The "file" action requires PATH.')
    if selected == "file" and as_json:
        raise click.UsageError('"--json" is not supported with "file".')
    if max_pages is not None and selected not in {"comments", "commits"}:
        raise click.UsageError(
            '"--max-pages" is only supported with "comments" or "commits".'
        )
    if context is not None and selected != "diff":
        raise click.UsageError('"--context" is only supported with "diff".')
    if source_path is not None and selected != "diff":
        raise click.UsageError('"--source-path" is only supported with "diff".')
    if source_path is not None and path is None:
        raise click.UsageError('"--source-path" requires PATH.')
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
    help="Print files, comments, commits, or the raw diff as JSON.",
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
    help="Maximum comment or commit pages (1-1000; default 100).",
)
@click.option(
    "--context",
    type=click.IntRange(0, 100),
    default=None,
    help="Diff context lines (0-100; default 3).",
)
@click.option(
    "--source-path",
    default=None,
    help="Previous relative path for a renamed, copied, or moved diff file.",
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
    source_path: str | None,
    allow_http_loopback: bool,
) -> None:
    """Get one pull request, its changed files, comments, commits, diff, or one file.

    The optional third argument is "show" (default raw JSON), "files",
    "comments", "commits", "diff", or "file". "--max-pages" applies to
    "comments" and "commits"; "--context" applies only to "diff"; PATH selects
    one diff file with "diff" and is required with "file"; "--source-path"
    applies only to a "diff" with PATH.
    """
    selected, selected_side = _pr_arguments(
        action,
        path,
        side,
        source_path,
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
            path=path,
            source_path=source_path,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None


@cli.command()
@click.argument("repo")
@click.option(
    "--state",
    type=click.Choice(["OPEN", "MERGED", "DECLINED", "ALL"]),
    default="OPEN",
    show_default=True,
    help="Exact pull request state.",
)
@click.option(
    "--order",
    type=click.Choice(["NEWEST", "OLDEST"]),
    default=None,
    help="Exact pull request order (server default when omitted).",
)
@click.option(
    "--limit",
    type=click.IntRange(1, 1000),
    default=25,
    show_default=True,
    help="Maximum pull requests to return (1-1000).",
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
def prs(
    repo: str,
    state: str,
    order: str | None,
    limit: int,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List a repository's pull requests in server order."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_pull_requests(
            base_url,
            repo,
            token=token,
            state=state,
            order=order,
            limit=limit,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_pull_requests(rows, as_json=as_json)


@cli.command("my-prs")
@click.option(
    "--state",
    type=click.Choice(["OPEN", "MERGED", "DECLINED"]),
    default="OPEN",
    show_default=True,
    help="Exact pull request state.",
)
@click.option(
    "--role",
    type=click.Choice(["AUTHOR", "REVIEWER", "PARTICIPANT"]),
    default="AUTHOR",
    show_default=True,
    help="Exact role of the authenticated user.",
)
@click.option(
    "--participant-status",
    default=None,
    help="Comma-separated UNAPPROVED, NEEDS_WORK, or APPROVED (at most three).",
)
@click.option(
    "--limit",
    type=click.IntRange(1, 1000),
    default=25,
    show_default=True,
    help="Maximum pull requests to return (1-1000).",
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
def my_prs(
    state: str,
    role: str,
    participant_status: str | None,
    limit: int,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List pull requests where the authenticated user takes part."""
    token = _environment_token("ATLAWIRE_BITBUCKET_TOKEN", token_from_env)
    try:
        rows = list_my_pull_requests(
            base_url,
            token=token,
            state=state,
            role=role,
            participant_status=participant_status,
            limit=limit,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    _print_my_pull_requests(rows, as_json=as_json)


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
@click.option("--status", default=None, help="Return issues in this exact status name.")
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
def mine(
    status: str | None,
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List your Jira issues, optionally filtered to one status name."""
    token = _environment_token("ATLAWIRE_JIRA_TOKEN", token_from_env)
    try:
        rows = list_my_issues(
            base_url,
            token=token,
            status=status,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_MINE_COLUMNS}")
    for row in rows:
        values = (
            row["key"],
            row["status"],
            row["type"],
            row["priority"],
            row["updated"],
            row["summary"],
        )
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command()
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL", required=True)
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array of status names."
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def statuses(
    base_url: str,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """List the sorted unique status names visible on the Jira instance."""
    token = _environment_token("ATLAWIRE_JIRA_TOKEN", token_from_env)
    try:
        names = list_statuses(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(names))
        return
    for name in names:
        click.echo(_tsv_cell(name))


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

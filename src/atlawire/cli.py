"""Command-line entry point for AtlaWire."""

import json
import os
import re

import click

from atlawire import __version__
from atlawire.bitbucket import list_projects, list_repositories
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

"""Command-line entry point for AtlaWire."""

import base64
import hashlib
import json
import os
import re
import sys
from io import TextIOWrapper
from pathlib import Path
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
    get_branch,
    get_commit,
    get_commit_diff,
    get_commit_diff_text,
    get_file_blame,
    get_last_modified,
    get_pull_request,
    get_pull_request_diff,
    get_pull_request_diff_text,
    get_pull_request_diff_with_fallback,
    get_pull_request_file,
    get_pull_request_merge_status,
    get_repository_file,
    get_tag,
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
    list_tags,
)
from atlawire.bitbucket_attachment import (
    _DEFAULT_MAX_BYTES as ATTACHMENT_MAX_BYTES_DEFAULT,
)
from atlawire.bitbucket_attachment import get_repository_attachment
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
from atlawire.catalog import build_command_catalog
from atlawire.confluence import (
    ATTACHMENT_LIMIT_DEFAULT,
    CHILD_LIMIT_DEFAULT,
    CHILD_LIMIT_MAX,
    CHILD_LIMIT_MIN,
    COMMENT_LIMIT_DEFAULT,
    CQL_LIMIT_MAX,
    CQL_LIMIT_MIN,
    LABEL_LIMIT_DEFAULT,
    PAGE_LIMIT_MAX,
    PAGE_LIMIT_MIN,
    PAGE_START_MIN,
    SPACE_LIMIT_DEFAULT,
    SPACE_LIMIT_MAX,
    SPACE_LIMIT_MIN,
    get_page,
    get_page_attachments,
    get_page_comments,
    get_page_history,
    get_page_labels,
    get_page_version,
    get_page_web_url,
    list_children,
    list_spaces,
    search_cql,
)
from atlawire.confluence_conversion import convert_content_body
from atlawire.confluence_markdown import render_page_markdown
from atlawire.credentials import resolve_saved_credentials
from atlawire.federated import (
    LIMIT_DEFAULT as FEDERATED_LIMIT_DEFAULT,
)
from atlawire.federated import (
    LIMIT_MAX as FEDERATED_LIMIT_MAX,
)
from atlawire.federated import (
    LIMIT_MIN as FEDERATED_LIMIT_MIN,
)
from atlawire.federated import ProductTarget, federated_search
from atlawire.file_publication import (
    create_temporary_file,
    discard_temporary_file,
    publish_new_file,
)
from atlawire.http import (
    AtlaWireError,
    bearer_session,
    normalize_base_url,
    reject_credential_echo,
)
from atlawire.identity import whoami
from atlawire.issue_markdown import render_issue_markdown
from atlawire.jira import (
    COMMENT_PAGES_DEFAULT,
    COMMENT_PAGES_MAX,
    COMMENT_PAGES_MIN,
    SEARCH_LIMIT_MAX,
    SEARCH_LIMIT_MIN,
    USER_RESULTS_DEFAULT,
    USER_RESULTS_MAX,
    USER_RESULTS_MIN,
    get_current_user,
    get_issue,
    get_issue_changelog,
    get_issue_worklogs,
    list_issue_comments,
    list_issue_remote_links,
    list_issue_types,
    list_jira_projects,
    list_my_issues,
    list_priorities,
    list_resolutions,
    list_status_categories,
    list_statuses,
    list_transitions,
    search_issues,
    search_users,
)
from atlawire.jira_comments_search import find_author_comments
from atlawire.jira_metadata import (
    get_create_meta,
    get_edit_meta,
    get_transition_fields,
)
from atlawire.operations import (
    BINARY_MAX_BYTES,
    OperationShapeError,
    canonical_operations,
    describe_operation,
    list_operations,
    read_binary,
    read_operation,
)
from atlawire.pr_review import collect_pr_review, parse_pr_link, render_markdown
from atlawire.repo_grep import (
    GREP_LIMIT_DEFAULT,
    GREP_LIMIT_MAX,
    GREP_LIMIT_MIN,
    GREP_TIMEOUT_DEFAULT,
    REGEX_TIMEOUT_DEFAULT,
    grep_repository,
)
from atlawire.repo_scan import scan_repository_extensions
from atlawire.sdk import SdkRequestError, get_json, request_json

_TSV_CONTROLS = re.compile(
    r"[\\\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e"
    r"\u2028\u2029\u2066-\u2069\ud800-\udfff]"
)
_TSV_ESCAPES = {"\\": r"\\", "\t": r"\t", "\r": r"\r", "\n": r"\n"}
_JQL_COLUMNS = "key\tstatus\ttype\tpriority\tassignee\tupdated\tsummary"
_MINE_COLUMNS = "key\tstatus\ttype\tpriority\tupdated\tsummary"
_CQL_COLUMNS = "id\tspace\ttype\ttitle\turl"
_SPACE_COLUMNS = "key\tname\ttype"
_CHILD_COLUMNS = "id\ttitle\tversion"
_TRANSITION_COLUMNS = "id\tname\tto_status"
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


def _error_envelope(
    product: str | None,
    *,
    code: str,
    message: str,
    status: int | None = None,
    classification: str = "client_error",
    path: str | None = None,
    body: str | None = None,
    body_json: object = None,
    body_truncated: bool = False,
) -> dict[str, object]:
    """Build the one machine-readable error envelope."""
    return {
        "ok": False,
        "product": product,
        "error": {
            "status": status,
            "code": code,
            "classification": classification,
            "message": message,
            "path": path,
            "content_type": None,
            "body": body,
            "body_json": body_json,
            "body_truncated": body_truncated,
        },
    }


def _emit_catalog(context: click.Context) -> None:
    """Print the command catalog as one JSON document and exit.

    The catalog is derived from Click metadata plus the operation registry.
    No product URL or token is resolved, so neither the saved BBK file nor the
    environment is read and no network request is made.
    """
    group = cast(click.Group, context.command)
    catalog = build_command_catalog(group)
    catalog["operations"] = canonical_operations()
    click.echo(json.dumps(catalog))
    context.exit()


def _emit_description(context: click.Context, value: str) -> None:
    """Print one operation description, or a JSON error for an unknown ID."""
    try:
        described = describe_operation(value)
    except AtlaWireError:
        click.echo(
            json.dumps(
                _error_envelope(
                    None,
                    code="validation_error",
                    message="Unknown operation ID.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    click.echo(json.dumps(described))
    context.exit()


def _reject_conflicting_root_actions(
    context: click.Context,
    *,
    catalog: bool,
    describe_id: str | None,
    show_help: bool,
    show_version: bool,
) -> None:
    """Reject combined root-level actions as one JSON validation error.

    The four root actions are parsed before any subcommand context exists, so a
    conflict exits before credentials, files, or network access. The discovery
    actions stay exclusive of a subcommand, as before.
    """
    actions = [
        name
        for name, active in (
            ("--catalog", catalog),
            ("--describe", describe_id is not None),
            ("--help", show_help),
            ("--version", show_version),
        )
        if active
    ]
    if not actions:
        return
    discovery = catalog or describe_id is not None
    if len(actions) > 1 or (discovery and context.invoked_subcommand):
        click.echo(
            json.dumps(
                _error_envelope(
                    None,
                    code="validation_error",
                    message=(
                        "Use --catalog, --describe, --help, or --version alone, "
                        "without a subcommand."
                    ),
                )
            )
        )
        raise click.exceptions.Exit(2)


@click.group(invoke_without_command=True, add_help_option=False)
@click.option(
    "--version",
    "show_version",
    is_flag=True,
    help="Show the version and exit.",
)
@click.option(
    "--catalog",
    is_flag=True,
    help="Print every command, parameter and canonical operation as JSON.",
)
@click.option(
    "--describe",
    "describe_id",
    metavar="OPERATION_ID",
    default=None,
    help="Print one operation's full JSON description, then exit.",
)
@click.option(
    "--help",
    "show_help",
    is_flag=True,
    help="Show this message and exit.",
)
@click.pass_context
def cli(
    context: click.Context,
    show_version: bool,
    catalog: bool,
    describe_id: str | None,
    show_help: bool,
) -> None:
    """Work with self-hosted Jira, Confluence, and Bitbucket.

    Commands use the saved BBK credential file by default. Pass
    --token-from-env to read one product URL and token from the environment.

    Discover reads offline with `atlawire --catalog`, then describe one with
    `atlawire --describe <operation-id>`. Run the read with
    `atlawire read <operation-id> --params '<json-object>'`.
    """
    if not context.resilient_parsing:
        _reject_conflicting_root_actions(
            context,
            catalog=catalog,
            describe_id=describe_id,
            show_help=show_help,
            show_version=show_version,
        )
        # Every root action is handled here instead of by an eager Click
        # option, so a conflicting pair is seen before any of them runs.
        if show_help:
            click.echo(context.get_help())
            context.exit()
        if show_version:
            click.echo(f"atlawire, version {__version__}")
            context.exit()
        if describe_id is not None:
            _emit_description(context, describe_id)
        if catalog:
            _emit_catalog(context)
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


def _read_stdin_utf8() -> str:
    """Read standard input to EOF and decode it as strict UTF-8.

    The bytes are decoded without trimming, newline translation, or BOM
    removal, so empty input and leading or trailing whitespace stay exact.
    """
    raw = cast(TextIOWrapper, sys.stdin).buffer.read()
    try:
        return bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise AtlaWireError("Expected UTF-8 text on standard input.") from None


def _write_storage_text(text: str) -> None:
    """Write exact storage UTF-8, failing before any stdout bytes."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise click.ClickException(
            "The page storage text is not valid UTF-8."
        ) from None
    _write_exact_text(text)


def _page_storage_text(page: dict[str, object]) -> str:
    """Return the validated storage body or a generic shape error."""
    body = page.get("body")
    storage = body.get("storage") if isinstance(body, dict) else None
    value = storage.get("value") if isinstance(storage, dict) else None
    if not isinstance(value, str):
        raise AtlaWireError("Expected a Confluence page storage body.")
    return value


_PRODUCT_ENVIRONMENT = {
    "bitbucket": ("ATLAWIRE_BITBUCKET_URL", "ATLAWIRE_BITBUCKET_TOKEN"),
    "confluence": ("ATLAWIRE_CONFLUENCE_URL", "ATLAWIRE_CONFLUENCE_TOKEN"),
    "jira": ("ATLAWIRE_JIRA_URL", "ATLAWIRE_JIRA_TOKEN"),
}


def _product_base_url_and_token(
    product: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> tuple[str, str]:
    """Resolve one product's matched URL and token for a command invocation.

    Explicit ``--token-from-env`` keeps the environment-only contract and never
    opens the saved BBK file: the product's own URL variable supplies the
    destination when no explicit URL was passed. Otherwise the saved pair is
    required, and an explicit or environment URL is accepted only when it
    equals the saved one.
    """
    url_name, token_name = _PRODUCT_ENVIRONMENT[product]
    if token_from_env:
        resolved_url = base_url or os.environ.get(url_name)
        if not resolved_url:
            raise click.UsageError(
                f"Missing --base-url or {url_name} when using --token-from-env."
            )
        return resolved_url, os.environ.get(token_name, "")
    try:
        saved = resolve_saved_credentials(
            product,
            supplied_base_url=base_url,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    return saved.base_url, saved.token


def _federated_targets(
    token_from_env: bool,
    allow_http_loopback: bool,
) -> tuple[ProductTarget | None, ProductTarget | None, ProductTarget | None]:
    """Resolve each matched pair independently before any federated request.

    A missing or invalid pair becomes ``None`` for that product only, so the
    other products are still searched and the unusable one is reported in
    ``errors``. Environment mode reads each product's own URL variable, so a
    token is never combined with another product's destination.
    """

    def resolve(product: str) -> ProductTarget | None:
        try:
            base_url, token = _product_base_url_and_token(
                product, None, token_from_env, allow_http_loopback
            )
            validated_url = normalize_base_url(
                base_url, allow_http_loopback=allow_http_loopback
            )
            bearer_session(token).close()
        except click.ClickException, AtlaWireError:
            return None
        return ProductTarget(validated_url, token)

    return resolve("confluence"), resolve("jira"), resolve("bitbucket")


def _whoami_target(
    product: str,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> ProductTarget | None:
    """Resolve one whoami pair, dropping unusable configuration.

    A missing or invalid saved/environment pair becomes ``None`` so the
    identity check can report that product as a fixed configuration failure
    without echoing a token, URL, or parser detail. Other products continue.
    """
    url_name, _ = _PRODUCT_ENVIRONMENT[product]
    supplied = os.environ.get(url_name) if token_from_env else None
    try:
        base_url, token = _product_base_url_and_token(
            product, supplied, token_from_env, allow_http_loopback
        )
        validated_url = normalize_base_url(
            base_url, allow_http_loopback=allow_http_loopback
        )
        bearer_session(token).close()
    except click.ClickException, AtlaWireError:
        return None
    return ProductTarget(validated_url, token)


def _product_of_operation(operation_id: str) -> str | None:
    """Return the registered product, or ``None`` for an unknown ID."""
    for entry in list_operations():
        if entry.get("id") == operation_id:
            product = entry.get("product")
            if isinstance(product, str) and product in _PRODUCT_ENVIRONMENT:
                return product
            return None
    return None


def _operation_product(operation_id: str) -> str:
    """Return the static product for one exact registered operation ID."""
    product = _product_of_operation(operation_id)
    if product is None:
        raise click.ClickException("Unknown operation ID.")
    return product


def _operation_json_object(raw: str) -> dict[str, object]:
    """Parse one JSON object without duplicate keys or echoing its text."""

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        parsed = json.loads(raw, object_pairs_hook=no_duplicates)
    except ValueError, RecursionError:
        raise click.ClickException(
            "Expected a JSON object without duplicate keys."
        ) from None
    if not isinstance(parsed, dict):
        raise click.ClickException("Expected a JSON object without duplicate keys.")
    return cast(dict[str, object], parsed)


@cli.command()
@click.argument("project")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repositories in a Bitbucket project."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List visible projects."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """Find repositories across visible projects by name or slug substring."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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


@cli.command("find")
@click.argument("terms", nargs=-1, required=True)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for compatibility; JSON is always printed.",
)
@click.option(
    "--limit",
    type=click.IntRange(FEDERATED_LIMIT_MIN, FEDERATED_LIMIT_MAX),
    default=FEDERATED_LIMIT_DEFAULT,
    show_default=True,
    help=(
        "Per-term row cap for each product "
        f"({FEDERATED_LIMIT_MIN}-{FEDERATED_LIMIT_MAX})."
    ),
)
@click.option(
    "--token-from-env",
    is_flag=True,
    help="Read all three ATLAWIRE product URL/token pairs from the environment.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def find_command(
    terms: tuple[str, ...],
    as_json: bool,
    limit: int,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Search every TERM in Confluence, Jira, and Bitbucket; print merged JSON.

    TERM is plain text: double quotes, backslashes, controls, bidi controls, and
    lone surrogates are rejected before any request. Each term is searched as
    one quoted literal, and each product returns at most --limit rows per term.
    """
    confluence, jira, bitbucket = _federated_targets(
        token_from_env, allow_http_loopback
    )
    try:
        result = federated_search(
            terms,
            confluence=confluence,
            jira=jira,
            bitbucket=bitbucket,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("operations")
def operations_command() -> None:
    """Print every registered fixed read operation as JSON.

    The catalog is static: no credential is resolved and no request is made.
    """
    click.echo(json.dumps(list_operations()))


@cli.command("read-operation")
@click.argument("operation_id")
@click.option(
    "--params",
    "raw_params",
    required=True,
    help="JSON object of registered path arguments.",
)
@click.option(
    "--query",
    "raw_query",
    default=None,
    help="Optional JSON object of declared typed query fields.",
)
@click.option(
    "--base-url",
    default=None,
    help="Base URL for the operation's product (saved-file mode checks it).",
)
@click.option(
    "--token-from-env",
    is_flag=True,
    help="Read the selected product's URL/token pair from the environment.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def read_operation_command(
    operation_id: str,
    raw_params: str,
    raw_query: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Run one allowlisted fixed GET and print its raw JSON result.

    Only the exact registered ID, its registered path arguments, and its
    declared typed query fields are accepted. No URL, method, body, header, or
    arbitrary query parameter is caller selectable. Duplicate JSON keys,
    malformed or non-object JSON, and unknown IDs fail before any request
    without echoing the input. No pagination is attempted.
    """
    arguments = _operation_json_object(raw_params)
    query = _operation_json_object(raw_query) if raw_query is not None else None
    product = _operation_product(operation_id)
    resolved_url, token = _product_base_url_and_token(
        product, base_url, token_from_env, allow_http_loopback
    )
    try:
        result = read_operation(
            operation_id,
            resolved_url,
            token=token,
            arguments=arguments,
            query=query,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("read")
@click.argument("operation_id")
@click.option(
    "--params",
    "raw_params",
    required=True,
    help="JSON object of the operation's registered path arguments.",
)
@click.option(
    "--query",
    "raw_query",
    default=None,
    help="Optional JSON object of declared typed query fields.",
)
@click.option(
    "--body",
    "raw_body",
    default=None,
    help="JSON object of declared body fields for a semantic-read POST.",
)
@click.option(
    "--out",
    "destination",
    default=None,
    help="Destination file for a binary read; must not already exist.",
)
@click.option(
    "--max-bytes",
    type=click.IntRange(min=1),
    default=BINARY_MAX_BYTES,
    show_default=True,
    help="Upper bound for a binary download.",
)
@click.option("--base-url", default=None)
@click.option(
    "--token-from-env",
    is_flag=True,
    help="Read the selected product's URL/token pair from the environment.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def read_command(
    operation_id: str,
    raw_params: str,
    raw_query: str | None,
    raw_body: str | None,
    destination: str | None,
    max_bytes: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Run one described read-only operation and print a JSON envelope.

    This is the canonical agent-facing read path. The operation ID, its path
    arguments and its declared query fields come from the same registry that
    `--catalog` and `--describe` expose. Validation and configuration failures
    print one JSON error without contacting the server.
    """
    try:
        arguments = _operation_json_object(raw_params)
        query = _operation_json_object(raw_query) if raw_query is not None else None
        body = _operation_json_object(raw_body) if raw_body is not None else None
    except click.ClickException as exc:
        click.echo(
            json.dumps(
                _error_envelope(
                    _product_of_operation(operation_id),
                    code="validation_error",
                    message=exc.format_message(),
                )
            )
        )
        raise click.exceptions.Exit(2) from None

    product = _product_of_operation(operation_id)
    if product is None:
        click.echo(
            json.dumps(
                _error_envelope(
                    None,
                    code="validation_error",
                    message="Unknown operation ID.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None

    # Validate the caller's argument names against the registry before reading
    # credentials, so a typo never looks like a configuration failure.
    described = describe_operation(operation_id)
    expected = {
        str(argument["name"])
        for argument in cast(list[dict[str, object]], described["arguments"])
    }
    if set(arguments) != expected:
        names = ", ".join(sorted(expected)) or "none"
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message=f"Expected exactly these path arguments: {names}.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    allowed_query = {
        str(field["name"])
        for field in cast(list[dict[str, object]], described["query"])
    }
    if query and set(query) - allowed_query:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message="The query parameters are invalid.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    allowed_body = {
        str(field["name"]) for field in cast(list[dict[str, object]], described["body"])
    }
    if body is not None and (not allowed_body or set(body) - allowed_body):
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message="The request body is invalid.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    if described["method"] == "POST" and body is None:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message="This operation requires --body.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    response_kind = cast(dict[str, object], described["response"])["kind"]
    if response_kind != "binary" and destination is not None:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message="This operation returns JSON; --out is only for binary reads.",
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    try:
        resolved_url, token = _product_base_url_and_token(
            product, base_url, token_from_env, allow_http_loopback
        )
    except (click.ClickException, click.UsageError) as exc:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="credentials_error",
                    message=exc.format_message(),
                )
            )
        )
        raise click.exceptions.Exit(2) from None

    if response_kind == "binary":
        if not destination:
            click.echo(
                json.dumps(
                    _error_envelope(
                        product,
                        code="validation_error",
                        message="This operation writes a file; pass --out.",
                    )
                )
            )
            raise click.exceptions.Exit(2) from None
        try:
            receipt = read_binary(
                operation_id,
                resolved_url,
                token=token,
                arguments=arguments,
                destination=destination,
                max_bytes=max_bytes,
                allow_http_loopback=allow_http_loopback,
            )
        except SdkRequestError as exc:
            click.echo(json.dumps(exc.to_dict(product=product, token=token)))
            raise click.exceptions.Exit(1) from None
        except AtlaWireError as exc:
            click.echo(
                json.dumps(
                    _error_envelope(
                        product,
                        code="validation_error",
                        message=str(exc),
                    )
                )
            )
            raise click.exceptions.Exit(2) from None
        click.echo(json.dumps({"ok": True, "product": product, "data": receipt}))
        return

    try:
        result = read_operation(
            operation_id,
            resolved_url,
            token=token,
            arguments=arguments,
            query=query,
            body=body,
            allow_http_loopback=allow_http_loopback,
            use_library=True,
        )
    except SdkRequestError as exc:
        click.echo(json.dumps(exc.to_dict(product=product, token=token)))
        raise click.exceptions.Exit(1) from None
    except OperationShapeError as exc:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="invalid_response",
                    classification="invalid_response",
                    message=str(exc),
                    status=exc.status,
                )
            )
        )
        raise click.exceptions.Exit(1) from None
    except AtlaWireError as exc:
        click.echo(
            json.dumps(
                _error_envelope(
                    product,
                    code="validation_error",
                    message=str(exc),
                )
            )
        )
        raise click.exceptions.Exit(2) from None
    click.echo(json.dumps({"ok": True, "product": product, "data": result}))


@cli.command("api-get")
@click.argument("product", type=click.Choice(sorted(_PRODUCT_ENVIRONMENT)))
@click.argument("path")
@click.option(
    "--params",
    "raw_params",
    default=None,
    help="Optional JSON object of query parameters.",
)
@click.option("--base-url", default=None)
@click.option(
    "--token-from-env",
    is_flag=True,
    help="Read the selected product's URL/token pair from the environment.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def api_get_command(
    product: str,
    path: str,
    raw_params: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Read one standard non-admin JSON GET through atlassian-python-api."""
    params = _operation_json_object(raw_params) if raw_params is not None else None
    resolved_url, token = _product_base_url_and_token(
        product, base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_json(
            product,
            resolved_url,
            path,
            token=token,
            params=params,
            allow_http_loopback=allow_http_loopback,
        )
    except SdkRequestError as exc:
        click.echo(
            json.dumps(
                exc.to_dict(product=product, token=token),
                ensure_ascii=False,
            )
        )
        raise click.exceptions.Exit(1) from None
    except AtlaWireError as exc:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "product": product,
                    "error": {
                        "status": None,
                        "code": "validation_error",
                        "classification": "client_error",
                        "message": str(exc),
                        "path": path,
                        "content_type": None,
                        "body": None,
                        "body_json": None,
                    },
                },
                ensure_ascii=False,
            )
        )
        raise click.exceptions.Exit(1) from None
    click.echo(json.dumps(result))


@cli.command("api-request")
@click.argument("product", type=click.Choice(sorted(_PRODUCT_ENVIRONMENT)))
@click.argument("method", type=click.Choice(["GET", "POST"], case_sensitive=False))
@click.argument("path")
@click.option("--params", "raw_params", default=None)
@click.option("--body", "raw_body", default=None)
@click.option("--base-url", default=None)
@click.option("--token-from-env", is_flag=True)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def api_request_command(
    product: str,
    method: str,
    path: str,
    raw_params: str | None,
    raw_body: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Run one read-only GET or POST through atlassian-python-api."""
    params = _operation_json_object(raw_params) if raw_params is not None else None
    body = _operation_json_object(raw_body) if raw_body is not None else None
    resolved_url, token = _product_base_url_and_token(
        product, base_url, token_from_env, allow_http_loopback
    )
    try:
        result = request_json(
            product,
            resolved_url,
            path,
            method=method,
            token=token,
            params=params,
            body=body,
            allow_http_loopback=allow_http_loopback,
        )
    except SdkRequestError as exc:
        click.echo(
            json.dumps(
                exc.to_dict(product=product, token=token),
                ensure_ascii=False,
            )
        )
        raise click.exceptions.Exit(1) from None
    except AtlaWireError as exc:
        click.echo(
            json.dumps(
                {
                    "ok": False,
                    "product": product,
                    "error": {
                        "status": None,
                        "code": "validation_error",
                        "classification": "client_error",
                        "message": str(exc),
                        "path": path,
                        "content_type": None,
                        "body": None,
                        "body_json": None,
                    },
                },
                ensure_ascii=False,
            )
        )
        raise click.exceptions.Exit(1) from None
    click.echo(json.dumps(result))


@cli.command("whoami")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option(
    "--token-from-env",
    is_flag=True,
    help="Read all three ATLAWIRE product URL/token pairs from the environment.",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
@click.pass_context
def whoami_command(
    context: click.Context,
    as_json: bool,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Probe all three products and print one per-product JSON result.

    Confluence must return a known identity; anonymous responses fail.
    Bitbucket proves authenticated dashboard access but does not identify the
    user. Jira reads the current user. Other product failures remain visible.
    The exit status is 0 only when every product reports ok=true; a partial
    result prints the complete JSON and exits 1.
    """
    confluence = _whoami_target("confluence", token_from_env, allow_http_loopback)
    jira = _whoami_target("jira", token_from_env, allow_http_loopback)
    bitbucket = _whoami_target("bitbucket", token_from_env, allow_http_loopback)
    try:
        result = whoami(
            confluence=confluence,
            jira=jira,
            bitbucket=bitbucket,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))
    if any(check.get("ok") is not True for check in result.values()):
        context.exit(1)


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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
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
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
        if as_json:
            rendered = json.dumps(rows)
        else:
            rendered = _render_search_results(rows, every_page=every_page)
        reject_credential_echo(rendered, tokens=(token,))
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(rendered)
        return
    click.echo(rendered, nl=False)


@cli.command("grep-repo")
@click.argument("repo")
@click.argument("pattern", required=False, default=None)
@click.option(
    "--at",
    "--ref",
    "at_ref",
    default=None,
    help="Commit, branch, tag, or qualified ref; omitted uses the default branch.",
)
@click.option(
    "--glob",
    "glob_filter",
    default=None,
    help="Optional fnmatch glob selecting eligible repository paths.",
)
@click.option(
    "--path",
    "path_filter",
    default=None,
    help="Optional repository-relative path prefix filter.",
)
@click.option(
    "--limit",
    type=click.IntRange(GREP_LIMIT_MIN, GREP_LIMIT_MAX),
    default=GREP_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum matching lines ({GREP_LIMIT_MIN}-{GREP_LIMIT_MAX}).",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0, min_open=True),
    default=GREP_TIMEOUT_DEFAULT,
    show_default=True,
    help="Cooperative total time budget in seconds.",
)
@click.option(
    "--regex-timeout",
    type=click.FloatRange(min=0, min_open=True),
    default=REGEX_TIMEOUT_DEFAULT,
    show_default=True,
    help="Per-file regex helper budget in seconds.",
)
@click.option(
    "--max-pages",
    type=click.IntRange(1, 1000),
    default=100,
    show_default=True,
    help="Page budget for each listing call (1-1000).",
)
@click.option(
    "--case-sensitive",
    is_flag=True,
    help="Make the regular expression case-sensitive.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def grep_repo_command(
    repo: str,
    pattern: str | None,
    at_ref: str | None,
    glob_filter: str | None,
    path_filter: str | None,
    limit: int,
    timeout: float,
    regex_timeout: float,
    max_pages: int,
    case_sensitive: bool,
    as_json: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print a read-only regex search or path listing of one snapshot as JSON.

    Omitting PATTERN lists filtered paths without reading file contents or
    evaluating a regex. With a pattern and neither --glob nor --path only known
    text suffixes are eligible; either filter selects explicitly. The ref is
    pinned to one full commit, so every file read uses the same snapshot.
    --timeout is cooperative between requests and helper runs, not a hard
    network deadline. Each hit preview is capped at 300 characters and flags
    truncation. Any listing, file, ref, or budget failure aborts with no stdout.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = grep_repository(
            base_url,
            repo,
            pattern,
            token=token,
            at=at_ref,
            glob=glob_filter,
            path=path_filter,
            ignore_case=not case_sensitive,
            limit=limit,
            timeout_s=timeout,
            regex_timeout_s=regex_timeout,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command()
@click.argument("repo")
@click.option("--filter", "filter_text", default=None, help="Branch text to match.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repository branches in server order."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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


@cli.command("branch")
@click.argument("repo")
@click.argument("name")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def branch_command(
    repo: str,
    name: str,
    base_url: str | None,
    token_from_env: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """Print the branch with the exact display name NAME as JSON."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        row = get_branch(
            base_url,
            repo,
            name,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(row))


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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List repository commits newest first."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """Get one commit as JSON by full or abbreviated hexadecimal SHA."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List the files changed by one commit (SHA is 7-40 hex characters)."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def commit_diff_command(
    repo: str,
    sha: str,
    paths: tuple[str, ...],
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    context: int,
    allow_http_loopback: bool,
) -> None:
    """Show a commit diff, whole or for explicit relative paths."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def file_command(
    repo: str,
    path: str,
    at: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one Bitbucket repository file exactly as stored."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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


def _write_bytes(destination: str, payload: bytes) -> dict[str, object]:
    """Write bytes to a new file atomically and return a receipt; never overwrite.

    A destination created between the caller's check and publication is
    refused, not replaced, and no receipt is produced on failure.
    """
    target = Path(destination)
    if target.exists():
        raise AtlaWireError("The destination already exists.")
    temporary = create_temporary_file(target)
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
        publish_new_file(temporary, target)
    except OSError:
        raise AtlaWireError("Could not write the destination file.") from None
    finally:
        discard_temporary_file(temporary)
    return {
        "path": str(target),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


@cli.command("attachment-get")
@click.argument("repo")
@click.argument("attachment_id")
@click.option(
    "--base64",
    "as_base64",
    is_flag=True,
    help="Print standard base64 in one JSON object.",
)
@click.option(
    "--out",
    "destination",
    default=None,
    help="Write the attachment to this file instead; it must not exist.",
)
@click.option(
    "--max-bytes",
    type=click.IntRange(min=1),
    default=ATTACHMENT_MAX_BYTES_DEFAULT,
    show_default=True,
    help="Maximum response-body bytes (positive; default is 8 MiB).",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def attachment_get_command(
    repo: str,
    attachment_id: str,
    as_base64: bool,
    destination: str | None,
    max_bytes: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one repository attachment as base64 JSON, or write it to --out.

    REPO is PROJECT/slug and ATTACHMENT_ID is one path segment. This sends one
    authenticated read-only GET to the fixed configured origin and never
    follows a redirect or response link. Pass exactly one of --base64 or --out.
    --base64 prints {"base64": "..."} holding the complete body. --out writes
    the bytes to a new file and prints a {path, bytes, sha256} receipt; it
    refuses an existing destination, including one created during publication,
    and leaves no temporary file or receipt on failure. --max-bytes bounds the
    decoded body and a larger body is rejected, never truncated. The route is
    BBK-observed only: it is absent from the local Bitbucket Server 5.10
    reference, and plugin/server version support is unverified.
    """
    if as_base64 == (destination is not None):
        raise click.UsageError("Pass exactly one of --base64 or --out.")
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        payload = get_repository_attachment(
            base_url,
            repo,
            attachment_id,
            token=token,
            max_bytes=max_bytes,
            allow_http_loopback=allow_http_loopback,
        )
        if destination is None:
            document = json.dumps({"base64": base64.b64encode(payload).decode("ascii")})
            reject_credential_echo(document, tokens=(token,))
        else:
            receipt = _write_bytes(destination, payload)
            document = json.dumps(receipt)
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(document)


@cli.command("files")
@click.argument("repo")
@click.option("--at", default=None, help="Revision to list files at.")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List every file path in a Bitbucket repository recursively."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List the direct children of a Bitbucket repository directory."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """Show one line per file line with its author, date, and commit."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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


def _render_search_results(rows: list[SearchRow], *, every_page: bool) -> str:
    """Render the bounded summary before any bytes reach stdout."""
    suffix = "" if every_page else " (first page only; use --all for every page)"
    lines = [f"# {len(rows)} file(s){suffix}"]
    for row in rows:
        where = f"{row['project']}/{row['repository']}:{row['file']}"
        count = "unknown hits" if row["hitCount"] is None else f"{row['hitCount']} hits"
        lines.append(f"{_search_cell(where)} ({count}) {_search_evidence(row)}")
    return "\n".join(lines) + "\n"


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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
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
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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


@cli.command("pr-merge-status")
@click.argument("repo")
@click.argument("pr_id")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def pr_merge_status(
    repo: str,
    pr_id: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print a Bitbucket pull request's mergeability object as JSON.

    REPO is PROJECT/slug. This sends one read-only GET to the fixed merge
    status route; it never performs the merge and never follows response links.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_pull_request_merge_status(
            base_url,
            repo,
            pr_id,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("pr-diff-complete")
@click.argument("repo")
@click.argument("pr_id")
@click.option(
    "--context",
    type=click.IntRange(0, 100),
    default=3,
    show_default=True,
    help="Diff context lines (0-100).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def pr_diff_complete_command(
    repo: str,
    pr_id: str,
    context: int,
    as_json: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print a whole PR diff or an all-or-nothing file fallback as JSON.

    The first request is the fixed whole-diff GET. Only a declared truncation,
    including a nested file flag, starts the fallback: one terminal
    untruncated changes GET and then one fixed per-file diff GET per changed
    path. A capped or truncated changes page, or any later file failure, aborts
    the whole call with no stdout. This is not a snapshot: the pull request can
    change between requests, so a fallback result can mix revisions.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_pull_request_diff_with_fallback(
            base_url,
            repo,
            pr_id,
            token=token,
            context=context,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("pr-review")
@click.argument("repo_or_url")
@click.argument("pr_id", required=False, default=None)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print JSON (the default).",
)
@click.option(
    "--markdown",
    is_flag=True,
    help="Print a Markdown review instead of JSON.",
)
@click.option(
    "--no-diff",
    is_flag=True,
    help="Skip the diff request and leave line counts unknown.",
)
@click.option(
    "--context",
    type=click.IntRange(0, 100),
    default=2,
    show_default=True,
    help="Diff context lines (0-100).",
)
@click.option(
    "--jira-base-url",
    default=None,
    help="Explicit Jira URL for ticket enrichment (requires the env token flag).",
)
@click.option(
    "--jira-token-from-env",
    is_flag=True,
    help="Read the Jira token from ATLAWIRE_JIRA_TOKEN.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def pr_review_command(
    repo_or_url: str,
    pr_id: str | None,
    as_json: bool,
    markdown: bool,
    no_diff: bool,
    context: int,
    jira_base_url: str | None,
    jira_token_from_env: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print a read-only pull request review packet as JSON or Markdown.

    Accept either REPO PR_ID or one Bitbucket pull request URL. The URL supplies
    only the repository and ID, never the request destination. Jira ticket
    enrichment is optional: without explicit Jira options the saved BBK pair is
    tried, and a missing pair leaves any detected ticket explicitly unverified.
    Explicit Jira options must resolve before any request.
    """
    if as_json and markdown:
        raise click.UsageError("Use --json or --markdown, not both.")
    try:
        if pr_id is None:
            repo, requested_id = parse_pr_link(repo_or_url)
        else:
            repo, requested_id = repo_or_url, pr_id
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if jira_base_url is not None and not jira_token_from_env:
        raise click.UsageError("--jira-base-url requires --jira-token-from-env.")
    bitbucket_url, bitbucket_token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    jira_url: str | None = None
    jira_token: str | None = None
    if jira_base_url is not None or jira_token_from_env:
        url_name, _ = _PRODUCT_ENVIRONMENT["jira"]
        supplied = jira_base_url or os.environ.get(url_name)
        if not supplied:
            raise click.UsageError(
                "Missing --jira-base-url or ATLAWIRE_JIRA_URL when using "
                "--jira-token-from-env."
            )
        jira_url, jira_token = _product_base_url_and_token(
            "jira", supplied, True, allow_http_loopback
        )
    else:
        try:
            jira_url, jira_token = _product_base_url_and_token(
                "jira", None, False, allow_http_loopback
            )
        except click.ClickException:
            jira_url = None
            jira_token = None
    try:
        packet = collect_pr_review(
            bitbucket_url,
            repo,
            requested_id,
            token=bitbucket_token,
            include_diff=not no_diff,
            context=context,
            allow_http_loopback=allow_http_loopback,
            jira_base_url=jira_url,
            jira_token=jira_token,
        )
        output = render_markdown(packet) if markdown else json.dumps(packet)
        tokens = tuple(value for value in (bitbucket_token, jira_token) if value)
        reject_credential_echo(output, tokens=tokens)
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if markdown:
        click.echo(output, nl=False)
        return
    click.echo(output)


@cli.command("tags")
@click.argument("repo")
@click.option(
    "--filter",
    "filter_text",
    default=None,
    help="Optional server-side tag filter text.",
)
@click.option(
    "--order",
    "order_by",
    type=click.Choice(["ALPHABETICAL", "MODIFICATION"]),
    default=None,
    help="Exact server tag order (default: server order).",
)
@click.option(
    "--limit",
    type=click.IntRange(1, 1000),
    default=25,
    show_default=True,
    help="Maximum tags to return (1-1000).",
)
@click.option(
    "--max-pages",
    type=click.IntRange(1, 1000),
    default=100,
    show_default=True,
    help="Maximum tag pages to read (1-1000).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def tags_command(
    repo: str,
    filter_text: str | None,
    order_by: str | None,
    limit: int,
    max_pages: int,
    as_json: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """List repository tags in server order as a JSON array.

    ``--filter`` is sent as ``filterText`` and ``--order`` as ``orderBy`` on
    every page. Rows are returned unchanged, including declared, nested, and
    unknown fields. Reaching --limit means the cap was reached, not that no
    more tags exist.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_tags(
            base_url,
            repo,
            token=token,
            filter_text=filter_text,
            order_by=order_by,
            limit=limit,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("tag")
@click.argument("repo")
@click.argument("name")
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def tag_command(
    repo: str,
    name: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one repository tag as raw JSON by exact name.

    NAME is a slash-delimited tag path; every segment is validated and encoded
    before the single fixed GET.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_tag(
            base_url,
            repo,
            name,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("last-modified")
@click.argument("repo")
@click.argument("path", required=False, default=None)
@click.option(
    "--at",
    default=None,
    help="Commit ID or ref; omit to leave the at parameter out of the request.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def last_modified_command(
    repo: str,
    path: str | None,
    at: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print last-modification metadata as raw JSON for a repo or path.

    Without PATH the repository root is read. When --at is omitted, the at
    parameter is not sent; server versions may use a default branch or reject
    that request, so an explicit --at is preferred.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_last_modified(
            base_url,
            repo,
            path,
            token=token,
            at=at,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("scan-extension")
@click.option(
    "--ext",
    "extension",
    required=True,
    help="File extension to match, such as .py (leading dot optional).",
)
@click.option(
    "--project",
    default=None,
    help="Optional Bitbucket project key or ~user project to scan alone.",
)
@click.option(
    "--workers",
    type=click.IntRange(1, 8),
    default=8,
    show_default=True,
    help="Bounded parallel repository file walks (1-8).",
)
@click.option(
    "--max-pages",
    type=click.IntRange(1, 1000),
    default=100,
    show_default=True,
    help="Page budget for each listing call (1-1000).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_BITBUCKET_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def scan_extension_command(
    extension: str,
    project: str | None,
    workers: int,
    max_pages: int,
    as_json: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print repositories containing files with one extension as JSON.

    Every visible project and its repositories are enumerated first, then one
    file walk per repository reads its default branch. An optional --project
    restricts enumeration to that project and skips the visible-project
    listing. This can be expensive: at most --workers walks run concurrently,
    and --max-pages bounds each listing call. Any project, repository,
    file-page, budget, transport, or validation failure aborts the whole scan
    with no rows and no stdout.
    """
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = scan_repository_extensions(
            base_url,
            extension,
            token=token,
            workers=workers,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
            project=project,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List a repository's pull requests in server order."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_BITBUCKET_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """List pull requests where the authenticated user takes part."""
    base_url, token = _product_base_url_and_token(
        "bitbucket", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option("--markdown", is_flag=True, help="Print Markdown instead of JSON.")
@click.option(
    "--wiki",
    is_flag=True,
    help="Render Jira wiki markup as Markdown (implies --markdown).",
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    markdown: bool,
    wiki: bool,
    allow_http_loopback: bool,
) -> None:
    """Get a Jira issue as JSON or Markdown by key or browse URL."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_issue(
            base_url, key_or_url, token=token, allow_http_loopback=allow_http_loopback
        )
        rendered = (
            render_issue_markdown(result, use_wiki=wiki) if markdown or wiki else None
        )
        if rendered is not None:
            reject_credential_echo(rendered, tokens=(token,))
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if rendered is not None:
        click.echo(rendered, nl=False)
        return
    click.echo(json.dumps(result))


@cli.command("issue-comments")
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--max-pages",
    type=click.IntRange(COMMENT_PAGES_MIN, COMMENT_PAGES_MAX),
    default=COMMENT_PAGES_DEFAULT,
    show_default=True,
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue_comments(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    max_pages: int,
    allow_http_loopback: bool,
) -> None:
    """Print the full comment thread of a Jira issue as JSON."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_issue_comments(
            base_url,
            key_or_url,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("issue-remote-links")
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue_remote_links(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print every remote link of a Jira issue as JSON.

    A pasted browse URL supplies only the issue key; the request still goes to
    the configured instance. Returned URLs are data and are never fetched.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_issue_remote_links(
            base_url,
            key_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("issue-worklogs")
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue_worklogs(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the server's current worklog page as raw JSON.

    ``startAt``, ``maxResults``, ``total``, and every row are preserved. This
    is one server page; it may be incomplete and never claims exhaustion.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_issue_worklogs(
            base_url,
            key_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("issue-changelog")
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def issue_changelog(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the server's current changelog page as raw JSON.

    The changelog document keeps ``startAt``, ``maxResults``, ``total``, every
    history, and unknown fields. This is one server page; it may be incomplete
    and never claims exhaustion.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_issue_changelog(
            base_url,
            key_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command()
@click.argument("query")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """Search Jira with JQL and print short issue rows."""
    if not query.strip():
        raise click.UsageError("Provide a non-empty JQL query.")
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List your Jira issues, optionally filtered to one status name."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array of status names."
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def statuses(
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """List the sorted unique status names visible on the Jira instance."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
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
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--json", "as_json", is_flag=True, help="Print a JSON array instead of TSV."
)
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def transitions(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    allow_http_loopback: bool,
) -> None:
    """List the workflow transitions available for a Jira issue."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_transitions(
            base_url,
            key_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(rows))
        return
    click.echo(f"# {len(rows)} row(s)\n{_TRANSITION_COLUMNS}")
    for row in rows:
        values = (row["id"], row["name"], row["to_status"])
        click.echo("\t".join(map(_tsv_cell, values)))


@cli.command("jira-edit-meta")
@click.argument("key_or_url")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_edit_meta(
    key_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the edit-screen field metadata of one issue as JSON.

    This is a read-only metadata GET; it does not edit the issue.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_edit_meta(
            base_url,
            key_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("jira-create-meta")
@click.option(
    "--project",
    default=None,
    help="Optional exact uppercase Jira project key.",
)
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_create_meta(
    project: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print create-screen field metadata as JSON.

    This is a read-only metadata GET; it does not create an issue. Jira 8.22
    marks the legacy createmeta endpoint deprecated but still available.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_create_meta(
            base_url,
            token=token,
            project=project,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("jira-transition-fields")
@click.argument("key_or_url")
@click.option(
    "--transition-id",
    default=None,
    help="Optional numeric Jira transition ID.",
)
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_transition_fields(
    key_or_url: str,
    transition_id: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print offered transitions and their screen fields as JSON.

    This is a read-only metadata GET; it does not execute a transition.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_transition_fields(
            base_url,
            key_or_url,
            token=token,
            transition_id=transition_id,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("jira-me")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_me(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the authenticated Jira user as JSON."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        user = get_current_user(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(user))


@cli.command("jira-priorities")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_priorities(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print every Jira priority as JSON, unchanged."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_priorities(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-resolutions")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_resolutions(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print every Jira resolution as JSON, unchanged."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_resolutions(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-issue-types")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_issue_types(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print every visible Jira issue type as JSON, unchanged."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_issue_types(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-status-categories")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_status_categories(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print every visible Jira status category as JSON, unchanged."""
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_status_categories(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-projects")
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_projects(
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the visible Jira project array as JSON, unchanged.

    The response carries no pagination metadata, so a short array is not proof
    that no further visible project exists.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = list_jira_projects(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-users")
@click.argument("query")
@click.option(
    "--start-at",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Zero-based index of the first user in this page.",
)
@click.option(
    "--limit",
    "max_results",
    type=click.IntRange(USER_RESULTS_MIN, USER_RESULTS_MAX),
    default=USER_RESULTS_DEFAULT,
    show_default=True,
    help=(f"Maximum users in this page ({USER_RESULTS_MIN}-{USER_RESULTS_MAX})."),
)
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_users(
    query: str,
    start_at: int,
    max_results: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one page of Jira users matching QUERY as JSON.

    The server returns a bare array. A short or full page does not prove that no
    further matching users exist, so this command never claims exhaustion.
    """
    if not query.strip():
        raise click.UsageError("Provide a non-empty user search query.")
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = search_users(
            base_url,
            query,
            token=token,
            start_at=start_at,
            max_results=max_results,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command("jira-author-comments")
@click.argument("user", required=False, default=None)
@click.option(
    "--days",
    type=click.IntRange(min=1),
    default=90,
    show_default=True,
    help="Issue-update window in days (positive integer).",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="Maximum newest matching comments to return.",
)
@click.option(
    "--project",
    default=None,
    help="Optional uppercase Jira project key.",
)
@click.option(
    "--grep",
    "grep_pattern",
    default=None,
    help="Optional case-insensitive regex over the full raw comment body.",
)
@click.option(
    "--max-issues",
    type=click.IntRange(min=1),
    default=20000,
    show_default=True,
    help="Maximum matching issues the complete scan may read.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Accepted for symmetry; JSON is always printed.",
)
@click.option("--base-url", envvar="ATLAWIRE_JIRA_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_JIRA_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def jira_author_comments(
    user: str | None,
    days: int,
    limit: int,
    project: str | None,
    grep_pattern: str | None,
    max_issues: int,
    as_json: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the newest comments by one exact Jira author as JSON.

    USER is optional; omitting it uses the authenticated Jira user. A non-exact
    USER is resolved through Jira user search, whose bare array has no
    completion marker; candidate scanning stops at the first empty page. A
    singleton non-exact match is a heuristic and does not prove uniqueness; pass
    the exact login for unambiguous use. --days bounds the issue-update window,
    not comment creation. The complete matching issue set must fit --max-issues,
    and --limit only caps returned rows after that scan. User lookup, search
    pages, and comment threads are separate requests, so the result is not a
    consistent snapshot. --grep is an optional case-insensitive regex over each
    full raw comment body, run in a bounded killable helper; an invalid pattern
    or helper failure aborts the scan.
    """
    base_url, token = _product_base_url_and_token(
        "jira", base_url, token_from_env, allow_http_loopback
    )
    try:
        rows = find_author_comments(
            base_url,
            user,
            token=token,
            days=days,
            limit=limit,
            project=project,
            grep=grep_pattern,
            max_issues=max_issues,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(rows))


@cli.command()
@click.argument("query")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """Search Confluence with CQL and print short content rows."""
    if not query.strip():
        raise click.UsageError("Provide a non-empty CQL query.")
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List Confluence spaces and print short space rows."""
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
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
    base_url: str | None,
    token_from_env: bool,
    as_json: bool,
    limit: int,
    allow_http_loopback: bool,
) -> None:
    """List direct child pages of a Confluence page by ID or page link."""
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
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
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--storage",
    "--html",
    "storage",
    is_flag=True,
    help="Print raw Confluence storage XHTML instead of JSON.",
)
@click.option("--markdown", is_flag=True, help="Print Markdown instead of JSON.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page(
    page_id_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    storage: bool,
    markdown: bool,
    allow_http_loopback: bool,
) -> None:
    """Get a Confluence page as JSON, Markdown, or raw storage XHTML."""
    if markdown and storage:
        raise click.UsageError("Use --markdown or --storage/--html, not both.")
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    storage_text: str | None = None
    try:
        result = get_page(
            base_url,
            page_id_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        if storage:
            storage_text = _page_storage_text(result)
        rendered = render_page_markdown(result) if markdown else None
        if rendered is not None:
            reject_credential_echo(rendered, tokens=(token,))
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    if storage_text is not None:
        _write_storage_text(storage_text)
        return
    if rendered is not None:
        click.echo(rendered, nl=False)
        return
    click.echo(json.dumps(result))


@cli.command("convert-body")
@click.option(
    "--from-representation",
    "representation",
    required=True,
    help="Source representation: storage or editor.",
)
@click.option(
    "--to",
    "target",
    required=True,
    help=(
        "Target representation: view, export_view, styled_view, or editor "
        "(storage is the only target for an editor source)."
    ),
)
@click.option(
    "--expand",
    default=None,
    help="Optional expand query value; an empty string is sent unchanged.",
)
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def convert_body_command(
    representation: str,
    target: str,
    expand: str | None,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Convert one content body read from stdin and print the raw JSON object.

    The source and target must form one of the five documented Confluence 6.6
    pairs: storage to view, export_view, styled_view, or editor; editor to
    storage. All stdin bytes are read to EOF and must be UTF-8. They are sent
    exactly, including empty input, leading or trailing spaces, newlines, and
    non-ASCII text, with no trimming. This is one POST to the fixed conversion
    route because that API defines the conversion as POST; no URL, method,
    header, body key, or query key is caller selectable. --expand is sent as the
    single expand query parameter, including an empty value.

    The complete response object is printed unchanged as one JSON line after
    adapter validation; any adapter failure prints a generic Click error and no
    stdout. The command adds no second scan of its serialized output, so an
    ordinary JSON escape such as ``\\u1234`` is printed normally. The adapter
    still refuses caller ``value`` or ``expand`` that literally contains the
    token, and a decoded response that echoes the token is still rejected before
    output. No response link or redirect is followed. Rendering can run
    server-side macros and plugins, so their side effects are not guaranteed to
    be absent. The exact route, target-version support, and live behavior are
    unverified. This command imposes no input-size cap; only the response is
    bounded by the shared 8 MiB JSON limit.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        value = _read_stdin_utf8()
        result = convert_content_body(
            base_url,
            value,
            representation=representation,
            to=target,
            token=token,
            expand=expand,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-attachments")
@click.argument("page_id_or_url")
@click.option(
    "--start",
    type=click.IntRange(min=PAGE_START_MIN),
    default=PAGE_START_MIN,
    show_default=True,
    help="Zero-based index of the first attachment in this page.",
)
@click.option(
    "--limit",
    type=click.IntRange(PAGE_LIMIT_MIN, PAGE_LIMIT_MAX),
    default=ATTACHMENT_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum attachments in this page ({PAGE_LIMIT_MIN}-{PAGE_LIMIT_MAX}).",
)
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_attachments(
    page_id_or_url: str,
    start: int,
    limit: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one page of Confluence attachment metadata as raw JSON.

    The response object is returned unchanged, including metadata, pagination
    fields, and links. A continuation link is data and is never followed.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_page_attachments(
            base_url,
            page_id_or_url,
            token=token,
            start=start,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-comments")
@click.argument("page_id_or_url")
@click.option(
    "--start",
    type=click.IntRange(min=PAGE_START_MIN),
    default=PAGE_START_MIN,
    show_default=True,
    help="Zero-based index of the first comment in this page.",
)
@click.option(
    "--limit",
    type=click.IntRange(PAGE_LIMIT_MIN, PAGE_LIMIT_MAX),
    default=COMMENT_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum comments in this page ({PAGE_LIMIT_MIN}-{PAGE_LIMIT_MAX}).",
)
@click.option(
    "--root-only",
    is_flag=True,
    help="Request root comments only; omit depth=all.",
)
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_comments(
    page_id_or_url: str,
    start: int,
    limit: int,
    root_only: bool,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one page of Confluence page comments as raw JSON.

    By default the request includes replies (``depth=all``) and
    ``expand=body.storage``. ``--root-only`` omits ``depth`` so the server's
    root-only default applies. Both the content-type-keyed map and a flat paged
    object are returned unchanged. A continuation link is data and is never
    followed, so one page may still be incomplete.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_page_comments(
            base_url,
            page_id_or_url,
            token=token,
            start=start,
            limit=limit,
            include_replies=not root_only,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-labels")
@click.argument("page_id_or_url")
@click.option(
    "--start",
    type=click.IntRange(min=PAGE_START_MIN),
    default=PAGE_START_MIN,
    show_default=True,
    help="Zero-based index of the first label in this page.",
)
@click.option(
    "--limit",
    type=click.IntRange(PAGE_LIMIT_MIN, PAGE_LIMIT_MAX),
    default=LABEL_LIMIT_DEFAULT,
    show_default=True,
    help=f"Maximum labels in this page ({PAGE_LIMIT_MIN}-{PAGE_LIMIT_MAX}).",
)
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_labels(
    page_id_or_url: str,
    start: int,
    limit: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one page of Confluence page labels as raw JSON.

    No response schema beyond a JSON object is assumed. A continuation link is
    data and is never followed.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_page_labels(
            base_url,
            page_id_or_url,
            token=token,
            start=start,
            limit=limit,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-history")
@click.argument("page_id_or_url")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_history(
    page_id_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print the raw history object for a Confluence page as JSON.

    This is not a complete version list: the history representation does not
    document every version. Links are data and are never followed.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_page_history(
            base_url,
            page_id_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-version")
@click.argument("page_id_or_url")
@click.argument("version", type=click.IntRange(min=1))
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_version(
    page_id_or_url: str,
    version: int,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one explicit historical Confluence page version as raw JSON.

    VERSION must be a positive integer. The returned page id and version number
    are validated. Historical status and version compatibility are not
    live-verified; a server may reject this combination.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        result = get_page_version(
            base_url,
            page_id_or_url,
            version,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result))


@cli.command("page-url")
@click.argument("page_id_or_url")
@click.option("--base-url", envvar="ATLAWIRE_CONFLUENCE_URL")
@click.option("--token-from-env", is_flag=True, help="Read ATLAWIRE_CONFLUENCE_TOKEN.")
@click.option(
    "--allow-http-loopback", is_flag=True, help="Allow local HTTP for tests only."
)
def page_url(
    page_id_or_url: str,
    base_url: str | None,
    token_from_env: bool,
    allow_http_loopback: bool,
) -> None:
    """Print one browser URL for a Confluence page.

    The URL uses the configured base URL and context path. A safe
    context-relative ``_links.webui`` path is preferred; a missing or unsafe
    link falls back to the deterministic page-id URL. Links are never followed.
    """
    base_url, token = _product_base_url_and_token(
        "confluence", base_url, token_from_env, allow_http_loopback
    )
    try:
        url = get_page_web_url(
            base_url,
            page_id_or_url,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        reject_credential_echo(url, tokens=(token,))
    except AtlaWireError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(url)


# BBK exposed a one-shot `selftest` for all three products. AtlaWire already
# reports per-product identity and failures through `whoami`, so expose the
# same probe under that name instead of duplicating it.
_WHOAMI = cli.commands["whoami"]
cli.add_command(
    click.Command(
        "selftest",
        callback=_WHOAMI.callback,
        params=_WHOAMI.params,
        help="Check authentication for all three products (same probe as whoami).",
    )
)


def main() -> None:
    """Run the AtlaWire command-line interface."""
    cli()

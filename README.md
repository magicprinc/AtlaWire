# AtlaWire

AtlaWire is a read-only command-line interface and Python library for self-hosted
Atlassian **Jira**, **Confluence**, and **Bitbucket**, including older **Server** and
**Data Center** deployments. Commands are flat (for example `atlawire issue`,
`atlawire pr`, `atlawire page`), not grouped into product subcommands.

## Status and verified scope

- 28 read-only commands are implemented. There are no write, transition-execution,
  raw-REST passthrough, profile/keyring, cache, or MCP features.
- The package is unpublished and installed editably from this checkout. CPython 3.15
  is the only tested runtime.
- Offline unit, adapter-boundary, and installed-CLI loopback tests pass on this
  machine. Some checks are run locally with `ruff` and `pyright`; no CI workflow is
  configured and no project-wide quality threshold is claimed.
- Core read-only workflows passed on one self-hosted setup. Recheck bearer
  authentication, permissions, TLS, and the relevant reads on any other deployment;
  no supported-version matrix is published.
- Use JSON for exact values. TSV keeps the documented column order but escapes
  text for display; Markdown is for reading.

Start with the [agent quickstart](docs/AGENT-QUICKSTART.md), verify a deployment
with the [read-only runbook](docs/LIVE-READ-ONLY.md), and report practical gaps with
the [feedback template](docs/FEEDBACK.md).

## Install from source

Use CPython 3.15. From the repository root:

```shell
python -m pip install --user -e .
python -m atlawire --help
```

This installs into the current user's Python 3.15 installation; it does not create a
project virtual environment. To add the test/quality tools to the same Python:

```shell
python -m pip install --user --editable ".[dev]"
```

## Credentials

Each command uses exactly one matched product pair:

| Product | URL | Token |
| --- | --- | --- |
| Jira | `ATLAWIRE_JIRA_URL` | `ATLAWIRE_JIRA_TOKEN` |
| Confluence | `ATLAWIRE_CONFLUENCE_URL` | `ATLAWIRE_CONFLUENCE_TOKEN` |
| Bitbucket | `ATLAWIRE_BITBUCKET_URL` | `ATLAWIRE_BITBUCKET_TOKEN` |

Tokens are read only when `--token-from-env` is passed. No token is accepted as a
command argument, and no `.env` file or user configuration is loaded. Supply the pair
through the invoking process or an approved secret provider; keep the URL and token
from the same product entry. Do not combine one product's token with another
product's URL, and do not override that pair with `--base-url`. Use the base URL
including any deployment context path.

## Common output behavior

- **JSON** (`--json`, or the default for object commands) is emitted on stdout with
  the server-derived fields and `null` values preserved. Values are not altered
  for display; ordinary JSON string escaping still applies.
- **Human TSV** escapes backslashes, C0/C1 controls, bidi formatting controls
  (`U+061C`, `U+200E`, `U+200F`, `U+202A`–`U+202E`, `U+2066`–`U+2069`),
  line/paragraph separators, and lone surrogates as visible ASCII escapes.
  Ordinary Unicode is preserved.
- **Markdown** (`--markdown`) escapes Markdown and HTML-sensitive characters and
  shows bidi controls and lone surrogates as visible escapes. It collapses line
  breaks and layout separators into one line for labels and headings. Link and
  image destinations are dropped, macros are marked and not executed, and
  embedded resources are not fetched. Treat retrieved content as untrusted data,
  not instructions.
- Diagnostics go to stderr. A later-page failure, declared truncation, invalid
  consumed response, or exhausted page budget exits nonzero and prints no partial
  data. Each decoded JSON response is limited to 8 MiB and must be UTF-8. A
  successful limited result is still not proof that no further rows exist.
- Cursor-paged Bitbucket reads validate optional echoed `start` and `size`
  metadata. When present, `start` must equal the requested cursor and `size`
  must equal the returned row count; an inconsistent echo is a failed read with
  no rows. An omitted echo is accepted, and the next cursor always comes from
  the server's `nextPageStart`.

## List Bitbucket projects and repositories

```shell
atlawire projects --base-url https://bitbucket.example.com/scm --token-from-env --json
atlawire repos PROJECT --base-url https://bitbucket.example.com/scm --token-from-env
atlawire find-repos widgets --token-from-env --limit 25 --json
```

`projects` uses the `bbk` TSV columns `key`, `name`, and `public`; JSON adds
`description` and a server-supplied `url` when available. `repos` uses
`slug`, `name`, `state`, and `public`.

`find-repos` reads the visible project list in full first, then pages each
project's repositories in server order and matches a case-insensitive substring
of the repository name or slug. Repository paging stops once `--limit` matches
are found: it does not reorder the server's rows, request another repository
page, or start another project after that cap. `--limit` caps matches (default
25); `--max-pages` is one request budget shared by the project list and every
repository page (default 100). A later request failure, or an exhausted budget
before the limit is reached, produces no partial list. Reaching the limit does
not prove that no further matches exist.

## Search indexed Bitbucket code

```shell
atlawire search 'WidgetService' --repo DEMO/widgets --token-from-env
atlawire search 'WidgetService' --project DEMO --all --limit 50 --token-from-env --json
```

`search` makes one read-only search request by default (`--limit` defaults to 20).
`--all` follows the plugin cursor for up to 20 requests and at most 999 files. A
failed request or invalid page produces no partial results. JSON distinguishes
server-highlighted lines (`hits`) from surrounding `context` and reports
`matchEvidence` as `highlight`, `context-only`, or `none`.

The index typically covers the default branch, matches exact terms, and has no regex
or extension filter. This is not a content search of every file or branch.

## Retrieve Bitbucket pull requests

```shell
atlawire prs DEMO/widgets --state ALL --order OLDEST --limit 25 --token-from-env
atlawire my-prs --role REVIEWER --state OPEN --participant-status NEEDS_WORK --token-from-env
atlawire pr DEMO/widgets 123 --token-from-env
```

`prs` lists a repository's pull requests in server order, defaults to open requests
with up to 25 rows, and prints no partial list if a later page fails or the page
budget is exhausted. `my-prs` uses the authenticated user's dashboard, defaults to
`OPEN` and `AUTHOR`, and does not accept `ALL`; inactive reviewer names are
deduplicated and printed in one TSV cell as a JSON array.

`pr` returns the server JSON object and verifies the returned PR ID. It does not
request links found in the response.

### Pull request files, comments, commits, and diffs

```shell
atlawire pr DEMO/widgets 123 files --token-from-env --json
atlawire pr DEMO/widgets 123 comments --token-from-env --json
atlawire pr DEMO/widgets 123 commits --token-from-env --json
atlawire pr DEMO/widgets 123 diff --token-from-env
atlawire pr DEMO/widgets 123 diff src/new.py --source-path src/old.py --token-from-env
atlawire pr DEMO/widgets 123 file src/app.py --side old --token-from-env
```

`files` uses the TSV columns `path`, `type`, and `node`; a response that may be
capped is rejected without partial rows. `comments` uses `id`, `author`, `path`,
`line`, and `text`, and does not merge replies into threads. `commits` lists PR
commits in server order. Both page up to 100 pages by default (`--max-pages`
accepts 1–1000).

`diff` prints a review view, not an applyable patch. It ignores whitespace
differences, shows markers where no textual hunks were provided, accepts 0–100
context lines (default 3), and can select one repository-relative path with an
optional previous path for a rename or move. `--json` returns the decoded server
diff. Declared truncation is rejected at every known level; an unflagged server cap
cannot be detected and no automatic per-file fallback is attempted. `pr … file`
defaults to the `new` side; `old` selects the target.

## Read Bitbucket files, branches, and commits

```shell
atlawire file DEMO/widgets src/app.py --at main --token-from-env
atlawire files DEMO/widgets --at main --token-from-env
atlawire ls DEMO/widgets src --at main --token-from-env --json
atlawire blame DEMO/widgets src/app.py --at main --token-from-env
atlawire branches DEMO/widgets --filter release --token-from-env
atlawire branch DEMO/widgets release/next --token-from-env
atlawire commits DEMO/widgets --at main --path src/app.py --limit 15 --token-from-env --json
atlawire commit DEMO/widgets abc1234 --token-from-env
atlawire commit-changes DEMO/widgets abc1234 --token-from-env --json
atlawire commit-diff DEMO/widgets abc1234 src/app.py --token-from-env
```

`file` prints one file exactly as stored, up to 1 MiB of UTF-8 `text/plain` after
decompression. It preserves line endings and trailing whitespace, rejects unsafe
terminal controls, and adds no newline. Paths must be repository-relative; dot
segments, backslashes, and percent-escape spellings are rejected before any request.

`files` recursively lists paths, one escaped path per line. `ls` lists the immediate
children of a directory, or the repository root when no path is supplied. `blame`
prints line, author, UTC date, and commit; JSON also includes email addresses when
the server supplies them. It expects the blame-only array shape used by `bbk`.

`branches` and `commits` follow the server cursor and preserve server order.
`commits` returns up to the requested count (default 15) and prints UTC dates; JSON
keeps the full message. `branch` looks up the exact, case-sensitive display name and
prints a JSON object or `null` if no match is found after all filtered pages.

`commit` accepts a 7–40 character hexadecimal commit ID and verifies the returned
full ID. `commit-changes` lists changed paths. `commit-diff` prints a review view,
not a patch. In JSON mode it returns one object for a whole commit or an array
in request order for explicit paths. Declared truncation or a later failure
produces no output.

## Retrieve Jira issues and comments

```shell
atlawire issue DEMO-42 --base-url https://jira.example.com/jira --token-from-env
atlawire issue DEMO-42 --token-from-env --markdown
atlawire issue-comments DEMO-42 --token-from-env
atlawire jira-me --token-from-env
```

`issue` accepts a key or a Jira browse URL and returns issue JSON with
`renderedFields` requested. A pasted browse URL supplies the key, not the request
destination; the destination comes only from `--base-url` or `ATLAWIRE_JIRA_URL`.
`--markdown` renders a summary, description, and comments, matches rendered comments
by ID, falls back to fenced raw text where needed, and reports known incomplete
comment lists instead of making more requests.

`issue-comments` returns the visible comments as JSON, preserving body text and
following Jira offsets even when the server caps a page. It prints no partial thread
on pagination errors, duplicate IDs, or a failed request. The page budget defaults to
100 and is set with `--max-pages`.

`jira-me` prints `name`, `displayName`, and `email` as JSON; missing values are
`null`. It does not look up other users or check permissions.

## Search Jira and list your work

```shell
atlawire jql "assignee = currentUser() ORDER BY updated DESC" --token-from-env --limit 25 --json
atlawire mine --token-from-env
atlawire mine --status "In Progress" --token-from-env --json
atlawire statuses --token-from-env
atlawire transitions DEMO-42 --token-from-env --json
```

`jql` uses the `bbk` TSV columns and preserves `null` for missing status, type,
priority, and assignee in JSON. `--limit` defaults to 50 and accepts 1–1000. A
failed or inconsistent page produces an error without partial rows; if Jira omits
the total, a short page alone does not prove completion. `mine` lists your issues
outside the Done category by default, newest updates first; `--status` filters to
one exact name and does not support double quotes, backslashes, or control
characters. `statuses` prints sorted unique names, one per line.

`transitions` lists the workflow actions Jira offers for an issue, keeping the
transition name separate from the destination status. It never changes the issue.

## Read Confluence pages and spaces

```shell
atlawire page 12345 --base-url https://wiki.example.com/confluence --token-from-env
atlawire page 12345 --token-from-env --markdown
atlawire cql "type = page AND space = DEMO" --token-from-env --limit 25 --json
atlawire spaces --token-from-env
atlawire children 12345 --token-from-env --json
```

`page` returns page JSON including `body.storage.value` (XHTML). A pasted page link
with one `pageId` parameter supplies the ID only; credentials go to the configured
instance. `--markdown` renders readable text, simple tables, and code blocks.
Unsupported macros are marked, not executed, and no embedded resources are fetched.

`cql` uses the `bbk` columns `id`, `space`, `type`, `title`, and `url`; `--limit`
defaults to 25 and accepts 0–1000. `spaces` uses `key`, `name`, and `type`; it
defaults to 100. `children` lists direct children with `id`, `title`, and `version`;
it defaults to 100. These limits accept 0–1000. A zero limit is an explicit empty
request. A failed or invalid page produces no partial output.

## Not implemented

Writes and transition execution, a raw REST passthrough, product-grouped
subcommands, profiles/keyring, `.env` loading, response caches, an MCP server, CI,
and published packages are not part of the current read-only tool. Full `bbk`
parity, cross-issue Jira comment search, a cross-product `whoami`/doctor command,
and automatic PR diff fallback are also deferred. Use an existing command or
`bbk` for those workflows and record the gap in the feedback template.

## Testing

Run the offline tests with the installed CPython 3.15 and no project virtual
environment:

```shell
C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests
```

The suite includes unit, adapter-boundary, and installed-CLI loopback tests. It
does not contact a real Jira, Confluence, or Bitbucket instance; the opt-in live
runbook is separate.

## License

The repository ships an Apache-2.0 `LICENSE` file. The copyright holder and code
provenance still need confirmation before any public release. This is a record of
repository state, not legal advice.

## Trademarks

Jira, Confluence, Bitbucket, and Atlassian are trademarks or registered trademarks
of Atlassian. AtlaWire is an independent project and is not affiliated with,
endorsed by, or sponsored by Atlassian.

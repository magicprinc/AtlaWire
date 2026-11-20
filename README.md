# AtlaWire

AtlaWire is a command-line interface and Python library under development for working with self-hosted
Atlassian **Jira**, **Confluence**, and **Bitbucket**, including older **Server** and
**Data Center** deployments that many agent integrations do not target. Its first supported
product scope is deliberately these three products; the design should make independently
maintained adapters for other products possible without promising them in the initial release.

> **Status: early implementation.** The CLI lists Bitbucket projects and repositories and
> gets PR details. It also retrieves and searches Jira issues, reads Confluence pages, runs
> CQL searches, and lists spaces and direct child pages. These workflows are tested offline,
> not yet verified on live instances.
> See [TODO.md](TODO.md) for the next steps.

## Install from source

Use CPython 3.15. From the repository root:

```shell
python -m pip install --user -e .
python -m atlawire --help
```

This installs into the current user's Python 3.15 installation; it does not create a project
virtual environment. To install the package and its test/quality tools into the same Python:

```shell
python -m pip install --user --editable ".[dev]"
```

The package is not published yet.

## List Bitbucket projects

```shell
atlawire projects --base-url https://bitbucket.example.com/scm --token-from-env --json
```

Use the same Bitbucket settings as for `repos`. The default TSV columns match `bbk projects`:
`key`, `name`, and `public`. JSON adds `description` and the `url` supplied by the server, when
available. AtlaWire does not request that URL. If paging fails or `--max-pages` is reached
before the last page, no partial list is printed. The page limit defaults to 100.

## List Bitbucket repositories

With `ATLAWIRE_BITBUCKET_TOKEN` supplied by your secret provider, run:

```shell
atlawire repos PROJECT --base-url https://bitbucket.example.com/scm --token-from-env
atlawire repos PROJECT --base-url https://bitbucket.example.com/scm --token-from-env --json
```

Use the actual base URL, including any deployment context path. It can also come from
`ATLAWIRE_BITBUCKET_URL`. The default output uses the same TSV columns as `bbk repos` but
escapes backslashes and control characters so every repository stays on one row. `--json`
outputs the original field values as a JSON array. AtlaWire follows the server's `nextPageStart` and returns no
rows if any page fails or the page limit is reached. This first command uses bearer credentials
and HTTPS without redirects. Keyring and custom proxy/CA configuration are not wired yet.
See the [Bitbucket Server 5.10 REST reference](https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html).

## Retrieve a Bitbucket pull request

```shell
atlawire pr DEMO/widgets 123 --token-from-env
```

Use the same Bitbucket settings as for `repos`. `show` is an optional third argument. Unlike
`bbk pr show`, AtlaWire returns the server's JSON object without compacting it. It verifies the
returned PR ID and does not request any links in the response.

```shell
atlawire pr DEMO/widgets 123 files --token-from-env --json
```

For `files`, the default TSV columns are `path`, `type`, and `node`; `--json` returns those
fields as an array of objects. Bitbucket 5.10 can cap the list in one response. If the response
reaches the reported cap or otherwise indicates truncation, AtlaWire fails without printing
partial rows. This can also reject a list that happens to fit the cap exactly. Diffs and
comments are not implemented yet.

## Retrieve a Jira issue

With `ATLAWIRE_JIRA_TOKEN` supplied by your secret provider, run:

```shell
atlawire issue DEMO-42 --base-url https://jira.example.com/jira --token-from-env
```

The command accepts a key or a Jira browse URL and returns issue JSON by default, with
`renderedFields` requested. The destination comes only from `--base-url` or
`ATLAWIRE_JIRA_URL`; a pasted browse URL provides the key, not the server.

Add `--markdown` for a readable issue summary, description, and comments. AtlaWire matches
rendered comments by ID and falls back to fenced raw text where needed. It reports known
incomplete comment lists instead of making more requests. Converted HTML keeps link labels
and image alt text, not their destinations. Treat the Markdown as untrusted content.

See the [Jira Server 8.22 REST reference](https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/).

## Search Jira with JQL

```shell
atlawire jql "assignee = currentUser() ORDER BY updated DESC" --token-from-env --limit 25 --json
```

Use the same Jira URL and credentials as for `issue`. The default is TSV with the same columns
as `bbk jql`; `--json` emits an array and preserves `null` for missing status, type, priority,
and assignee. `--limit` defaults to 50 and accepts 1–1000. AtlaWire follows multiple pages when
Jira returns fewer results per page. A failed or inconsistent page produces an error without
publishing partial rows. If Jira omits the total, a short page alone does not prove completion.

## Retrieve a Confluence page

With `ATLAWIRE_CONFLUENCE_TOKEN` supplied by your secret provider, run:

```shell
atlawire page 12345 --base-url https://wiki.example.com/confluence --token-from-env
```

You can also set `ATLAWIRE_CONFLUENCE_URL`. The command returns page JSON, including
`body.storage.value` (XHTML). A pasted absolute page link with one `pageId` parameter supplies
the ID only; credentials go to the configured instance.

Add `--markdown` for readable text, simple tables, and code blocks. Unsupported macros are
marked, not executed, and no embedded resources are fetched.

## Search Confluence with CQL

```shell
atlawire cql "type = page AND space = DEMO" --token-from-env --limit 25 --json
```

Use the same Confluence settings as for `page`. The default is TSV with the `bbk cql` columns
`id`, `space`, `type`, `title`, and `url`; `--json` outputs an array. The limit defaults to 25
and accepts 0–1000. AtlaWire keeps the original query and configured endpoint for every page,
including when a server sends a continuation link. A failed or invalid page produces no
partial output.

## List Confluence spaces

```shell
atlawire spaces --token-from-env
```

Use the same Confluence settings as for `page`. The default output is TSV with the `bbk spaces`
columns `key`, `name`, and `type`; add `--json` for an array. The limit defaults to 100 and
accepts 0–1000. A failed or invalid page produces no partial output.

## List direct Confluence child pages

```shell
atlawire children 12345 --token-from-env --json
```

Pass a parent page ID or a pasted page URL containing one `pageId`. The URL supplies only
the ID. The default TSV columns are `id`, `title`, and `version`; `--json` preserves missing
versions as `null`. The limit defaults to 100 and accepts 0–1000. This lists direct children
only and does not print partial results on failure.

## Problem

Agent tooling for Atlassian usually assumes the newest Cloud API, a fixed set of operations, or
an extra service such as an MCP server. Corporate installations are often older, self-hosted,
and reachable only from inside a private network. The goal is direct, scriptable access to what
the installed version actually supports, with output that is safe to parse and failures that are
explicit rather than guessed.

## Design goals (not implemented)

- **One tool, two entry points.** A single CLI plus an importable Python library built on the
  same core, so interactive use, scripts, and agents share behavior instead of drifting apart.
- **Legacy versions are a first-class target.** Compatibility with Server and Data Center
  releases is established by a documented, test-backed version matrix — not by assuming one
  modern API response generalizes to every installation.
- **Machine-safe output.** JSON on stdout, diagnostics on stderr, documented exit codes, and no
  banners, color codes, progress bars, or prompts in machine-readable mode.
- **Bounded, honest pagination.** Page limits by default, an explicit full-fetch mode only when
  requested, and partial results reported as partial instead of silently truncated.
- **No daemon.** The tool runs, does its work, and exits: no background service or listening
  port. Any persistent cache or working data belongs in a standard per-user data/cache
  directory, never in the source checkout by default.
- **Works with the current user's setup.** Configuration, cache, and working data use standard
  per-user locations for the operating system, with explicit overrides for users and agent
  deployments. Credentials remain in the user's OS credential store, not in the cache.
- **Safe writes by default.** Generic REST access is read-only unless a mutating request is
  explicitly authorized; destructive convenience commands require explicit confirmation.
- **Clear trust boundaries.** TLS verification stays on; credentials stay out of plaintext
  files, command arguments, logs, and URLs; requests stay constrained to the configured
  instance so a crafted path cannot leak credentials elsewhere.
- **Reproducible checks.** Linting, typing, and tests run from a clean checkout; a live-instance
  suite is opt-in and never required for ordinary CI.

## Current non-goals

- Claiming Cloud or self-hosted feature parity before publishing version-specific test evidence.
- Cloud support in the initial release; the initial target is self-hosted Jira, Confluence, and
  Bitbucket.
- An MCP server or any always-running component.
- Bulk administration, migration, or backup tooling.
- Storing credentials in plaintext configuration files.
- Publishing a package or claiming supported versions before the version matrix and tests
  exist.

## Planned shape

Commands are expected to be grouped by product (`jira`, `confluence`, `bitbucket`) around a
shared configuration, credential, and HTTP core, with a generic REST passthrough for endpoints
that have no dedicated command. That passthrough is the practical form of broad API coverage:
it can reach documented endpoints, but it cannot make an endpoint exist on a server version
that does not provide it, and it does not turn undedicated endpoints into typed commands.

Product command names, flags, and output schemas are not fixed yet. Examples for Atlassian
operations will be added once those commands exist and have been run.

Third-party client libraries, including
[`atlassian-python-api`](https://github.com/atlassian-api/atlassian-python-api), are candidates
to evaluate rather than adopted dependencies. Requests is the planned synchronous HTTP transport;
product behavior will live in AtlaWire adapters rather than being coupled to an upstream client.
The project does not claim endorsement by or affiliation with any upstream library.

## Compatibility

Atlassian products differ across Server, Data Center, and Cloud in authentication options,
endpoint availability, pagination shape, and response fields. AtlaWire intends to handle those
differences in explicit adapters covered by contract tests, and to publish a version matrix
listing which product versions were actually tested, with which authentication method.

Right now that matrix is empty: no version, product, or authentication mode is claimed as
supported. The initial product scope is self-hosted Jira, Confluence, and Bitbucket; exact
product versions and authentication modes will be listed only after they are tested.

## Security boundaries

These are requirements for the implementation, not current behavior:

- Credentials should come from the operating system credential store by default, or an
  explicitly configured environment/secret provider. They are never written to plaintext
  configuration, passed as ordinary positional arguments, or echoed in logs or error payloads.
- An ignored local `.env` may supply credentials only to an explicitly invoked live-test suite;
  ordinary CLI/library use must not load it implicitly.
- Sensitive request and response headers are redacted before any diagnostic output.
- TLS certificate verification is enabled by default; disabling it requires a deliberate,
  visible opt-out.
- The raw REST passthrough validates method, path, and target host against the configured
  instance so that a supplied path cannot redirect a credential to another origin.
- Mutating HTTP methods are gated behind an explicit write flag, and retries apply only to
  operations that are safe to retry.

## Quality plan

The tools are listed in the development extra, but their project rules and CI checks are not
configured yet. The intended baseline:

| Area | Intended choice |
| --- | --- |
| Formatting and linting | Ruff, configured to one line-length and rule set |
| Static typing | Pyright, strict on the public API and external-data boundaries |
| Tests | pytest, with CLI-level and HTTP-boundary tests rather than mock-only unit tests |
| Edge-case input | Hypothesis for pagination, path, URL, and encoding invariants |
| HTTP simulation | `responses` for focused Requests-boundary tests; a local HTTP server for CLI end-to-end tests |
| Feedback | `coverage.py` to find untested changed behavior; no arbitrary project-wide threshold |
| CI checks | Dependency and secret checks on the normal offline test job |

Mutation testing can be added later for critical behavior if ordinary tests leave meaningful
uncertainty. No test count or percentage is a substitute for checking the important failure
cases.

## Testing

The current offline tests cover installed-CLI startup, list and search pagination, JSON and
TSV output, Markdown rendering, and failure behavior across all three adapters.
The broader plan has two test suites:

1. **Offline suite (default).** Deterministic unit, integration, and end-to-end tests run on
   every commit and in CI. At least one end-to-end path must invoke the installed CLI against a
   local test HTTP server, exercising the real command, configuration, credential selection,
   transport, adapter, and output boundaries without depending on internal services. Additional
   fixture/contract tests cover version-specific responses.
2. **Live suite (opt-in).** Runs against explicitly configured, preferably disposable
    Server/Data Center instances with least-privilege credentials. It must never touch production
    data and must never be a prerequisite for ordinary CI. A developer may keep a local,
    Git-ignored `.env` for this suite, loaded only by an explicit test command; the library and
    CLI must not load `.env` implicitly.

## Roadmap

See [TODO.md](TODO.md) for the prioritized checklist. It is the authoritative plan; this
README intentionally does not duplicate it.

## License

The repository currently ships an Apache-2.0 `LICENSE` file. The copyright holder and the
provenance of the code and documentation still need to be confirmed before any public release;
that open item is tracked in [TODO.md](TODO.md). This note records repository state, not a legal
opinion.

## Trademarks

Jira, Confluence, Bitbucket, and Atlassian are trademarks or registered trademarks of Atlassian.
AtlaWire is an independent project and is not affiliated with, endorsed by, or sponsored by
Atlassian.

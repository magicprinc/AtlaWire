# TODO

Prioritized, dependency-ordered plan. AtlaWire is an early implementation: unchecked items remain
open, and no product behavior or compatibility claim is made before it is tested and recorded.

## Resume after restart

- **Goal:** replace `bbk` for daily self-hosted Atlassian work and demonstrate stronger
  regression coverage. Keep `bbk` unchanged and usable until the side-by-side checks pass.
- **Saved work:** the editable Python 3.15 package has `projects`, `repos`, `branches`, `commits`,
  `file`, `pr` (show, files, comments, diff, and file), `issue` and `page` (JSON or Markdown),
  `jql`, `cql`, `spaces`, and `children`. Check `git status` before resuming; preserve local
  references and unrelated edits.
- **Last verification:** 899 offline tests passed, including installed CLI subprocesses.
  Ruff lint/format/security, Pyright, lock, and diff checks passed. History regressions
  checked fixed filters, cursor gaps, and malformed metadata at the commit row cap.
  Runtime tests used installed `markdownify` 1.2.3; the lock resolves 1.2.4.
  No live compatibility or corporate TLS/proxy proof.
- **Next slice:** Jira `mine` and `statuses`. Reuse the JQL pager; distinguish the status
  name list from search-result objects.
  Verify `projects` and `repos` live before relying on them for caching.
- **Where to start:** `src/atlawire/jira.py` owns Jira endpoints, `http.py` owns the
  authenticated transport, and `cli.py` owns command output. Use `tests/test_jira_e2e.py`
  and `tests/test_repos_e2e.py` as local-server test patterns. Compare the existing tool's
  `jira.jql()` and `jira.rows()` as read-only behavioral references; do not copy its
  single-request search assumption. See the [Jira Server 8.22 REST reference][jira-rest].
- **JQL contract:** preserve the existing `jql` command's useful columns and limit,
  respect the server's page size, and test a server-capped page, an empty result, and a
  later-page failure. Do not treat missing paging metadata or a failed request as a complete
  result. Keep tests offline with synthetic credentials. Preserve JSON `null` for absent status,
  type, priority, and assignee; only TSV renders those fields as empty cells.
- **Implementation workflow:** the primary agent defines the bounded contract, critical
  scenarios, expected outcomes, and plausible faulty behavior before delegation. DeepSeek
  V4.1 Flash HIGH implements the named tests and code, runs checks, fixes failures, and
  self-reviews. The primary agent reviews both production code and the tests' ability to catch
  defects, sends corrections back, and reruns affected checks. Test counts are not acceptance.
- **Verification cadence:** one assignment per usable workflow where practical. The worker runs
  focused tests and lint/type checks during implementation. The primary reviews the code and
  tests and runs the full regression suite once on the milestone candidate, not after every
  intermediate check. Cover each distinct failure mode at the smallest useful test boundary.
  Add a checkpoint or independent check when security, writes, or uncertain server behavior
  justify it; do not weaken those checks to save time.
- **Milestone commits:** commit each completed, verified milestone locally with a message
  explaining what changed and how it was verified. Exclude unrelated work. Only the owner
  pushes.
- **Milestone handoff:** a milestone commit is not the end of the task. Before ending a turn,
  record the next action here. If the next slice is in scope and unblocked, start it and
  report the actual dispatch. If work is waiting for review, permission, or a dependency,
  state what it is waiting for. On resume, review completed work or recover the recorded
  action before dispatching another worker; do not duplicate active work.
- **Design review:** assign each rule to the component with the information to enforce it.
  Keep CLI formatting, product behavior, and credential/transport handling separate. Prefer
  composition and narrow interfaces; share code only when it enforces the same contract.
  Review callers for knowledge of internals and test observable behavior at real boundaries.
  Use a design pattern only when it solves a concrete problem more simply.
- **Constraints:** use the existing Python 3.15 user installation, no project venv. Do not
  read secret files, run live writes, publish, or rewrite history while resuming this work.

[jira-rest]: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/

From the repository root, recheck the saved baseline before editing:

```shell
git status --short --branch
python --version
python -B -m pytest -p no:cacheprovider -q tests
```

## First milestone: replace the current Atlassian CLI

- [x] Map the existing Atlassian commands and candidate regression suites.
- [x] Port Bitbucket project repository listing and verify CLI output, paging, and failure
      behavior with an offline end-to-end test.
- [x] Review repository listing output: escape TSV control characters without changing JSON.
- [x] Port Jira issue lookup by key or browse URL with offline end-to-end tests for the
      configured destination, rendered fields, and error handling.
- [x] Port Jira JQL with bounded pagination, Bitbucket-independent Jira credentials,
      `bbk`-compatible rows, and no stdout on a later-page failure.
- [ ] Confirm which remaining workflows are used daily and port them first. Continue with
      Confluence page/CQL and Bitbucket code/PR review. Keep agent
      coordination and unrelated services out of AtlaWire.
- [x] Add opt-in Jira issue Markdown while preserving JSON. Match comments by ID and fall back
      to raw descriptions or comments when HTML cannot be used.
- [ ] Finish Jira issue CLI parity where useful: decide whether users need `--wiki` and `--out`;
      check optional metadata and comment rendering on the real target.
- [x] Port Confluence page retrieval before CQL. Fetch `body.storage`, version, space, and
      ancestors in one request; expose JSON first and verify a page ID or `pageId` URL, context
      path, and product-specific credentials through the installed CLI. A pasted URL supplies
      the ID only, never the request destination. Handle storage XHTML as a separate Markdown
      slice; do not claim macro parity from generic HTML conversion.
- [x] Add `page --markdown` without changing default JSON or making extra requests. Start
      with the formats used in engineering docs: headings, lists, simple tables, and
      `code`/`noformat` macros. Preserve code whitespace and keep embedded fences literal.
      Identify unsupported macros without fetching embedded resources or discarding readable
      body text. Defer macro parity beyond fixtures that represent real workflows.
- [ ] Finish Confluence page parity where useful: raw storage/HTML and output-file options;
      verify panel/link/table differences against real engineering pages.
- [x] Port CQL with the existing `bbk cql` row shape and default limit. Adapt the legacy
      pagination contracts: server-capped pages with or without a `next` link, an empty
      terminal page, malformed/inconsistent metadata, repeated pages, and a later-page
      failure with no stdout. Verify that server-supplied links cannot change the destination
      or rewrite the original query. Reuse this pager later only where contracts actually match.
- [x] Port Confluence `spaces` with legacy TSV columns, a bounded limit, and adapted
      pagination regressions using the CQL pager.
- [x] Port Confluence `children` with legacy TSV columns, a bounded limit, and adapted
      pagination regressions using the same pager and page-ID parser.
- [x] Port Bitbucket PR lookup with one instance-bound request and response identity checks.
      AtlaWire currently returns raw JSON; the legacy compact view remains open.
- [x] Port Bitbucket PR file listing. Server 5.10 documents `/changes` as a single capped
      response even though it uses a page envelope. Do not apply the repository cursor pager
      or treat a cap as a complete list. Test nested path objects and explicit or plausible
      truncation using the versioned reference before claiming parity.
- [x] Port Bitbucket PR comment activity with cursor pagination and no partial output.
      Preserve legacy columns and handle the 5.10 `commentAnchor` and `createdDate` fields.
- [x] Port Bitbucket whole-PR diff JSON retrieval. Reject declared truncation at all known
      levels without attempting fallback.
- [x] Render Bitbucket PR diff text as a readable review view, not a patch.
- [ ] Add and verify per-file diff requests and fallback separately.
- [x] Port Bitbucket repository and PR-side file reads with one raw text transport,
      repository-relative path validation, and explicit tests for forked PRs.
- [x] Port Bitbucket `branches` and `commits` using the repository cursor pager.
- [ ] Port Jira `mine` and `statuses` with legacy output and offline tests for scoped status filters.
- [ ] Port Jira and Confluence comment/page changes and Bitbucket PR changes with explicit write
      approval. Verify each write offline before any separately authorized live test.
- [ ] Run the same daily workflows with both tools on the self-hosted versions we use. Preserve
      useful behavior and document any intentional differences that affect scripts.
- [ ] Show concrete improvements over the current tool: clearer failures, no silent pagination
      truncation, and machine-readable output agents can rely on.
- [ ] Demonstrate stronger test coverage of those workflows and their failure paths: reuse
      relevant regressions, add focused unit and integration tests, and run the installed CLI
      end to end. Compare what the tests catch, not just how many tests there are.

Keep the current tool available until AtlaWire passes these checks. Prioritize a working port
over more packaging or framework work.

## Final acceptance: `bbk` parity

- [ ] Make a disposition table for every current `bbk` CLI command, library workflow, and test
      file. Record the AtlaWire equivalent, adapted test, and verified outcome; do not silently
      drop mixed or manual suites.
      If present in the local checkout, use `.development/review/2026-11-20_BBK_PARITY_BASELINE.md`
      as the starting inventory.
- [ ] Port and pass the applicable `bbk` regressions against the AtlaWire API. Keep offline
      tests as the default; run live reads and disposable-instance write checks separately.
      Test diagnostics and failure behavior as well as successful output.
- [ ] Resolve the scope of non-Atlassian integrations, agent coordination, and historical
      tool probes against the prior Atlassian-only boundary. Record where their functionality
      and tests live; none count as migrated without evidence.
- [ ] Establish AtlaWire as the home for Atlassian implementation notes and version evidence.
      Update `bbk` readers and the shared agent skill to point there before removing copies.
      Keep the skill focused on choosing commands, safely using them, and finding references.

## Product ideas to validate

- [ ] Add a redacted profile/capability view and consistent machine-readable failure categories.
- [ ] Consider compact agent-oriented projections as opt-in output. Keep existing JSON and
      TSV contracts intact. Prefer predictable flags and result budgets over a second interface.
- [ ] Design guarded writes with preview and explicit execution before adding bulk operations.
      Keep raw REST escape hatches instance-bound and read-only by default.
- [x] Port Bitbucket `projects` with `nextPageStart`, `key,name,public` TSV and optional
      description/link metadata in JSON. Offline tests cover noncontiguous cursors, links
      returned without dereferencing, and no partial output.
- [ ] Verify project and repository listings on the target instance, then evaluate opt-in
      cached snapshots of visible project/repository metadata: key or slug, short name,
      description when supplied, and a browser URL. Keep repositories scoped to parent project.
      Start with explicit refresh and freshness information rather than a background downloader.
      Do not replace a complete snapshot after a partial refresh, expose one credential's
      catalog under another, or fall back to cached content on authorization failure.

## 1. Decisions to lock before code

- [x] Confirm first release product scope: self-hosted Jira, Confluence, and Bitbucket. Keep
      adapter boundaries open to external/community modules, but do not claim other products or
      Cloud support in the initial release.
- [x] Set Python 3.15 as the minimum supported runtime; record and test the supported CI target
      in `pyproject.toml` before advertising compatibility.
- [x] Use a shared library core with a Click CLI facade; keep product adapters separate and
      independently extensible without adding a third-party plugin registry to the first
      release.
- [x] Use a synchronous Requests-based HTTP client for the first release; do not expose
      transport-specific objects as part of the public adapter contract.
- [x] Use uv for project/lockfile workflows and Hatchling as the build backend; verify current
      Python/platform compatibility and pin the build version when creating the project.
- [ ] Decide non-secret configuration precedence (CLI options > environment > per-user config);
      never accept credentials as command-line arguments.
- [x] Use the OS keyring by default for interactive credentials; allow explicit
      environment/secret-provider overrides for non-interactive use. Fail clearly rather than
      silently falling back to plaintext storage when a secure backend is unavailable.
- [ ] Wire keyring and per-user profiles for both implemented commands. They currently require
      explicit environment credentials. Verify corporate CA/proxy configuration and whether
      each target instance needs an authentication mode other than bearer.
- [ ] Decide the raw passthrough policy: which methods are allowed, how paths are validated
      against the configured base URL, and what exactly `--write` unlocks.
- [ ] Decide the pagination contract: default page cap, `--all`, and the machine-readable
      "partial result" signal.
- [ ] Decide how product/version differences are modeled (adapter per product + version
      capability probe) rather than branching inside commands.
- [ ] Decide retry policy per method class, including `429`/`Retry-After` and an overall
      deadline; state which failures are terminal.

## 2. Package foundation

- [x] Create `pyproject.toml` with the src layout, console entry point, and current package
      metadata. License metadata remains open until the provenance item in section 7 is resolved.
- [x] Add a lock file and pin the build backend; document the exact install command.
- [x] Add the local development toolset: Ruff, Pyright, pytest/pytest-cov, `responses`, Hypothesis,
      and pip-audit. The selected versions resolve for Python 3.15; favor active, suitable tools
      with established adoption.
- [ ] Run dependency and secret checks in CI.
- [ ] Add tool configuration in `pyproject.toml`: Ruff line length `88`, target version, rule
      selection, and exclusions for vendored or generated files.
- [ ] Configure Pyright strictness for the public interface, JSON decoding, adapters, and
      credential handling.
- [ ] Add a CI workflow (Windows and Linux) running lint, type check, offline tests, and
      dependency/secret checks; keep the live suite a separate, manually triggered job.
- [x] Run an initial advisory audit against the locked public dependencies. On 2026-11-20,
      `uv audit --frozen --no-build --no-python-downloads` reported no known vulnerabilities
      or adverse project statuses in 56 packages. Repeat for release changes.
- [x] Run Ruff's security rules against runtime source (`ruff check --select S src/atlawire`).
      No findings in the initial pass; this does not replace security review or secret scanning.

## 3. Configuration and paths

- [ ] Define per-user directories using platform conventions: standard config, data, and cache
      locations per OS, with an explicit override flag/environment variable.
- [ ] Support a configurable data/cache override for agent deployments. When sharing a parent
      directory with another application, use an AtlaWire-specific child path to avoid collisions.
- [ ] Specify cache policy before caching private API responses: profile/principal isolation,
      short TTL, bypass, write invalidation, and no credential headers or secret-bearing request
      bodies in the cache. Default to no response caching until these rules are tested.
- [ ] Do not load `.env` implicitly in library or CLI code. For explicitly enabled live tests,
      allow the developer's ignored local `.env` to be loaded by the test command (for example,
      uv's explicit `--env-file` option); CI uses protected environment variables. Offline tests
      must need no credentials.
- [ ] Keep credentials out of fixtures, logs, recordings, and command-line arguments.
- [ ] Validate configuration on load with actionable errors and no secret echo.

## 4. Adapters, HTTP core, and CLI contract

- [ ] Implement a shared HTTP core: timeouts, bounded retries with backoff, TLS verification,
      proxy support, redaction, and a single error taxonomy mapped to exit codes. The first
      read-only slice must disable automatic cross-origin redirects and test proxy/TLS behavior;
      do not retry writes.
- [ ] Implement Jira, Confluence, and Bitbucket adapters with explicit version differences and
      capability probes instead of optimistic calls.
- [ ] Implement the raw REST passthrough: method allowlist, path and host validation, read-only
      default, `--write` gate, and refusal to follow redirects that leave the configured origin.
- [ ] Implement paging per product/version/endpoint: Jira commonly uses `startAt` and
      `maxResults`, with `total` optional; Confluence commonly uses `start`/`limit` and
      `_links.next`; Bitbucket Server REST commonly uses `isLastPage` and `nextPageStart`
      (do not infer it from page length). Verify each supported response shape against
      versioned docs and fixtures; expose page limits, explicit `--all`, and a partial-result
      marker with the continuation token or reason.
- [ ] Map paging/server errors to explicit failures (unsupported endpoint, version mismatch,
      truncated result) rather than empty success.
- [ ] Implement CLI output contract: JSON to stdout, diagnostics to stderr, stable exit codes,
      no interactive prompts when non-interactive, and help text that lists operations.
- [ ] Add `--help`-driven operation discovery so an agent can enumerate commands without
      guessing endpoint names.

## 5. Tests

- [ ] Build the offline fixture suite from recorded, sanitized responses per supported product
      version; never commit real tokens, URLs, or user data.
- [ ] Include unit, integration, and end-to-end coverage. At least one deterministic offline
      E2E test must invoke the installed CLI against a local HTTP server and exercise the real
      CLI/configuration/credential-selection/transport/adapter/output boundaries.
- [ ] Cover CLI contract: parseable JSON, stdout/stderr isolation, exit codes, redaction,
      argument validation, and non-interactive behavior.
- [ ] Cover HTTP boundary: authentication failures (`401`/`403`), `404`, `429` with
      `Retry-After`, `5xx`, timeouts, malformed JSON, and redirect escape attempts.
- [ ] Add real TLS/CA and proxy tests and verify request/response size and time budgets.
      Local HTTP E2E tests do not prove TLS or corporate proxy behavior.
- [ ] Cover pagination: first page, empty page, repeated cursor, missing total, partial result,
      and `--all` with an enforced cap.
- [ ] Cover write safety: read-only default, `--write` required, non-idempotent methods never
      retried automatically.
- [ ] Add property-based tests for path/URL validation, encoding, and pagination invariants.
- [ ] Add an opt-in live E2E suite for the internal self-hosted Jira, Confluence, and Bitbucket
      versions, disabled by default and skipped without explicit configuration; use least-
      privilege, read-only credentials and document the target/version setup. Do not put internal
      hostnames or captured user data in public fixtures or CI logs.
- [ ] Use coverage reports to find untested changed behavior; add mutation testing only if a
      critical path needs stronger evidence.
      Use [the subprocess coverage configuration](.development/review/coverage-subprocess.ini)
      when including installed-CLI tests; the default coverage run does not measure those
      subprocesses.

## 6. Portability and cleanup

- [ ] Verify Windows and Linux behavior for paths, temp files, permissions, and line endings;
      remove any shell-only assumptions from library code.
- [ ] Verify no artifact is written outside the documented config/data/cache directories; keep
      local machine paths in untracked local configuration rather than public project files.
- [ ] Add a clean-checkout smoke check that builds the package, runs the CLI help, and runs the
      offline suite. Restrict test discovery to the intended project test directory; never
      collect unrelated `test_*.py` files under `.development/`.

## 7. Documentation, release, and provenance

- [ ] Before public release, confirm Apache-2.0 software licensing and imported code provenance.
      Keep the Markdown needed to verify requirements; documentation licensing is not a
      development blocker.
- [ ] Before pushing, review the tracked tree and commits not yet on the remote for internal
      paths, personal data, secrets, unrelated third-party material, and provenance. Do not
      rewrite published history without explicit owner approval.
- [ ] Publish the supported-version matrix from actually executed tests, with product version
      and authentication method per row.
- [ ] Document installation, configuration, credential setup, and exit codes from working
      commands only. The current checkout install command is `python -m pip install --user -e .`;
      keep it only while it works and the package remains unpublished.
- [ ] Add `CHANGELOG.md` entries per release; keep unreleased changes under `Unreleased`.
- [ ] Add agent integration examples after the CLI surface is stable and tested.

## 8. Candidate regression contracts from earlier bbk work (re-verify here)

These behaviors were exercised in the earlier bbk tooling. They are candidates to port as
regression tests for AtlaWire, not current tests and not proof of behavior in this repository.

- [ ] Bounded paging with an explicit partial-result signal instead of silent truncation.
- [ ] Raw passthrough path validation plus a read/write gate for mutating methods.
- [ ] Explicit environment credential selection and keyring lookup with redaction in errors.
- [ ] Retry behavior on `429`/`Retry-After` and `5xx`, and no retry for unsafe writes.
- [ ] Stdout/stderr separation and stable exit-code mapping for the documented error classes.
- [ ] JSON envelope stability for list endpoints (items, page metadata, continuation).

Each item must be re-derived from AtlaWire's own contract and observed to fail before the
implementation exists, then observed to pass; do not copy assertions on faith.

## 9. Open questions blocking compatibility claims

- [ ] Live Data Center paging: which Jira Server/DC releases return `total` reliably, which
      require `isLast`-style detection, and how to behave when the server omits both.
- [ ] Bitbucket continuation: verify per endpoint/version whether continuation uses
      `nextPageStart`, a link, or another cursor. If a server supplies an absolute continuation
      URL, validate its origin against the configured instance before sending credentials.
- [ ] Which authentication modes are actually available per version (personal access tokens,
      basic auth with API tokens, OAuth) and which must be documented as unsupported.
- [ ] Whether Confluence and Bitbucket legacy versions need separate adapters or a shared
      compatibility layer.

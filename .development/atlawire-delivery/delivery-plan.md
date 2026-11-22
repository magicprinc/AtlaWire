# AtlaWire: architecture review and delivery plan

**Verdict:** Fix the release blockers below. Continue with one installed CLI
slice and reconcile standard read coverage in parallel. Do not treat the
nine-method prototype, a working arbitrary-route command, or a green smoke
suite as the deliverable.

This is the plan for the implementer. See the companion
[delivery test plan](test-plan.md) for executable acceptance criteria.
The original local drafts and session ledger remain under
`.planning/2026-11-22-read-only-rest-and-bbk-parity/`. Commit changes to these
development plans as separate review iterations, without unrelated code.

## The agent's acceptance test

Give a fresh agent `atlawire` on `PATH`, access to run it, and the hint
“start with `atlawire --help`.” Credentials are configured locally by the owner,
not given to the agent. The agent must be able to discover what exists, choose
exactly one canonical command, build a valid call from its help, and interpret
success, no results, another page, or a failure without reading source or
upstream library docs. A shell-capable agent needs no separate MCP setup.

Proposed public flow, using the existing repository lookup ID:

```shell
atlawire --help
atlawire bitbucket --help
atlawire bitbucket repository get --help
atlawire bitbucket repository get DEMO widgets
atlawire --catalog
atlawire --describe bitbucket.repository.get
```

- `%cli-help-5`: Use standard CLI help: root lists product/utility groups and
  examples; groups list their commands or subgroups; command-level `--help`
  describes the selected operation and shows its syntax. Prefer positional
  identifiers and named options for ordinary calls; reserve JSON input for
  genuinely structured arguments. The canonical catalog is not a flat list
  of 200 CLI flags.
- `--catalog` lists every supported operation once: stable ID, product and a
  short task-oriented summary, with its command path. Keep existing operation
  IDs where they mean the same thing. Compatibility spelling is an alias, not
  another recommendation in the catalog. Do not infer unqualified IDs from
  whichever method names happen to be unique today.
- `--describe ID` gives required and optional inputs with types, defaults,
  bounds and allowed values; the expected success kind and important result
  fields; pagination and how to request the next page; permission, version or
  plugin conditions; and a runnable example with placeholder resource IDs
  (include its argument array so an agent need not guess shell quoting).
  Descriptions state what the method does and does **not** do, e.g. “List the
  available transitions; does not change issue status.”
- Every supported operation, including a library gap, is callable as a named
  read. Python offers `AtlaWire().call(ID, **params)` and thin product methods
  for common workflows. Both interfaces execute the same entry. Do not add
  a duplicate generic CLI syntax or a Python wrapper by hand for every ID.
- Help, JSON discovery and execution use one operation registry. Extend the
  existing `operations.py` registry and let Click consume its metadata for
  the ordinary cases; no generated source or new CLI framework. Do not scale
  the prototype's second registry. All help and discovery work offline, even
  when a product is not configured. The short guide shipped next to the wheel
  explains setup, these flags, success and error conventions, and a few
  workflows. It is not a second hand-maintained catalog.

### Local credentials and diagnostics

- `%credential-access-6`: Store the product URL/token pairs under the owner's
  home directory. Reuse the private BBK credential provider initially
  (`~/.config/atlassian/credentials.json` by default). The
  agent invokes the tool; it does not receive a token, supply one in arguments,
  or open a credential file. The tool loads only the selected product pair.
  A supported CLI that does not reveal secrets is not OS isolation: an agent
  with unrestricted filesystem access under the same account may be able to
  read that account's files directly. If the threat model requires isolation,
  restrict the agent to tool invocation or use a separate execution identity.
- `%runtime-log-6`: Keep an operational, rotating log in a user-private
  `atlawire` directory under the OS temporary directory, for example
  `%TEMP%\atlawire\atlawire.log` on Windows. Describe the location and retention
  in help and the quickstart. Use fixed size and backup-count bounds; log
  timestamps, operation IDs, products, attempt number, elapsed time, and safe
  status/error codes. Never log tokens, headers, full URLs, searches, payloads
  or unchecked exception text, even in debug mode. Do not log help/catalog
  calls. Keep rotation safe when several CLI processes run at once; a
  process-local logging handler alone does not coordinate that rotation.
  A bounded, process-safe append/rotate policy is enough. A log lock,
  unavailable directory or failed log write must not change the JSON result
  or its exit status. This is troubleshooting, not an audit ledger.

### Human setup is separate from the read surface

- `%auth-setup-7`, `%auth-choice-10`: Use one human-only command:
  `atlawire auth login <product> --url <server-base-url>`. Prefer browser
  consent without copying a token only if this deployment already supports
  a verified, configured authorization flow that the CLI can use. Return an
  authorization code through the registered flow, never a token in a URL.
  Do not introduce a new OAuth integration or server configuration change
  just to deliver setup.
- `%pat-onboarding-9`: The required, simple fallback opens the documented
  token-creation page (or shows its link if the browser cannot open). Show
  product-specific steps to create and copy a token, then wait for the owner
  to paste it into a hidden local prompt and press Enter. Use Python's
  [`getpass.getpass()`](https://docs.python.org/3.15/library/getpass.html)
  and treat `GetPassWarning` as a failure, not permission for visible input.
  Do not read the clipboard automatically, ask for the Atlassian password,
  accept a token in command arguments, or scrape browser cookies. Ordinary
  read commands never prompt for login.
- Use the documented page for the deployed product. Jira 8.22 and
  [Bitbucket Server 5.10](https://confluence.atlassian.com/bitbucketserver/bitbucket-server-5-5-release-notes-938037662.html)
  support PATs; [native Confluence PATs start at
  7.9](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html).
  Do not infer the authentication mechanism for the live Confluence instance
  from the 6.6 REST reference used for coverage. If the deployment's
  token-creation page is unknown, give the owner the setup guidance rather
  than opening a guessed URL.
- Save the verified URL/token pair to the same private BBK-compatible store
  only after explicit owner setup. Replacing a configured pair requires
  confirmation; preserve other products and existing fields, and do not replace
  a working pair on cancellation, validation failure or failed persistence.
  Test with a synthetic browser launcher, prompt and store. If the owner
  created a token in the browser but local saving failed, do not claim it
  was revoked.
- `%live-fixtures-8`: The owner confirms existing tokens are available. Use
  them via the existing private provider for the owner-run real-server
  checks; no re-enrollment, credential migration, or new auth flow is needed
  to verify the read release. Do not print, inspect or copy active tokens.

## Findings and decisions

### 1. `%plan-review-1`: The plan currently specifies two incompatible products

The original `final-delivery-plan.md` decisions said raw JSON, generic routes,
and optional full traversal. Its appended corrections say envelopes, named
operations, and page-first only. The phases still call for
raw wrapper output and late compatibility work. A worker could follow either
version and pass a different set of tests.

**Decision:** Publish one machine-oriented surface with a consistent envelope.
Preserve existing useful commands and their observable behavior during migration;
do not advertise them as an equal second way to use the new API. In particular,
distinguish general discovery of base capabilities (required) from public access
to a mutable SDK client (not required to provide the same reads). The owner
previously endorsed advanced library access with unsafe methods excluded
(ses_dfe0f5775ffeG7f6XccNrOWoMV #12044); confirm the deprecation or restriction of
that advanced surface, rather than treating a reviewer's recommendation as owner
approval to remove it. If existing `api-get`/`api-request` syntax must stay, resolve
only known method/product/route combinations to the shared registry. Do not ship
the current unrestricted forms alongside a supposedly read-only canonical API.

### 2. `%readonly-1`: A name filter does not enforce the public read boundary

[`sdk.py:175–219`](../../src/atlawire/sdk.py#L175) forwards unknown attributes
to the library client, so approval depends on naming, not behavior.
[`sdk.py:255–278`](../../src/atlawire/sdk.py#L255) accepts `/rest/` GETs subject
to a segment blacklist and matches semantic POSTs without binding them to the
product. An existing test explicitly accepts Confluence conversion under the Jira
product/client ([`test_sdk_cli_e2e.py:91–109`](../../tests/test_sdk_cli_e2e.py#L91)).
Serving two products on the same host makes product/context checking important;
matching the host alone is insufficient. The Jira mapping also records that the
library's issue read defaults to updating history.

**Fix:** Dispatch only reviewed reads, with fixed product, verb and route and
validated arguments. Retain semantic POSTs only by exact operation, with
documented conversion destinations and body representations. Disable optional
activity-history writes. Never derive destinations from result links; refuse
redirects by default and do not replay a semantic POST to another route. Preserve
the matched credential pair. Keep explicit environment mode if already supported,
but require a complete pair and never fall back after auth failure. Test that
rejected inputs do not even load credentials, and that no redirected destination
receives a request. Classify obvious admin reads by reference; park ambiguous
routes with evidence and an owner, rather than build a permission engine.

### 3. `%compatibility-1`: Fix behavior regressions, not the assertions that caught them

On this working tree the focused Jira reference run had **22 failures, 114
passes**. Twenty-one are CLI cases, including wrong JSON shapes, late malformed
rows, an oversized user page, 206, redirects and diagnostic differences.
[`cli.py:307–326`](../../src/atlawire/cli.py#L307) returns the SDK result
without domain checks, while the existing
[`jira.py:538–592`](../../src/atlawire/jira.py#L538) readers validate rows and
the user limit. The separate failing unit test checks for `pluginField` in all
fixtures, but the priority fixture uses `pluginRank`
([fixture](../../tests/test_jira_reference_unit.py#L20),
[assertion](../../tests/test_jira_reference_unit.py#L240)).

**Fix:** Reconnect the six compatibility commands to their existing strict
readers for the first green baseline. Migrate one command only after the
new adapter can preserve its contract; retain tests for malformed payloads,
status semantics, failure output and no follow-on request. Fix the unit oracle
to compare the fixture's actual independent field and nested values, not to
drop the preservation check. Do not promote `read_operation(use_library=True)`
as-is: [`operations.py:1200–1221`](../../src/atlawire/operations.py#L1200)
short-circuits on any SDK `None`, despite documenting a single route-specific
204 exception. Normal HTTP errors keep status and category; conforming empty
lists remain successful. Distinguish contract violations from revised wording
in diagnostics, rather than assuming every failing test is a library bug.

### 4. `%response-1`, `%errors-1`: A machine contract has to work before the HTTP request too

The current SDK commands parse JSON and resolve credentials outside their JSON
error handlers; Click usage failures bypass those handlers altogether
([`cli.py:688–809`](../../src/atlawire/cli.py#L688),
[`cli.py:3929–3931`](../../src/atlawire/cli.py#L3929)). The SDK relays
exception text, returns success unfiltered, and only redacts its diagnostic
body in `to_dict()` ([`sdk.py:84–105`](../../src/atlawire/sdk.py#L84),
[`sdk.py:271–314`](../../src/atlawire/sdk.py#L271)). Capping an extracted
string after the library has buffered a response is not a bound on the read.
The in-progress facade adds a second error formatter and treats anything
returned by `get_json` as success
([`facade.py:316`](../../src/atlawire/facade.py#L316),
[`facade.py:480–516`](../../src/atlawire/facade.py#L480)).

**Contract for the new surface:** CLI emits one strict JSON document on stdout
on every application-controlled outcome, including malformed arguments, missing
credentials and unknown operation. Exit `0` for success, `2` for usage or
configuration, `1` for failed execution. `--help`, human legacy output, process
termination and broken stdout are not JSON command results. Python returns the
same JSON-compatible result for expected failures. Do not promise to catch
Python signature errors outside the dispatcher. Parse and serialize strictly;
`NaN`/`Infinity` are not JSON.

- Success: `{"ok":true,"product":"jira","data":...}`. Preserve the complete
  parsed JSON and its unknown fields if valid and safe. `[]` is an empty list;
  `null` is allowed only for a documented no-content operation. A malformed
  JSON body, unexpected status or login HTML is an error, not a success
  string. Declared text commands return strings in `data`.
- Error: `{"ok":false,"product":"jira","error":{...}}`. Keep `status` (nullable),
  stable `code`, `classification`, safe `message`, operation ID (nullable),
  canonical route template (if applicable), `content_type`, `body`, `body_json`
  and `body_truncated`. Product can be `null` when unknown. Use one mapper for
  CLI and Python. Error codes must distinguish usage/configuration, access
  denial, missing resource, rate limit, timeout/network and invalid response.
  Guide the agent using stable codes, not wording it must pattern-match.
- `body` is a bounded, sanitized diagnostic excerpt, **not** an unconditional
  promise of byte-for-byte upstream text. Include `body_json` only if parsed
  and safe; withhold unsafe content. Never serialize exception strings, header
  dumps, credentials or request query/body. Test causal echoes in both
  success and error responses, preserving ordinary payloads; avoid redesigning
  all unrelated CLI output to catch coincidental strings. Apply actual
  response/read bounds where required and prove cleanup on failure.
- Binary is declared per operation, never guessed from the payload. Small
  binary uses a documented bounded base64 result. Large files/archives require
  an explicit destination and return a JSON receipt only after a complete
  bounded download. Use existing streaming/bounds helpers where needed; do
  not overwrite an existing file or leave partial output on failure. Reuse
  this policy rather than implement separate file handling per endpoint.

### 5. `%retry-2`, `%pagination-1`: Recover from a network blink, not by making the agent guess

[`sdk.py:159–172`](../../src/atlawire/sdk.py#L159) passes retry settings for
429/503 to the library. That alone proves neither connection recovery nor the
effective delay for `Retry-After`. The prototype's searchable/pageable methods
accept `limit` but not a continuation offset
([`facade.py:139–167`](../../src/atlawire/facade.py#L139),
[`facade.py:396`](../../src/atlawire/facade.py#L396)). It cannot be used
to reliably obtain page two.

**Fix:** One retry owner: use the pinned library's verified retry behavior or
its supported session configuration, not stacked retry loops. Specify a small
attempt limit, connect/read timeouts and bounded retry delays. Recover from a
transient connection failure/reset and selected transient statuses such as
429/503 where safe. On 429, honor `Retry-After` within the call budget; if it
does not fit, return a structured rate-limit failure. Do not retry 401/403/404,
invalid payloads, redirects, or unverified semantic POSTs. Do not imply a wall
clock deadline from a socket read timeout alone. Publish the effective policy
in discovery/help and check it without real sleeps using synthetic transport
failures, a subsequent success or exhaustion, and exact attempt counts.

One operation returns **one logical page**, not necessarily one attempt. Expose
documented continuation inputs (`startAt`, `start`, etc.) and keep upstream
metadata. For Bitbucket use the returned `nextPageStart` even when it is not
`start + limit`. An array without continuation metadata does not prove
exhaustion; a non-paged route remains non-paged. No automatic traversal in the
base API; prove it with a first response advertising a next page and a server
request counter. Bound explicit advanced fan-out separately.

### 6. `%mapping-1`, `%scope-1`: Neither a mapped route nor an SDK method proves coverage

The local mapping files answer different questions. Bitbucket counts full
enumeration as `covered` (`mapping-bitbucket.json`, lines 340–350) and omits
its read-only markup preview from a GET-only denominator (lines 13–56).
Confluence marks a library method `covered` even when it traverses or loses
the response envelope (`mapping-confluence.json`, lines 110–116). Jira records
four authorization-uncertain reads outside its count and a dubious GET inside
it (`mapping-jira.json`, lines 2430–2435). Bitbucket maps `application-properties` while
the SDK excludes that path by name. None of these discrepancies can be resolved
by adding up 109, 36 and 66.

**Fix:** Use the versioned official inventories (Jira 8.22 platform, Confluence
6.6 reference pending live confirmation, Bitbucket 5.10 core) as the starting
scope. Record product edition/module, method, normalized route, permission
evidence, documented request parameters, response kind/codes, and one of
required/excluded/unresolved with a reason. Resolve differences against
versioned docs and deployment evidence, including whether Agile is applicable;
track plugin/BBK-only reads separately. A required operation that is missing
or unsupported remains a gap. A 403 is not proof the endpoint is
administrative. Do not let uncertainty in a few rows block implementation of
the rest; do not erase those rows from the completion report.

Per required operation, record adapter choice, discoverability, installed
loopback evidence and live status separately. Use a high-level method where it
preserves documented arguments, status semantics, output and one-page
behavior. Use one fixed low-level library adapter for genuine gaps **or SDK
semantic mismatches**, not custom HTTP or wrappers around projected data
claimed to be raw. The pinned SDK's raw-response mode is a candidate for fixed
reads that need headers/status; validate the actual 5.0.5 behavior in the
slice. Report confirmed SDK bugs or maintainable feature gaps upstream with a
minimal sanitized reproducer; a projection chosen by the library is not by
itself a defect. Publishing an issue is distinct from preparing it.

### 7. `%cross-product-1`: Return surviving evidence without lying about completeness

The existing `find` fails closed on one product error and resolves all three
configurations before issuing any request
([`federated.py:177–190`](../../src/atlawire/federated.py#L177),
[`cli.py:329–348`](../../src/atlawire/cli.py#L329)). That is not the target
partial-success contract. Bitbucket code search is a plugin backed by an index,
not equivalent to repository-name search.

**Fix:** Leave the legacy behavior in place until a verified additive workflow
is available. Implement only named workflows from actual BBK use, using the
same base read operations. Report product provenance, status
(`ok`/`failed`/`unsupported`), rows, limits and continuation for each requested
product; distinguish failed reads from another page and truncated output.
Return available results with `complete:false` on partial failure; if all
requested products fail, return a top-level failure. Group a demonstrated
shared-host transport failure without conflating per-product 401/403 errors.
Keep results compact, preserve links/IDs as data, and offer detail by stable
reference. No local cache/FTS or new framework before the base is complete.

### 8. `%distribution-1`, `%verification-1`: The wheel and the installed CLI are not verified by a checkout

[`pyproject.toml:11–16`](../../pyproject.toml#L11) pins 5.0.5;
[`uv.lock:6–12`](../../uv.lock#L6) omits it. The E2E helper selects
`atlawire` by PATH and inherits the current environment
([`tests/_loopback.py:90–104`](../../tests/_loopback.py#L90)). The facade tests
call Python directly with an injected credential provider despite the E2E
filename ([`test_facade_cli_e2e.py:90–97`](../../tests/test_facade_cli_e2e.py#L90)).
That is useful loopback evidence; it does not exercise CLI parsing, stdout,
exit status or real credential resolution. The older
real-server checks exercise `api-request`, not the proposed CLI or the final
wheel ([`checks/test_sdk_live.py:17–29`](../../checks/test_sdk_live.py#L17)).

**Fix:** Reconcile the lock, build the versioned wheel and prove a clean
Python 3.15 install outside the checkout early. Use an approved isolated
install target, not a repo-wide environment migration. Check the import
location, version, console path and packaged catalog; run the docs-only agent
walkthrough on that exact artifact. For offline tests use synthetic credentials,
an isolated home and a deliberately selected environment. For real-server tests
the owner runs an approved fixture-scoped, read-only command and provides only
revision/artifact identity and sanitized statuses and counts. An old smoke run
and a fake-subprocess parity test are not fresh live evidence.

## Execution order

| Order | Owner and work | Exit check |
| --- | --- | --- |
| 1. Recover the baseline | Integrator records tracked and untracked candidate changes, collects current worker patches without overwriting work, restores Jira compatibility, fixes its independent fixture oracle and reruns focused tests. In parallel gather live versions and safe fixtures through the owner, and reconcile the lock/build configuration. | Focused tests green; a reproducible candidate, explicit scope questions, and a wheel built/installed through the documented path, or a named installation blocker. |
| 2. Prove one vertical slice | One owner wires the existing registry, product credential resolution, private SDK transport, JSON boundary and CLI discovery. Add one high-level read per product where compatible, at least one fixed fallback, and one semantic POST. Include a real continuation, an auth error and a recovered network failure. Use the prototype as input rather than making it a second public surface. | Independent documented fixture expectations; unit → installed loopback → owner-run live smoke. Root and command `--help`, `--catalog` and `--describe` work before auth. Invoke a documented example outside the checkout; exact request, response, failed-output and retry oracles pass. |
| 3. Complete the base by product | Split Jira, Confluence and Bitbucket into non-overlapping product batches. Each worker owns its operation data, adapter exceptions and tests. Integrator owns shared dispatcher, credentials, CLI and docs. Classify binary, semantic POST and ambiguous permissions early rather than leave the difficult routes to the end. | Every required ID has discovery, independent request/response assertions and a passing installed-loopback case. Live status recorded per operation; representative live successes for each distinct adapter/response kind and all three products. No silent exclusions. |
| 4. Verify additive workflows | Reuse implemented Jira comment search, Confluence rendering, Bitbucket repo grep, PR review/diff and search work where it passes its contracts. Compare named Atlassian workflows with BBK using known stable fixtures, not two mutable latest-result sets as the only oracle. | Product-failure/partial-results tests, bounded work and real BBK parity evidence for the workflows claimed. Base discovery and calls remain available. |
| 5. Freeze and hand off | Run the complete offline suite and project quality checks on the reconciled candidate. Build the final wheel, repeat clean-install discovery and smoke, and collect the owner's sanitized live receipt. Have the requested fresh PonyTail reviewer challenge the original requirements, code and tests. Independent verification of the credential/read boundary uses the approved isolated candidate, not HEAD alone. | Publish a local release report: exact artifact, commands, versions, failures/skips, known unsupported scope, quickstart and feedback. No release/sign-off with unresolved material failures or missing decisive live evidence. |

Per-operation tests should share a harness, not an oracle. The harness can
read the manifest to enumerate IDs, but expected paths, encoded parameters and
payloads come from independent reference fixtures. Shared negative tests cover
unknown operation/argument, product mismatches, auth echo, redirects and
malformed payloads. Critical checks must fail on the corresponding faulty
behavior. Test rotation and a failed log write with the real installed CLI:
the output stays parseable and no token or synthetic request/response content
appears in logs, including rotated files. Use the existing offline suite and
opt-in checks under `checks/`; update the live runner to exercise the final
entry point before relying on it.

**Today:** Aim for the complete delivery gates, not a new round of abstract
architecture. The first useful checkpoint is a green compatibility baseline
plus an installed, self-describing slice. If any gate remains open at handoff,
label the artifact a **review candidate** and list the exact missing operation
IDs or evidence; do not lower the acceptance criteria to meet a date. BBK
retirement is a separate owner decision after Atlassian parity, credential
independence, preservation of its changes/state and an explicit plan for its
other integrations. No removal, deployment or upstream posting in this review.

## Review evidence

- Base `79e501d4a7d71cc858014f965f1b376b89a6a566` in
  `D:/REPO/github/AtlaWire`. Tracked and relevant untracked files were inspected;
  this was not a frozen full candidate (the new facade appeared during review).
- From this directory, using `C:/Python315/python.exe -B -m pytest -p
  no:cacheprovider --tb=no -q` with a unique project-local `--basetemp` per
  selection, an isolated synthetic home and no real credentials:
  - `tests/test_jira_reference_unit.py tests/test_jira_reference_cli_e2e.py`:
    exit **1**, **114 passed**, **22 failed**, **0 skipped** before the
    compatibility fix. Same selection after the retained focused fix:
    exit **0**, **136 passed**, **0 failed**, **0 skipped**. This is not a
    pass on a full integrated candidate.
  - `tests/test_sdk_unit.py tests/test_sdk_e2e.py tests/test_sdk_cli_e2e.py`:
    exit **0**, **21 passed**, **0 failed**, **0 skipped**. The tests establish
    the old SDK slice, not the proposed facade, retry policy or release.
  - `tests/test_facade_unit.py tests/test_facade_cli_e2e.py`: exit **0**,
    **87 passed**, **0 failed**, **0 skipped**. Unit plus Python-to-HTTP
    loopback, not the installed CLI.
- **INCONCLUSIVE:** full current suite, clean wheel install, actual runtime
  versions/permissions, endpoint inventory completeness, live results for the
  final entry point, and independent verification of the new boundary. No live
  services contacted and no credential or live response files read in this
  review. Local SDK source access was denied; Context7 documented the upstream
  interface, not the exact installed code. The plan treats unverified
  transport behavior as a test requirement, not as a proven feature.

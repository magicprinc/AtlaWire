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

## Start here: implement, do not re-plan

**Scope (`%delivery-scope-4`).** Here “service” means the installed `atlawire`
tool and its Python API calling existing Atlassian servers. No new HTTP server,
MCP server, UI, background process, cache, or separate authentication system.
Existing special-purpose commands are worth preserving; they are neither
another canonical API nor a substitute for documented base REST reads.

**Checkpoint:** 2026-11-23, code `16b739a`, review `6af2841`.
Use [audit-follow-up.md](audit-follow-up.md) for failure evidence and the
smallest justified repair. Historical findings later in this document explain
the contract; they are not a current list of open bugs. Do not redo the lock
or catalog round-trip fix unless a current check fails.

**Assessment evidence:** DeepSeek Flash reviewed the CLI, discovery, Python
exports, credentials, and documentation (`ses_df9f7e3f2ffe0gpUZpu30Q92QN`).
Source and local metadata checks confirm the counts below and the gap between
the installed slice and the required interface. That review reported one
unintended Jira GET returning 404 during a probe; it is excluded from live
evidence. No fresh full suite, clean wheel or live validation is claimed here.

### Requirements and current status

| Requirement | What exists | What is still owed |
| --- | --- | --- |
| **R1. A new agent can discover and use the installed tool unaided.** Root and command `--help`, offline `--catalog` and `--describe`, runnable examples and stable JSON. | 65 top-level Click commands; `read <id>` runs through the registry. The catalog recommends 3 canonical IDs. Existing flat workflows remain available. | Complete one documented CLI/Python path, close the parse/discovery and environment-only credential defects, and prove a fresh agent can finish from the final wheel and shipped guide. Describe parameters, page controls, result kinds and limits accurately. |
| **R2. Named read-only access to each supported API.** `atlassian-python-api==5.0.5`; documented semantic-read POST only, no admin/write actions. | SDK-backed `read` and fixed fallbacks, 202 registered entries (Jira 109, Confluence 36, Bitbucket 57; 199 GET, 3 POST), 7 binary entries. Those are inventory counts, not an acceptance denominator. | Close public raw-session exposure; freeze what is required against versioned sources. 180 entries declare no query fields and 152 use generic JSON. Distinguish genuinely absent fields from missing implementation; verify actual documented parameters, types, statuses, media and pagination. |
| **R3. Ordinary reads are safe and deterministic.** Explicit paired credentials, bounded reads and retries, no false complete results, binary files never overwrite. | BBK-compatible saved loader, explicit environment mode, retry and body limits, download paths, structured SDK responses. | Fix the reproduced safety and contract issues first: overwrite, truncated binary/JSON and gzip, invalid numeric output, invalid retry header/TLS behavior. Keep exact wire and no-request regressions. |
| **R4. Owner setup is separate from agent reads.** No agent handles raw tokens. | Existing saved credential pairs work as a provider; a real owner can keep using them while development continues. | Implement the approved manual enrollment path without guessing an unconfirmed product URL or token mechanism; preserve store on failure. Verify sanitized diagnostics and bounded log behavior per the contract. No prompt in ordinary reads. |
| **R5. Useful BBK read workflows remain available.** Search, exact reads and cross-product workflows are additive. | Jira issues/JQL/metadata, Confluence pages/CQL/history, Bitbucket search/files/grep/PR review, `whoami`/`selftest`, `find`, and `attachment-get --out` exist with differing evidence. | Reconcile actual BBK CLI flags and public helpers, not command names. Repair `find` unavailable-pair, mixed-term and total-budget gaps. Prove parity on required workflows and disclose plugin/version limitations. Non-Atlassian migration and BBK retirement are separate. |
| **R6. Proof follows the artifact.** Offline, clean installed wheel, representative live behavior, independent review of critical boundaries. | Focused tests and older live receipts exist. They do not establish clean-wheel or live parity on current code. | Freeze one wheel hash, make the required offline matrix green, run the supported live matrix with the owner, and record coverage and exact unresolved checks. |

Reference scope starts with Jira Server 8.22, Confluence Server 6.6, and
Bitbucket Server 5.10 documentation. Those are **reference** versions, not
claims about current target deployments; record actual versions, authentication,
permissions and plugins separately. Cloud and broad Data Center claims require
separate evidence. The full release remains all agreed documented standard
non-admin reads and required BBK workflows; an installed **review candidate**
is an earlier checkpoint, not a scope reduction.

**Decisions to obtain from the owner, without blocking step 1:** confirm the
canonical CLI/Python migration before changing that public interface, confirm
the deployed product versions and enrollment methods, then review the required
inventory and any exclusions. Ask for the approved isolated wheel target and
fixture-scoped live run only when the respective gates are ready. Existing
credentials are not a reason to use the real provider for an offline probe.

**First handoff:** a commit that fixes the publish-time overwrite in both
download paths, with a failing-before/passing-after regression. The model can
start it now using [slice A](audit-follow-up.md#work-order-for-the-implementer).
Do not pause for another whole-project audit. A useful installed CLI
**review candidate** is the next milestone; do not promise a full release date
until the required inventory is frozen and the live owner inputs are known.

**Implementation decision:** Canonical commands and Python methods use the
existing operation registry and a single private `atlassian-python-api`
adapter. The initial installed slice uses `jira.project.get`,
`confluence.space.get`, and `bitbucket.repository.get`, followed by the
page, fixed fallback, and semantic POST cases in the test plan. Do not make
`read <id>` or the prototype's separate registry a second canonical interface.
Follow the [execution order](#execution-order) below. Inventory research can
start now without delaying the shared safety fixes. The approved command
design is grouped CLI plus thin Python wrappers over the same registry.
If the owner prefers to retain generic `read <id>` as canonical for speed,
record that decision first. Until then, keep current spellings as working
compatibility paths; do not advertise both forms as canonical or delay
transport and test fixes while the decision is pending.

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
  whichever method names happen to be unique today. Keep the existing
  top-level `name`, `help` and `commands` metadata for existing consumers;
  add a compact `operations` list for the canonical reads. This is additive
  discovery metadata, not a second way to execute the read.
- `--describe ID` gives required and optional inputs with types, defaults,
  bounds and allowed values; the expected success kind and important result
  fields; pagination and how to request the next page; permission, version or
  plugin conditions; and a runnable example with placeholder resource IDs
  (include its argument array so an agent need not guess shell quoting).
  Descriptions state what the method does and does **not** do, e.g. “List the
  available transitions; does not change issue status.”
- `%verify-32`, `%catalog-38`: The runtime operation registry is the
  authority for the canonical command path, inputs and response semantics.
  Add only the missing facts to its entry for each operation: a concise
  purpose, an example argument array, result kind and key fields, and the
  documented permission, version and pagination rules. For non-paged
  operations say so; distinguish a documented default from a server-selected
  or unknown default, and do not invent permissions. Generate help and JSON
  from these entries. Agents start with `--help` for browsing, `--catalog`
  for machine enumeration, and `--describe ID` for an exact call. `commands`
  describes the actual Click tree for compatibility; `operations` identifies
  canonical reads. If the projections disagree, fix the mismatch before
  advertising the operation; do not ask the caller to choose one.
- Every supported operation, including a library gap, is callable as a named
  read. Python offers `AtlaWire().call(ID, **params)` and thin product methods
  for common workflows. Both interfaces execute the same entry. Do not add
  a duplicate generic CLI syntax or a Python wrapper by hand for every ID.
  `%python-contract-31`: The first slice proves this with one representative
  installed-wheel comparison of a canonical CLI command, `AtlaWire.call`,
  and one named Python wrapper. Do not duplicate the per-ID CLI suite in Python.
- Help, JSON discovery and execution use one operation registry. Extend the
  existing `operations.py` registry and let Click consume its metadata for
  the ordinary cases; no generated source or new CLI framework. Do not scale
  the prototype's second registry. All help and discovery work offline, even
  when a product is not configured. The short guide shipped next to the wheel
  explains setup, these flags, success and error conventions, and a few
  workflows. It is not a second hand-maintained catalog.
- `%docs-40`: Ship the existing `docs/AGENT-QUICKSTART.md` as the short
  guide alongside the wheel. It owns installation, setup and troubleshooting;
  README links to it. The shared result/error contract owns field meanings and
  stable codes; the guide explains how to read that contract with examples.
  The operation registry owns per-operation semantics. Do not maintain a new
  walkthrough, error-code table or endpoint reference with the same facts.

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
  in help and the quickstart. Start with one MiB per file and at most three
  backups as a local retention policy, not a workload assumption. Log
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
  accept a token in command arguments, or scrape browser cookies. Send setup
  instructions and prompts to the terminal or stderr, leaving stdout for the
  final status. Ordinary read commands never prompt for login.
- Use the documented page for the deployed product. Jira 8.22 and
  [Bitbucket Server 5.10](https://confluence.atlassian.com/bitbucketserver/bitbucket-server-5-5-release-notes-938037662.html)
  support PATs; [native Confluence PATs start at
  7.9](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html).
  Do not infer the authentication mechanism for the live Confluence instance
  from the 6.6 REST reference used for coverage. The implementer records the
  documented setup for each product; the deployment owner confirms the live
  version, token mechanism and page or instructions used. Jira 8.22 and
  Bitbucket 5.10 use the documented PAT flow; enable the Confluence PAT
  instructions only where that mechanism is verified. If a known bearer
  token is available but its creation page is not verified, guide the owner
  through the approved source and accept it via the same hidden prompt; do
  not open a guessed page. A deployment with no verified way to obtain an
  accepted bearer token remains unsupported for new enrollment: return
  `credentials_error` (exit `2`) with guidance, without opening a browser
  or prompting. An OAuth-only deployment does not require us to build
  OAuth as part of this release.
- `%auth-proof-31`: Before saving, reuse the proof criteria already in
  [`identity.py`](../../src/atlawire/identity.py): Jira `/myself` must
  identify a user, Confluence must return a `known` user with a nonempty
  username, and Bitbucket must pass an authenticated dashboard read rather
  than a public route. HTTP 200 alone does not prove authentication.
- Save the verified URL/token pair to the same private BBK-compatible store
  only after explicit owner setup. Replacing a configured pair requires
  confirmation. Preserve other products and existing fields. Validate first,
  then atomically publish the completed private file. Cancellation or failure
  before that publish point leaves the old file intact. `%credential-writers-31`:
  Enrollment is a manual single-writer operation: finish one AtlaWire or BBK
  configuration update before starting another against the same store.
  Document that restriction rather than adding cross-tool locking. Reads
  may still run during enrollment. Test with a synthetic browser launcher,
  prompt and store. If the owner
  created a token in the browser but local saving failed, do not claim it
  was revoked.
- `%live-fixtures-8`: The owner confirms existing tokens are available. Use
  them via the existing private provider for the owner-run real-server
  checks; no re-enrollment, credential migration, or new auth flow is needed
  to prove the initial read slice. The handoff still needs the documented,
  tested manual setup flow for the deployments claimed at handoff; one-click
  consent is optional. The deployment owner validates the real setup or
  confirms that only existing credentials are supported on that deployment.
  Existing-token access alone does not pass the new-enrollment check. Do not
  print, inspect or copy active tokens.

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
to the library client; the reviewer confirmed the public proxy exposes the
generic `request()` method without invoking a write. The `api-get` path also
followed a synthetic 302 to a second loopback server and exited successfully.
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
redirects and do not replay a semantic POST to another route. Preserve the
matched credential pair. In explicit environment mode, validate both values
before constructing a client or sending a request; an absent token is not
anonymous mode. Never fall back after auth failure. Restore product-specific
positive POST coverage and reject the wrong product in a separate no-request
test. Classify obvious admin reads by reference; park ambiguous routes with
evidence and an owner rather than build a permission engine.

### 3. `%compatibility-1`: Fix behavior regressions, not the assertions that caught them

Before the retained compatibility fix, the focused Jira reference run had
**22 failures, 114 passes**. Twenty-one were CLI cases, including wrong JSON
shapes, late malformed rows, an oversized user page, 206, redirects and
diagnostic differences. The former `_sdk_json` CLI helper returned SDK results
without domain checks, while the existing
[`jira.py:538–592`](../../src/atlawire/jira.py#L538) readers validate rows and
the user limit. The separately failing unit test expected `pluginField` in
all fixtures, but the priority fixture uses `pluginRank`
([fixture](../../tests/test_jira_reference_unit.py#L20),
[corrected assertion](../../tests/test_jira_reference_unit.py#L241)).

**Fix retained:** The six compatibility commands again use their strict readers,
and the unit oracle compares the independent field and nested values. Migrate
one command only after the new adapter can preserve its contract; retain tests
for malformed payloads, status semantics, failure output and no follow-on
request. Do not promote `read_operation(use_library=True)`
as-is: [`operations.py:1200–1221`](../../src/atlawire/operations.py#L1200)
short-circuits on any SDK `None`, despite documenting a single route-specific
204 exception. The reviewer observed an empty HTTP 200 returned as `None` for
Jira project lookup in this Python branch; the compatibility CLI does not
enable the branch. Pass status and content to the operation validator before
interpreting an empty body. Normal HTTP errors keep status and category;
conforming empty lists remain successful. Distinguish contract violations from
revised wording, rather than assuming every failing test is an SDK bug.

### 4. `%response-1`, `%errors-1`: A machine contract has to work before the HTTP request too

The current SDK commands parse JSON and resolve credentials outside their JSON
error handlers. Malformed JSON and missing configuration both reproduced
`exit 1` with no JSON stdout; missing token in explicit environment mode also
reached the synthetic server and returned success. Click usage failures bypass
the JSON handlers altogether
([`api-request` handler](../../src/atlawire/cli.py#L759),
[`main()`](../../src/atlawire/cli.py#L3907)). The SDK relays
exception text, returns success unfiltered, and only redacts its diagnostic
body in `to_dict()` ([`sdk.py:84–105`](../../src/atlawire/sdk.py#L84),
[`sdk.py:271–314`](../../src/atlawire/sdk.py#L271)). Capping an extracted
string after the library has buffered a response is not a bound on the read.
The in-progress facade adds a second error formatter and treats anything
returned by `get_json` as success, without checking response kind
([`facade.py:316`](../../src/atlawire/facade.py#L316),
[`facade.py:480–516`](../../src/atlawire/facade.py#L480)).

**Contract for CLI consumers:**

| Entry point | stdout and exit status |
| --- | --- |
| Canonical read or `--describe` | One strict JSON envelope. `0` success, `2` usage/configuration, `1` failed execution. Includes framework-level argument errors and unknown operation IDs. |
| `--catalog` | One JSON metadata document with the existing command metadata and the new canonical operation list; exit `0`. |
| `--help`, `--version` | Plain text; exit `0`. No credential, log or network work. |
| Owner-only `auth login` | Prompts/instructions out of stdout; stdout gets one safe final JSON status, without the token. |
| Documented compatibility commands | Keep existing output, exit and error contracts unless an unsafe path must be closed. Compatibility commands are not the new machine contract. |

Process termination and a broken stdout pipe are outside the JSON promise.
`%errors-33`: A valid invocation selects one top-level action. Product and
command help such as `atlawire bitbucket repository get --help` is legal.
Top-level `--catalog` and `--describe ID` are standalone: combining either
with the other, with root `--help`/`--version`, or with a command is
`validation_error`, exit `2`, in either argument order. Handle this before
Click eager callbacks can print and exit. Do not treat an option name inside
a parsed value or after the end-of-options marker as a second action; shell
quoting is not part of argv.
Use one boundary around canonical CLI argument parsing, configuration and
execution, including unknown options and missing arguments. Keep the legacy
contract for recognised legacy commands. Build one JSON document before
writing; if output is interrupted, callers must reject an incomplete
document rather than expect a second envelope on the broken stream.
Python returns the same JSON-compatible result for expected failures. Do not
promise to catch Python signature errors outside the dispatcher. Parse and
serialize strictly; `NaN`/`Infinity` are not JSON.

- Success: `{"ok":true,"product":"jira","data":...}`. Use `product:null`
  when the result has no single product. Preserve the complete parsed
  JSON and its unknown fields if valid and safe. `[]` is an empty list;
  `null` is allowed only for a documented no-content operation. A malformed
  JSON body, unexpected status or login HTML is an error, not a success
  string. Declared text commands return strings in `data`.
- Error: `{"ok":false,"product":"jira","error":{...}}`. Keep `status` (nullable),
  stable `code`, broad `classification`, safe `message`, operation ID (nullable),
  canonical route template (if applicable), `content_type`, `body`, `body_json`
  and `body_truncated`. Product can be `null` when unknown. Use one mapper for
  CLI and Python. Keep predictable codes: `validation_error` for usage,
  `credentials_error` for missing or malformed local configuration,
  `http_<status>` for server HTTP failures, and `timeout`, `transport_error`,
  `invalid_response`, or `internal_error` for the corresponding execution
  failures. Classify HTTP 401/403/404/429 as authentication, authorization,
  not found, and rate limit respectively. Guide the agent using stable codes,
  not wording it must pattern-match.
- `body` is a sanitized diagnostic excerpt capped at 8 KiB, **not** an
  unconditional promise of byte-for-byte upstream text. Include `body_json`
  only for a complete, safe, parseable body, not a truncated fragment.
  Never serialize raw exception strings, header dumps, saved credentials or
  request query/body as diagnostics.
- `%response-bound-31`: Preserve the existing read budgets in the canonical
  SDK adapter: **8 MiB for JSON, 1 MiB for declared text**, measured on
  HTTP content-decoded bytes before parsing. Count bytes from the stream,
  not only `Content-Length`; close the response on the first read over the
  limit, return `invalid_response` with the received HTTP status for an
  oversized success, and emit no partial success. For HTTP errors keep the
  original status and read only enough for the diagnostic excerpt and its
  truncation flag. Reuse the bounded-reader helper where applicable; do not
  add a separate transport or weaken the existing limits.
- `%token-scope-26`: A loopback server deliberately reflected a synthetic
  bearer value in a valid success payload; no live token exposure was shown.
  This is not a separate release gate or a reason to add generic token
  scanning, rewriting, or fail-closed filtering of valid upstream data.
  Keep existing protections and tests. Ensure AtlaWire itself does not
  print values from its credential store, emit auth headers, or log request
  or response bodies.
- `%binary-35`: No binary subsystem in the JSON-only first slice. When
  implementing the first required binary operation, record its concrete
  size limit, media/response kind and output contract before writing code.
  Use bounded base64 JSON for small inline objects or an explicit destination
  and JSON receipt for files/archives. Implement only the form that real
  operations need. Never infer destinations from response links, overwrite
  an existing file, or publish a receipt or partial file on failure. Reuse
  existing streaming/bounds helpers. Deferring that implementation to its
  first consumer does not remove required binary operations from release.

### 5. `%retry-2`, `%pagination-1`: Recover from a network blink, not by making the agent guess

[`sdk.py:159–172`](../../src/atlawire/sdk.py#L159) passes retry settings for
429/503 to the library. The review measured four requests on repeated 503s,
reported exhaustion as `transport_error`, and intercepted a scheduled
90-second 429 delay without waiting. A dropped connection before a response
did recover on the second attempt; preserve that behavior.
The prototype's searchable/pageable methods
accept `limit` but not a continuation offset
([`facade.py:139–167`](../../src/atlawire/facade.py#L139),
[`facade.py:396`](../../src/atlawire/facade.py#L396)). It cannot be used
to reliably obtain page two.

**Fix (`%retry-34`):** The private SDK adapter is the only retry-policy owner
for canonical reads. Configure the library or its supported session to do the
retry if it can meet the contract. If neither can, disable SDK/session
automatic retry and keep the small policy at that adapter around SDK calls.
Never stack retry engines. **Three total attempts** and **five seconds of
cumulative scheduled waits between attempts** are chosen client defaults,
not a measured SLA. Use 5 s connect and 30 s idle read limits, inherited
from the strict path. Time spent connecting or reading is not retry wait.
Use the same policy for loopback; only the test clock/sleeper differs.

Retry an eligible GET on 429/503 or transient failure before any response.
Do not retry certificate, configuration or protocol validation failures, or
semantic POSTs in the first slice. Use `Retry-After` for
429/503 when it is a valid nonnegative delay in seconds or an HTTP-date;
compute an HTTP-date delay from the current UTC time, with past dates
treated as zero. If missing or invalid, use 1 s before the second attempt
and 2 s before the third. No extra jitter in the initial policy. If the
chosen wait exceeds the remaining budget, do not sleep or send another
request: return the current HTTP error (429 or 503). If the final attempt
returns an HTTP error, keep its status and safe diagnostics; if it ends
without an HTTP response, use `status:null`. Do not retry other HTTP errors,
invalid payloads, redirects, or a binary download after partial output.
These are not a wall-clock deadline. Publish the policy and test it with
synthetic faults.

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

**Fix:** Use the official [Jira 8.22 platform](https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/),
[Confluence 6.6 reference](https://docs.atlassian.com/atlassian-confluence/REST/6.6.0/)
pending live confirmation, and
[Bitbucket 5.10 core](https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html)
inventories as the starting scope. Record product edition/module, method,
normalized route, permission
evidence, documented request parameters, response kind/codes, and one of
required/excluded/unresolved with a reason. Resolve differences against
versioned docs and deployment evidence, including whether Agile is applicable;
track plugin/BBK-only reads separately. A required operation that is missing
or unsupported remains a gap. A 403 is not proof the endpoint is
administrative. Do not let uncertainty in a few rows block implementation of
the rest; do not erase those rows from the completion report.

`%scope-30`: The integrator reconciles the existing mappings into a tracked
`rest-inventory.json` beside this plan, outside the runtime package. Freeze
the target product/edition/reference versions and each row's
method, normalized route, stable ID, response kind, disposition and source
anchor. Required rows define the completion denominator; excluded and
unresolved rows must include a reason and evidence. Do not derive the list
from the runtime registry or count the historical mappings as final. The
inventory can be built in parallel with the first slice; settle remaining
in-scope uncertainty before claiming full coverage. Changes to scope after
freeze require a recorded decision, not removal of a failing test. Compare
the required IDs with the advertised canonical base; explicitly identify
additive or compatibility-only operations outside that set. No smaller
subset may be called the complete release.

`%library-role-31`: Canonical operations always go through the pinned SDK.
The existing strict HTTP path remains for legacy callers during migration;
it is not an alternative canonical backend, and there is no transport
auto-fallback on failure. Retain reusable validation, error mapping and
bounded-read helpers, not a second backend behind the canonical command.
Per required operation, record adapter choice, discoverability, installed
loopback evidence and live status separately. Use a high-level SDK method where it
preserves documented arguments, status semantics, output and one-page
behavior. Use one fixed low-level library adapter for genuine gaps **or SDK
semantic mismatches**, not custom HTTP or wrappers around projected data
claimed to be raw. The pinned SDK's raw-response mode is a candidate for fixed
reads that need headers/status; validate the actual 5.0.5 behavior in the
slice. A projection deliberately chosen by the library is not by itself a
defect.

### Upstream bug reports and feature requests

`%upstream-issues-27`: Use the
[atlassian-python-api GitHub issue tracker](https://github.com/atlassian-api/atlassian-python-api/issues)
when the gap is in the library, not in our use of it. Search for existing
issues first. Write issue titles, descriptions, test comments and supporting
materials in clear English.

- **Confirmed library defect:** Write one minimal runnable test that uses
  the library directly, without an AtlaWire wrapper. Demonstrate the failure
  for the intended assertion on the pinned version; check the latest
  compatible release if an approved environment is available. Open a bug
  issue explaining **what breaks, why it matters, and what was expected**.
  Include SDK and Python versions, Atlassian product/edition/server version,
  relevant OS and transport versions, a documentation reference, exact
  reproduction steps, and sanitized expected/actual results. Add the
  complete test as a separate comment on that issue, with its run command,
  dependencies and any necessary synthetic fixtures.
- **Material missing capability:** After checking the library docs and API
  surface, open a feature request if a documented read is missing or a
  limitation forces a meaningful workaround. Explain the real workflow it
  blocks, why the existing method is insufficient, the proposed behavior
  and a small acceptance example. Include affected versions, the reference
  endpoint and parameters, and how the current workaround behaves. Do not
  file a feature request for every stylistic preference or wrapper.

Share only synthetic or sanitized evidence. Never post real credentials,
internal URLs/IDs, customer payloads or sensitive logs. Route suspected
security vulnerabilities through the upstream private reporting process.
Record the issue and test-comment links in the operation's evidence where
applicable. Prepare a ready-to-post draft if publishing is not authorized;
do not mark it opened. A tested compatible fallback can ship without
waiting for an upstream fix.

### 7. `%cross-product-1`: Return surviving evidence without lying about completeness

The existing `find` fails closed on one product error and resolves all three
configurations before issuing any request
([`federated.py:177–190`](../../src/atlawire/federated.py#L177),
[`cli.py:313–332`](../../src/atlawire/cli.py#L313)). That is not the target
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

`%bbk-denominator-31`: In the existing release evidence, record the required
read-only Atlassian BBK workflows and the replacement, check and result for
each. Start from the BBK inventory, not from the subset already implemented.
An unimplemented required workflow stays visible. This is not another
runtime registry; non-Atlassian BBK integrations stay outside AtlaWire.

`%federated-budget-31`: When the first multi-product workflow is implemented,
bound its total logical reads across products and terms, not just rows
returned. Choose and document the cap for that workflow, use the existing
per-read retry policy, and report an exhausted budget separately from an
HTTP failure or an empty result. No general scheduler or budget engine.

### 8. `%distribution-1`, `%verification-1`: The wheel and the installed CLI are not verified by a checkout

[`pyproject.toml:11–16`](../../pyproject.toml#L11) pins 5.0.5;
[`uv.lock:6–12`](../../uv.lock#L6) omits it. The E2E helper selects
`atlawire` by PATH and inherits the current environment
([`tests/_loopback.py:90–104`](../../tests/_loopback.py#L90)). `--describe` is
not wired in the current CLI, and `--catalog` contains Click command metadata
but no canonical operations list. The facade tests
call Python directly with an injected credential provider despite the E2E
filename ([`test_facade_cli_e2e.py:90–97`](../../tests/test_facade_cli_e2e.py#L90)).
That is useful loopback evidence; it does not exercise CLI parsing, stdout,
exit status or real credential resolution. The older
real-server checks exercise `api-request`, not the proposed CLI or the final
wheel ([`checks/test_sdk_live.py:17–29`](../../checks/test_sdk_live.py#L17)).

**Fix:** Reconcile the lock, build the versioned wheel and prove a clean
Python 3.15 install outside the checkout early. Use an approved isolated
install target, not a repo-wide environment migration. Normalize Click
metadata to native JSON values at the catalog producer without changing the
wire shape or dropping choices. Run the documented help → describe → example
sequence as an actual subprocess from that wheel, with a synthetic saved
credential file read by the real loader. Check the import location, version,
console path and packaged catalog. For offline tests use synthetic credentials,
an isolated home and a deliberately selected environment. For real-server tests
the owner runs an approved fixture-scoped, read-only command and provides only
revision/artifact identity and sanitized statuses and counts. An old smoke run
and a fake-subprocess parity test are not fresh live evidence.

## Execution order

| Order | Owner and work | Exit check |
| --- | --- | --- |
| **1. Stop false success and data loss** | Begin with one commit: no-overwrite publication for both download paths (`audit-follow-up.md`, slice A). Next close SDK body/status failures, gzip, JSON and retry defects inside the existing transport modules in small commits (slice B). Repair the three known harness failures without relaxing permission checks. Log the baseline before editing. | Each critical test fails on the current behavior and passes unchanged after its fix; affected modules pass. Stop and report a blocker if the primitive cannot publish safely on the target filesystem. Do not replace the transport, add a backend, or change namespaces. |
| **2. Make one complete agent path work** | Repair env URL selection and canonical JSON parse/action errors now; these fixes do not require selecting new public syntax. Keep the approved grouped design unless the owner changes it. Confirm the Python migration before modifying public exports; never export the prototype's second registry or raw SDK session. Use the three lookup IDs, one paged route, one fixed fallback, `jira.search.post`, and one binary read. | From a clean installed **review candidate**, run help → catalog/describe → advertised argv → result/report. Prove credential pairing and zero-I/O local refusals. Compare one Python call and wrapper to the same CLI operation once that migration is approved. Missing approval leaves the Python gate open, not the CLI fixes blocked. |
| **3. Reconcile and finish REST by product** | Start classification in parallel with step 1 if authorized; implement route batches only on the stable step-2 path. Put the required versioned inventory and reproducible generator inputs under version control. Use presence of important params, statuses, continuation and media as the gap list. Use existing valid implementations before adding metadata or fallbacks. An integrator owns shared dispatch and manifest merge; product workers must not independently change them. | Every required route has one canonical ID, a runnable call, an independent installed fixture and a disposition against documented/deployed scope. Prefer a reusable test harness with independently authored data, not hundreds of copied CLI tests. Gaps and denied classifications stay visible. |
| **4. Close owner setup and BBK workflows** | Use the existing private provider and manual browser + hidden paste, with confirmed product-relevant auth. Add the required bounded, best-effort diagnostics. Close known `find` gaps and verify each required BBK workflow against its existing behavior, including mixed results and documented differences. Correct stale README/quickstart/coverage claims from evidence. | Non-interactive/unsupported setup fails without exposed input; failed replacement preserves the store. Logging failure leaves results unchanged and no sensitive fields enter logs. `find` keeps successful terms/products with explicit errors; budget exhaustion is distinct. Every required BBK row has a check and outcome. |
| **5. Freeze, verify and hand off** | Run all [release gates](test-plan.md#5-release-gates-and-handoff) on the exact code and final wheel. Have a fresh reviewer challenge code and tests; isolated execution only with owner approval. Ask the owner to run the fixture-scoped live selection on that same wheel. | Provide the artifact hash, commands, counts, exits, versions, missing IDs, known limits and sanitized live results. No unresolved safety finding, in-scope missing operation, or missing decisive evidence in a release. Otherwise label it **review candidate**. Do not retire BBK or publish as part of this work. |

**Instructions to the model taking this over:** Read this section and the
matching test row. Start writing the discriminating regression for step 1
instead of commissioning another general audit. Fix one behavior at a time;
keep the existing SDK and established tests. Run focused checks per commit;
run the full suite and wheel gates on the integrated candidate, not after
every small edit. Commit only the completed slice with a descriptive message.
Record each checkpoint in
`.planning/2026-11-22-read-only-rest-and-bbk-parity/progress.md`: commit,
command, outcome and next open row. Do not restart completed work after a
context switch. While the integrator handles shared fixes, Flash workers can
reconcile separate product references or BBK workflows read-only; one writer
per file in each implementation wave. Keep integration and gate runs with the
primary model. A blocker report names the failing test/operation, evidence
and specific decision needed; it does not propose another redesign.

Per-operation tests should share a harness, not an oracle. The harness can
read the manifest to enumerate IDs, but expected paths, encoded parameters and
payloads come from independent reference fixtures. Shared negative tests cover
unknown operation/argument, product mismatches, missing credentials, redirects and
malformed payloads. Critical checks must fail on the corresponding faulty
behavior. Test rotation and a failed log write with the real installed CLI:
the output stays parseable and no token or synthetic request/response content
appears in logs, including rotated files. Use the existing offline suite and
opt-in checks under `checks/`; update the live runner to exercise the final
entry point before relying on it.

## Review changes to carry into implementation

The second pass compared the steps with the test plan and walked through a
fresh install, an unknown operation, a dropped connection, a second page,
and cancellation while replacing a token. Corrections: preserve existing
catalog consumers, distinguish JSON from human and legacy output, specify
retry/rotation limits, make manual setup a handoff gate without blocking
the first read slice, and pin verification to the actual CLI and artifact.
No claim is made that this pass proves the runtime behavior.

The final pass checked whether a plausible broken implementation could still
pass the proposed tests. The [fault checklist](test-plan.md#4-prove-the-critical-tests-can-fail)
requires a real failure at the intended boundary and a pass after the fix.
It also separates the installed CLI evidence from Python-only tests and ties
clean-install and live checks to the same wheel hash.

The subsequent PonyTail source/loopback review on `f936b32` and its working-tree
candidate ended with **251 passed, 1 failed, exit 1, no skips** across the
Jira reference, SDK, facade and catalog selections. The catalog failure was
`test_catalog_is_strict_json_serializable`: nine choice fields differed by
Python `tuple` versus decoded `list`. It did not show invalid CLI JSON.
Carry the confirmed cases into the first slice rather than rebuilding the
facade or expanding the catalog first. Full suite, final wheel and live
verification remain open.

### Decisions on the implementer's objections

| Objection | Decision and reason |
| --- | --- |
| `%scope-30` | Accept the independent release inventory; reject a reduced release. An installed slice is useful, but does not meet the owner's full-coverage requirement. |
| `%library-role-31` | Accept one private SDK path for canonical reads; reject making the strict legacy transport their backend. The pinned library is an explicit constraint, and preserving legacy behavior during migration does not require two canonical paths. |
| `%verify-32`, `%catalog-38`, `%docs-40` | Accept; the registry owns operation facts, generated discovery surfaces serve different callers, and the existing quickstart owns setup. No duplicate schema or guide. |
| `%errors-33` | Accept explicit action selection and incomplete-output semantics; reject exempting canonical parse failures from JSON. That would move error detection back into each caller. |
| `%retry-34` | Accept fixed defaults and one owner; do not add jitter tuning or a configurable retry framework without a need. |
| `%binary-35` | Accept implementing binary output with its first required consumer; reject dropping mandatory binary reads from the release scope. |
| `%setup-36` | Accept product-specific instructions and owner verification; reject speculative OAuth or guessing the live Confluence setup from REST reference docs. |
| `%gates-37`, `%testscope-39` | Accept exact offline/live gate split and bounded negative controls; representative live results do not imply per-operation live coverage. The test plan names the approval and evidence rules. |
| `%dates-41` | Accept removing scheduling language from acceptance; retain the installed slice as a technical milestone. |

If a mandatory gate remains open, label the artifact a **review candidate**
and list the exact missing operation IDs or evidence. BBK retirement is a
separate owner decision after Atlassian parity, credential independence,
preservation of its changes/state and a plan for its other integrations.
No removal, deployment or upstream posting in this review.

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

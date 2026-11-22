# AtlaWire delivery test plan

Companion to [the delivery plan](delivery-plan.md). These
are instructions for the implementer, not a test result.

**Target:** An agent who has only the installed command can learn it, execute
supported reads without handling secrets, and distinguish a valid result, an
empty result, another page, and a failure. The final artifact covers all
required operations in the agreed versioned inventory, with additive
workflows kept separate.

## 1. Lock the candidate and the evidence

1. Record the commit and tracked **and untracked** candidate changes. Install
   and test that candidate, not a different edit, a stale console launcher, or
   clean `HEAD` without the changes. Do not run a release gate while workers
   still edit that candidate.
2. Use CPython 3.15 and record the interpreter, installed library version,
   resolved package location and console launcher. Use a synthetic home,
   explicit synthetic BBK credential path, loopback or dummy endpoints and a
   deliberately selected environment for **all** offline commands. Include
   subprocesses. Do not assume passing mock tests prove egress restrictions.
   Use no real credential files, inherited product values, proxy/netrc state,
   or non-loopback test targets offline.
3. For every required operation, keep one row: stable ID, docs version/anchor,
   chosen SDK adapter, contract fixture, installed CLI case, live status and
   reason if not verified. The operation matrix may enumerate the test cases;
   it cannot supply their expected request/response. Derive method, path,
   parameter semantics, expected response and permission scope from the
   reference or independent fixture evidence. If the manifest had the
   documented path or parameter wrong, the test must fail.
4. Record the exact command, cwd, candidate/artifact hash, executed/failed/
   skipped counts and exit code. A blocked, filtered, empty or skipped test is
   not a pass. Store summaries, not command dumps containing real settings or
   payloads.

## 2. Start with the regression and one installed slice

The Jira-focused run reproduced 21 CLI regressions and one fixture-oracle
failure. The reviewed fix, retained in the working tree at the owner's
request, passed all 136 cases in that same selection. Recheck it on the
integrated candidate; preserve the malformed-row, page-cap, redirect, status,
and raw-field assertions. The priority fixture uses `pluginRank`, unlike
other reference fixtures; compare an independent expected nested value, not
the same mutable object returned by a mock.

Before expanding the catalog, prove these paths from the pinned library through
the installed CLI:

| Example | Why it is in the slice |
| --- | --- |
| Jira project lookup; a Confluence content or space lookup; Bitbucket repository lookup | Three real product clients, three context paths and three credential pairs; known ID/key/slug in the returned object. Select an exact high-level method if its contract fits. |
| Bitbucket paged project listing | Detect an SDK helper that traverses internally, drops the wrapper, or calculates the next offset. |
| One fixed SDK fallback for a documented route with no equivalent high-level method | Prove fallback is a supported named operation, not an arbitrary URL, and preserves output shape. |
| Jira search by semantic-read POST | Prove that method, product, JSON body, and response schema are retained and that arbitrary POST is not enabled. |
| One real authentication/authorization error **offline**, and one recovered network failure **offline** | Prove runtime mapping, automatic retry and output framing without a live fault injection. |

In each batch: **unit first → installed CLI loopback → owner-run live
validation**. Write a representative critical regression before the fix and
show that it fails for the intended behavior, then passes unchanged. If a
bug has no runnable original implementation, use a small controlled faulty
variant or an isolated negative-control fixture. Do not inject faults into
the shared candidate or the live server. For routine route additions, share
the harness; do not reproduce the whole boundary suite per route.

## 3. Required scenarios and what each test must reject

### A. Agent discovers and uses the tool, without source

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Fresh install, no credentials: root help, product help, command `--help`, `--catalog`, `--describe` a known operation | All work offline and show the expected command, usable parameters/defaults and result kind. Catalog has one row per supported ID and one canonical command per task. Unknown describe ID emits a structured error and does not echo the submitted value. A broken description, stale alias, browser launch, credential access or HTTP request fails the check. |
| Use only installed help/JSON to run a documented example on a synthetic fixture | Execute the advertised argv, not a corrected hand-written call. Assert documented required options, typed input, default behavior and exact returned object. Wrong ordering, missing options, invalid quoting and help/runtime drift fail. |
| Agent distinguishes normal results from errors | Test JSON-only stdout and exact exit code for every new machine-facing entry point. Valid object, list, empty list, declared text and documented no-content success are distinguishable. Human `--help`/`--version` and documented legacy commands are the explicit exceptions. Test Python and CLI parity for a representative operation; a Python-only loopback case is not CLI evidence. |

### B. One registered read really does what its description says

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Every required ID, with independent synthetic request and response fixture | Capture the real method, context-prefixed route, parsed query/body, matched synthetic bearer and request count. Assert a meaningful response shape and fixture identity, including at least one extra field where valid. Use full payload comparison on representative raw responses. A correct status on the wrong resource, or discarded fields/envelopes, fails. |
| Parameter boundaries | Cover a missing required argument, unknown argument, wrong type (including boolean as an integer), documented limits and enum members. For supported parameters, send Unicode, spaces, `+`, `&`, repeated names and an identifier/path that requires encoding. Check parsed query/body **and** the relevant exact wire spelling to catch double encoding and duplicate-key loss. Do not apply a restrictive generic key regex to a documented different identifier domain. |
| Page 1 advertises page 2 | Fixture returns `nextPageStart=19` after a request with `start=5, limit=2`; assert the client emits the first envelope intact and sends exactly one request on a healthy transport. Explicitly request page 2 from the advertised continuation, then assert `start=19`. Also cover Jira offset and Confluence metadata where those adapters paginate. Reject fetching page 2 automatically, deriving `7`, stripping the cursor, or calling a bare array exhaustive. |
| Response validation | A valid empty array is successful. A wrong object/array type, malformed late row required by the contract, login HTML for JSON, bad JSON, non-finite number, disallowed 206, unexpected 204 and missing mandatory field fail without partial stdout. A documented 204 maps to `data:null`; distinguish it from an undocumented 200 JSON `null`. Verify text and binary using declared endpoint kinds, not heuristics. |
| Positive binary and interrupted download | Compare bytes or an independent SHA-256, not just a file name or byte count. Exercise size cap, interrupted stream, an existing output file and cleanup. Never overwrite an existing file or publish a completed receipt or partial output on failure. Test a non-UTF-8 binary fixture so replacing bytes with decoded text fails. |

### C. Read-only and credentials: prove the point of refusal

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Unknown, mutating and excluded admin ID; unsupported method/route alias; wrong-product semantic POST; path escape or invalid context | Test before credential resolution and assert zero requests on the approved listener and a second forbidden listener. Run against every retained public escape hatch, including advertised SDK access and old route aliases if they survive. Confirm approved semantic POSTs still work under only their registered product. Do not carry forward the existing test that accepts Confluence conversion with the Jira client. |
| Same host with different product contexts and synthetic tokens | Only the selected configured product receives its paired token. A missing product pair, wrong destination, malformed pair or rejected credential must not try another product, reach a redirect, or load another source as fallback. Check unselected products continue to work. |
| Redirect from GET and semantic POST | Refuse off-origin and wrong-context redirects before a second request. Test a redirect that would preserve POST as well as a normal login redirect. Verify both listener counts, not just the eventual error. |
| Optional GET side effects | Verify the Jira issue read does not request activity-history updates. Verify listing transitions never invokes an actual transition. The first accepted request is inspected, not inferred from its response. |
| Credential-safe results and logs | Synthetic response echoes a long fixture token in success and error paths (including JSON escaping where relevant). Safe ordinary bodies still keep their documented excerpt and parsed form; echoed credentials, authorization fields and unsafe diagnostics never reach stdout, stderr or log files. Test a valid non-secret control case to reject a catch-all that returns empty data/errors. |
| Human setup, **if included in the candidate** | Synthetic browser, hidden terminal and private temp store. Correct product instructions, no visible fallback, no read of the clipboard, token verified against only the selected URL. Failed validation, canceled prompt, confirmed replacement and failed write must preserve preexisting data as specified. Test complete matched-pair replacement without dropping unrelated fields/products. A browser-consent path also needs valid/canceled callback, wrong state and no token output. Never mint, rotate or revoke live tokens as a release test. |

### D. Error and retry behavior

- Through the installed CLI, verify structured errors for bad CLI arguments,
  invalid structured input, unknown operation, absent configuration, 401,
  403, 404, 429, 5xx, transport/timeout and malformed response. Check
  `status`, stable `code`, `classification`, safe `message`, and bounded
  `body`/`body_json`/`body_truncated` where applicable. Assert null HTTP
  status for pre-HTTP failures. Include a valid JSON error with an unknown
  field, plain text, empty body and an unsafe or over-limit body. Require
  exactly one JSON document with the agreed exit code; merely asserting
  `returncode != 0` fails the contract.
- Verify the effective pinned retry owner, not just constructor attributes.
  A recoverable pre-response connection failure and a 503 followed by 200
  each produce one successful result and the expected attempt count. Test
  429 followed by success within budget, and a `Retry-After` beyond budget
  that does **not** induce the advertised wait or another call. Exhaustion
  produces the right error with no extra attempt. A unit-level controlled
  clock/sleeper checks delay and bounds; real loopback checks that the
  installed transport actually retries. Do not depend on wall-clock sleeps
  or purposely trigger throttling on the real service.
- Prove no retries for non-retryable HTTP, redirect, invalid data, and
  semantic POST not explicitly declared retryable. Separate the healthy
  single-page request-count test from retry cases. After all paths assert
  teardown, not unconditional cleanup that masks a leaked response/session.
- Run the CLI against a private scratch log directory with a small test
  rotation threshold, then induce a log-write failure. Check both active and
  rotated logs for safe event fields and absence of sensitive fields. Two
  concurrent CLI processes must not create unbounded backups or alter the
  stdout result because rotation is contended. Do not require lossless audit
  logging: a bounded best-effort diagnostic log may skip an event.

### E. Additive workflows and BBK comparison

Use fixtures with a known issue key, page ID, PR ID or pinned repository
commit. Assert exact results or a justified projection, not just that a result
exists. Compare stable BBK observations and expected AtlaWire improvements,
not the current search ranking of unrelated live datasets. Test a partial
failure, all requested products failed, unsupported Bitbucket Search,
pagination/limits vs true errors, ref pinning and documented diff truncation.
An empty result must not hide an unsupported or failed product.

## 4. Release gates and handoff

1. **Focused green.** From `D:/REPO/github/AtlaWire` in the isolated offline
   environment run:
   ```text
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_jira_reference_unit.py tests/test_jira_reference_cli_e2e.py
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_sdk_unit.py tests/test_sdk_e2e.py tests/test_sdk_cli_e2e.py tests/test_facade_unit.py tests/test_facade_cli_e2e.py
   ```
   Include the new installed-CLI test selection for the slice. Run affected
   compatibility tests with each batch. These commands are not the release
   suite and do not prove the current new CLI path by themselves.
2. **Full offline green and coverage reconciliation.** Run
   `C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests` plus
   project lint/types and the applicable dependency audit. Give pytest a
   unique project-local `--basetemp` if used. Report tool failures instead of
   suppressing them. Reconcile the required inventory against advertised IDs
   and independently verified test cases; report exclusions/unresolved items
   separately. No untested required ID, unexpected skip, or unsupported
   required operation counts as done.
3. **Clean wheel proof.** Check the lock (`uv lock --check`); build a versioned
   wheel with the approved Python 3.15 tooling. In an approved isolated
   install target outside the checkout, prove exact wheel hash, package
   metadata, imported module location and console launcher. Run section A
   there plus the slice from section 2 over actual loopback transport.
   A passing editable install or `CliRunner` alone is not this evidence.
4. **Real-server proof.** the owner runs the updated fixture-scoped live
   read-only runner for the same installed artifact using the saved
   credentials. Record the observed server versions and a sanitized outcome
   per run. Require positive shape/identity checks for each product and
   representative distinct adapter/response kinds (including a real page
   continuation, semantic POST if supported, and binary if mandatory), plus
   successful BBK comparisons for the workflows claimed. No read of real
   fixture values or tokens by the reviewer, no live failure injection. A
   gap in permission, fixture or availability remains visible in the matrix;
   mark it inconclusive, not passed. State explicitly which operations were
   exercised live; do not equate representative checks with universal
   live coverage.
5. **Review before handoff.** Implementer self-reviews code **and tests**
   against the original requirements and attaches the evidence above.
   Return the exact candidate and test receipt to the reviewer. The fresh
   review challenges both the tests and implementation; separately
   authorized independent execution uses an isolated copy of that candidate.
   Unsupported required scope, missing decisive live evidence, failed
   checks or unresolved safety findings block release; report a review
   candidate instead. BBK retirement remains a separate owner decision.

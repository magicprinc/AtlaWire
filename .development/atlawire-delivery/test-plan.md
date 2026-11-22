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
3. Compare the checked-in release inventory with the advertised canonical
   base and test coverage IDs; reject omissions, duplicates and unclassified
   additions. The inventory is derived from versioned references, not emitted
   by the runtime registry. For each required ID record the SDK adapter,
   contract fixture, installed CLI case, live status and reason if unverified.
   Tests may use the inventory to enumerate IDs, not to construct expected
   requests or responses. Derive those expectations independently; an
   incorrect route shared by the registry and inventory must still fail.
4. Record the exact command, cwd, candidate/artifact hash, executed/failed/
   skipped counts and exit code. A blocked, filtered, empty or skipped test is
   not a pass. Store summaries, not command dumps containing real settings or
   payloads.

### What counts as a useful test

Write down **input → externally observable outcome → plausible defect**
before writing production code. Test the public contract without importing
the production function that computes the expected answer. A test that only
asserts “a command exists”, “stdout is JSON”, “the result is nonempty”, or
“a mocked SDK returned exactly what we stubbed” is not a behavior test.

For a request rejected before I/O, use a paired valid case to prove the
listener and request recorder work, then assert zero requests on the invalid
case. At the unit boundary, explicitly fail if credentials or transport are
accessed. For subprocess cases, bound the run, check its exit status and
assert that the server thread finished without hiding handler failure. A
launch, import, timeout or fixture failure does not demonstrate that a
regression test detected a product defect.

## 2. Start with the regression and one installed slice

The Jira-focused run reproduced 21 CLI regressions and one fixture-oracle
failure. The reviewed fix, retained in the working tree at the owner's
request, passed all 136 cases in that same selection. Recheck it on the
integrated candidate; preserve the malformed-row, page-cap, redirect, status,
and raw-field assertions. The priority fixture uses `pluginRank`, unlike
other reference fixtures; compare an independent expected nested value, not
the same mutable object returned by a mock.

The subsequent PonyTail selection passed 251 tests and failed
`test_catalog_is_strict_json_serializable`. Do not diagnose it as invalid
CLI JSON: the encoder accepted the catalog, but Click choice tuples became
lists on decode. Keep the round-trip assertion and check that normalization
preserves the advertised choices and legacy catalog structure.

Before expanding the catalog, prove these paths from the pinned library through
the installed CLI:

| Example | Why it is in the slice |
| --- | --- |
| `jira.project.get`, `confluence.space.get`, `bitbucket.repository.get` | Three real product clients, three context paths and three credential pairs; known ID/key/slug in the returned object. Select an exact high-level method if its contract fits. |
| Bitbucket paged project listing | Detect an SDK helper that traverses internally, drops the wrapper, or calculates the next offset. |
| One fixed SDK fallback for a documented route with no equivalent high-level method | Prove fallback is a supported named operation, not an arbitrary URL, and preserves output shape. |
| Jira search by semantic-read POST | Prove that method, product, JSON body, and response schema are retained and that arbitrary POST is not enabled. |
| One synthetic HTTP 401/403 and one recovered loopback connection failure | Prove runtime mapping, automatic retry and output framing without a live fault injection. |

In each batch: **unit first → installed CLI loopback**. Ask the owner for
live validation when a batch adds a product, an adapter/response kind, or
a required live scenario not yet represented. Repeat the live minimum on the
final artifact. Write a representative critical regression before the fix and
show that it fails for the intended behavior, then passes unchanged. If a
bug has no runnable original implementation, use a small controlled faulty
variant or an isolated negative-control fixture. Do not inject faults into
the shared candidate or the live server. For routine route additions, share
the harness; do not reproduce the whole boundary suite per route.

Exercise the pinned SDK on canonical paths. A fake SDK or the strict legacy
transport can help isolate a unit test but neither counts as canonical
end-to-end evidence. Verify the representative high-level and fallback calls
use that library and do not switch to a second transport after an error.

### If a failure is attributed to the upstream library

Run a minimal standalone test against `atlassian-python-api` directly,
without the AtlaWire wrapper or a mock of the library method in question.
Use sanitized fixtures and record the exact assertion, command and SDK,
Python and Atlassian server versions. Distinguish the original documented
failure from a transport/configuration error or an AtlaWire-only contract
mismatch. If there is a working alternative, verify it with a positive
control and also test the AtlaWire fallback separately. Follow the
[upstream reporting workflow](delivery-plan.md#upstream-bug-reports-and-feature-requests),
including the standalone test as a GitHub issue comment for a confirmed bug.
For a missing capability, record the docs/source evidence and expected
behavior instead of inventing a failing bug test.

## 3. Required scenarios and what each test must reject

### A. Agent discovers and uses the tool, without source

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Fresh install, no credentials: root help, product help, command `--help`, `--catalog`, `--describe` a known operation | All work offline and show the expected command, usable parameters/defaults and result kind. Catalog retains its existing command metadata and has one `operations` row per supported ID. Unknown describe ID emits `validation_error`, exit `2`, and does not echo the submitted value. Pair the installed test with in-process spies that fail on credential resolution or request dispatch; merely setting a missing credential path does not prove these were never attempted. |
| Use only installed help/JSON to run a documented example on a synthetic fixture | Launch the actual console from the wheel and execute the advertised argv, not a corrected hand-written call. Use the real loader with a synthetic saved file, not a monkeypatched resolver. Assert documented inputs/defaults, actual request and exact returned object. Wrong ordering, missing options, invalid quoting and help/runtime drift fail. |
| Agent distinguishes normal results from errors | Test JSON-only stdout and exact exit code for each new machine-facing **entry point**, not a separate error matrix per operation. Verify canonical read/describe success and use malformed args, missing config and HTTP failure to distinguish exits 0/2/1. Valid object, list, empty list, declared text and documented no-content success are distinguishable. Help/version, existing catalog success format and documented legacy behavior follow the delivery plan's explicit rules. A Python-only loopback case is not CLI evidence. |
| CLI and Python share one operation | Using the same installed wheel, run a canonical CLI command, `AtlaWire.call` with its registry ID, and the corresponding Python wrapper against one independent fixture. Compare the captured requests and success envelopes. Test one shared validation failure: equivalent error code and no requests. Do not port the full CLI matrix to Python. |
| Conflicting actions or framework-level parse failure | Invoke `--catalog --describe ID`, `--help --catalog`, `--describe ID --version`, and discovery plus a command, in both orders. Assert exactly one JSON `validation_error`, exit `2`, and no credential, log or network activity. Also check an unknown canonical option and a missing positional argument through the real CLI. Run valid command-level `--help`, one known legacy invocation and a literal flag-like argument as positive controls; raw argv scanning must not reject the value. |
| Discovery authority and metadata | Compare representative registry-backed operations to independent expectations for command path, argument rules, documented/server-chosen defaults, response kind, access conditions and pagination. Use a paged and a non-paged operation; the latter must not advertise a continuation. Help, `--catalog` and `--describe` must point to the same canonical invocation without replacing existing `commands` metadata. |

### B. One registered read really does what its description says

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Every required ID, with independent synthetic request and response fixture | Capture the real method, context-prefixed route, parsed query/body, matched synthetic bearer and request count. Assert a meaningful response shape and fixture identity, including at least one extra field where valid. Use full payload comparison on representative raw responses. A correct status on the wrong resource, or discarded fields/envelopes, fails. |
| Parameter boundaries | Cover a missing required argument, unknown argument, wrong type (including boolean as an integer), documented limits and enum members. For supported parameters, send Unicode, spaces, `+`, `&`, repeated names and an identifier/path that requires encoding. Check parsed query/body **and** the relevant exact wire spelling to catch double encoding and duplicate-key loss. Do not apply a restrictive generic key regex to a documented different identifier domain. |
| Page 1 advertises page 2 | Fixture returns `nextPageStart=19` after a request with `start=5, limit=2`; assert the client emits the first envelope intact and sends exactly one request on a healthy transport. Explicitly request page 2 from the advertised continuation, then assert `start=19`. Also cover Jira offset and Confluence metadata where those adapters paginate. Reject fetching page 2 automatically, deriving `7`, stripping the cursor, or calling a bare array exhaustive. |
| Response validation | A valid empty array is successful. A wrong object/array type, malformed late row required by the contract, login HTML for JSON, bad JSON, non-finite number, disallowed 206, unexpected 204 and missing mandatory field fail with exactly one error JSON and no partial success data. In the SDK-backed project lookup, an empty HTTP 200, a 200 with JSON `null`, and a 204 are three failures; a documented 204 for Bitbucket's default branch is a separate positive control and maps to `data:null`. Exercise the registered Python adapter as well as the canonical CLI, not only the legacy `read-operation` path. |
| Read limits, not just output truncation | Test the shared bounded reader at its limit and just over it. In installed SDK loopback cases, send more than the limit without `Content-Length` and hold the stream open until the CLI exits, with bounded cleanup. An oversized JSON success gives `invalid_response`, received status and no partial success; an oversized HTTP error keeps its status and returns `body_truncated:true` and `body_json:null`. A client that waits for EOF or reports a timeout fails these checks. Check compressed content against decoded bytes; test declared text when its first operation is added. |
| Positive binary and interrupted download | Start with the first required binary operation, not in the initial JSON slice. Use non-UTF-8 bytes and compare decoded bytes or an independent SHA-256. Test the documented cap on both sides of its boundary. For file output, interrupt after a prefix and check cleanup, no receipt, and no overwrite of an existing file. |

### C. Read-only and credentials: prove the point of refusal

| Scenario | Observable result and faulty implementation rejected |
| --- | --- |
| Unknown, mutating and excluded admin ID; unsupported method/route alias; wrong-product semantic POST; path escape or invalid context | Test before credential resolution and assert zero requests on both listeners. Assert the public interface does not expose a callable generic SDK `request()`; no actual write is needed to prove this. If legacy aliases are retained, test their restrictions too. Convert the old Confluence-through-Jira success case into one correct Confluence positive case and one wrong-product no-request case. |
| Same host with different product contexts and synthetic tokens | Use distinct tokens; a shared token fixture cannot detect a pairing mistake. Supply a valid loopback URL but omit the token in explicit environment mode: assert `credentials_error`, `status:null`, exit `2`, and zero requests. A malformed or rejected pair must not try another product or another credential source. Check unselected products continue to work. |
| Redirect from GET and semantic POST | A synthetic GET 302 and a POST-preserving redirect must fail. Check one request to the first server and zero to the redirected destination, including wrong-context redirects on the same host. A second server returning a well-shaped 200 must not turn the redirect into success. |
| Optional GET side effects | Verify the Jira issue read does not request activity-history updates. Verify listing transitions never invokes an actual transition. The first accepted request is inspected, not inferred from its response. |
| Credential handling and diagnostics | Supply synthetic credentials through configuration. Assert the tool does not print those stored values or auth headers in startup, CLI results generated by the tool, or logs. Test that local failure diagnostics contain stable codes, not a dump of the exception/request. Preserve ordinary upstream payloads and existing secrecy tests; a synthetic upstream success deliberately containing an echo is not a new release gate or a reason to scan every result. |
| Human setup, required for handoff but not for the first read slice | Synthetic browser, hidden terminal and private temp store. Verify the documented page/instructions; for unsupported enrollment assert `credentials_error`, exit `2`, and no browser launch or prompt. No clipboard read, token verified only against the selected URL. A `GetPassWarning` or non-interactive invocation stops before visible input. Failed validation, cancellation or failed write preserves the existing store; confirmed replacement changes only the selected pair. Instructions stay off stdout. If optional browser consent is implemented, test success, canceled callback, wrong state and no token output. |
| Authentication proof before enrollment writes | Use the documented authenticated probe for each product, not a public list. In particular, a valid Confluence HTTP 200 with `type:"anonymous"` must fail, leaving the old store byte-for-byte unchanged; a `known` identity with the required username is the positive control. The setup guide states that credential updates are single-writer; no concurrent enrollment harness is required. |

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
  One dropped pre-response connection and one 503 followed by 200 each
  produce success on the second attempt. For repeated 503s with no
  `Retry-After` and sufficient wait budget, assert exactly three total
  attempts, exit `1`, `status:503` and `code:"http_503"`, not `transport_error`.
  Test 429 followed by success within budget. A 429 with `Retry-After: 90`
  must return `status:429` and `code:"http_429"` after one request with no
  sleep. Also check the cumulative budget with two individual delays that
  would each fit but do not fit together. With a fixed UTC clock, check a
  future HTTP-date, a past date (zero), and invalid or missing headers
  (1 s then 2 s); no additional jitter. When a 503 delay exceeds budget,
  keep 503 rather than recategorizing it as 429. Connection/read time is
  not charged to the scheduled-wait budget. A controlled clock/sleeper
  checks delays; real loopback checks the installed transport's attempts. Do not
  depend on wall-clock sleeps or trigger throttling on the real service.
- Prove no retries for non-retryable HTTP, redirects, invalid data, permanent
  TLS/configuration failures, and semantic POSTs in the first slice. If a
  retryable HTTP error is followed by a final transport failure, assert
  `status:null`, not the stale earlier HTTP status. Separate the healthy
  single-page request-count test from retry cases. After all paths assert
  that production code closes the response/session **before** fixture
  cleanup. A closed test server by itself is not that evidence.
- Run the CLI against a private scratch log directory with a small test
  rotation threshold, then induce a log-write failure. Check both active and
  rotated logs for safe event fields and absence of sensitive fields. Two
  concurrent CLI processes must not create unbounded backups or alter the
  stdout result because rotation is contended. Do not require lossless audit
  logging: a bounded best-effort diagnostic log may skip an event.

### E. Additive workflows and BBK comparison

Start from the required read-only Atlassian BBK workflow list in the release
evidence. Match every required workflow to a check, including the PR review
packet where required; the existing five comparisons are a starting point,
not the denominator. Use fixtures with a known issue key, page ID, PR ID or pinned repository
commit. Assert exact results or a justified projection, not just that a result
exists. Compare stable BBK observations and expected AtlaWire improvements,
not the current search ranking of unrelated live datasets. Test a partial
failure, all requested products failed, unsupported Bitbucket Search,
pagination/limits vs true errors, ref pinning and documented diff truncation.
An empty result must not hide an unsupported or failed product. For the first
workflow with a total read cap, use multiple products or terms, a small row
limit and a fixture requiring more reads than allowed. Assert the actual
number of reads on healthy transport, retained results and a distinct
budget-exhausted outcome, not an empty result or HTTP error.

## 4. Prove the critical tests can fail

`%testscope-39`: For each applicable **shared** boundary in the table, keep a
runnable regression and record the node ID and assertion that detects the
fault; do not repeat mutation checks for each operation. Prefer the known
pre-fix failure. If it is unavailable, use a fixture-based negative control
for a boundary the fixture can actually exercise, or ask the owner to approve
the exact project-local isolated candidate directory for a controlled faulty
variant. Never change production in the shared working tree for this check.
Keep the faulty variant out of the delivered tree; retain only the regression
and sanitized receipt, which identifies the candidate, the fault and observed
assertion. Run the same test against the correction. A passing positive
fixture alone is not sensitivity evidence; there is no mutation-score target.

| Plausible defect | Decisive check, not a proxy |
| --- | --- |
| Catalog description uses the wrong option or advertises a second canonical command | Run the actual argv from `--describe` on the wheel and assert exact wire query/body and fixture identity. Check the canonical IDs against the required inventory rather than comparing two lists from the same dispatcher. |
| CLI accepts an invalid argument or missing credentials by falling through to Click's text error | Assert exactly one strict JSON document, expected error code, nullable status and correct exit. The JSON checker must reject non-finite values; default `json.loads` alone accepts them. No credential/network work on a local validation failure. |
| The client skips an unexpected row, drops cursor metadata, or silently walks the next page | Address the late bad row and a distinct healthy two-page fixture. Compare the complete first payload and captured requests, then the requested second payload. A server over-returning the user page is rejected where that is the compatibility contract. |
| A valid nonempty success comes from the wrong resource/product | Use distinct context prefixes, distinct credentials and a marker valid only for the expected resource. Inspect the request and fixture ID; an HTTP 200 and a well-shaped response are insufficient. |
| A rejected method or redirect reaches the network, then fails later | On a positive control the approved listener sees the expected request; on a rejected operation neither listener is called. On a refused redirect assert exactly one request to the origin and zero to the other destination. |
| SDK retries and a wrapper also retries, or it treats the retry count as additional attempts | Exhaust a queue of retryable failures and assert the exact three total attempts. Vary delay to show the cumulative limit: a first `Retry-After` of 3 seconds and a second of 3 exceed 5 even though each alone fits. Use a controlled sleeper, not elapsed wall time. |
| AtlaWire prints a credential from configuration, an auth header or raw diagnostics | Configure a synthetic credential and exercise normal use and local/auth failure. Check stdout, stderr and logs for direct publication by AtlaWire; assert the documented result and error still arrive. Do not introduce broad scanning of results to pass this check. |
| Hidden input degrades to visible input, or saving a new pair erases the old pair on failure | Drive `GetPassWarning` with a visible-input trap. Inject a save failure after verification and before replacing the saved file; assert previous bytes, including other products, are unchanged, no temp file remains, and the result is not success. Also prove a confirmed save succeeds. |
| Binary read publishes a receipt or temporary contents after interruption | Interrupt after a nonempty byte prefix. Assert no success receipt and no file at the destination; when the destination already exists, assert its original bytes remain. Pair with known-byte success. |
| Federated results turn an unsupported or broken product into “no matches” | Fixture gives one success and one failure/unsupported source. Assert per-product status, surviving data and incomplete result. Separate all-failed case must have a top-level error; a next page without a failure must not be labeled a transport error. |

If an applied fault is not detected, fix the test and repeat the pair.
If permission to run an isolated faulty variant is unavailable and there is
no useful pre-fix run, mark sensitivity **INCONCLUSIVE**. For read-only
enforcement, credential secrecy, and replacement of stored credentials,
missing decisive sensitivity evidence is a handoff blocker, not an
invitation to run tests against a live destructive path.

## 5. Release gates and handoff

1. **Focused green.** From `D:/REPO/github/AtlaWire` in the isolated offline
   environment run:
   ```text
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_jira_reference_unit.py tests/test_jira_reference_cli_e2e.py
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_sdk_unit.py tests/test_sdk_e2e.py tests/test_sdk_cli_e2e.py tests/test_facade_unit.py tests/test_facade_cli_e2e.py tests/test_catalog_unit.py
   ```
   Include the new installed-CLI test selection for the slice. Run affected
   compatibility tests with each batch. These commands are not the release
   suite and do not prove the current new CLI path by themselves.
2. **Full offline green and coverage reconciliation.** Run
   `C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests` plus
   project lint/types and the applicable dependency audit. Give pytest a
   unique project-local `--basetemp` if used. Report tool failures instead of
   suppressing them. Reconcile the required inventory against advertised IDs
   and independently verified test cases. **Pass threshold:** every required
   ID is implemented, advertised and passes its installed-CLI loopback case.
   No unresolved in-scope classification, unexpected skip, or unsupported
   required operation counts as done. Exclusions and additive reads are
   reported separately.
3. **Clean wheel proof.** Run `uv lock --check` without regenerating the lock
   as part of the check. Confirm the lock includes the same SDK pin as the
   project metadata. Build a versioned wheel with approved Python 3.15 tooling.
   Run the release-equivalent
   checks on one final wheel hash; if it changes, rerun its bound checks.
   In an approved isolated
   install target outside the checkout, prove exact wheel hash, package
   metadata, imported module location and console launcher. Run section A
   there plus the slice from section 2 over actual loopback transport.
   A passing editable install or `CliRunner` alone is not this evidence.
4. **Real-server proof (`%gates-37`).** The owner runs the updated fixture-scoped live
   read-only runner for the same installed artifact using the saved
   credentials. Record the observed server versions and a sanitized outcome
   per run. Before the run, name the representative IDs and expected
   shapes/identities. **Pass threshold:** cover each product, plus materially
   different product-specific adapter or response paths, including a real
   page continuation, semantic POST and binary where applicable. Reuse one
   example for several categories when it proves them; no Cartesian product.
   Evidence for one product or deployed version does not stand in for a
   different product-specific path or another version. Run successful BBK
   comparisons for required workflows. The deployment owner also confirms the
   advertised enrollment method is usable on each deployment claimed for new users; no
   requirement to mint or revoke a live token in automated checks.
   No live failure injection or review of real fixture values or tokens.
   Other individual reads need not each run live if they pass offline and
   their live path is represented. Mark each unrun ID as such; the owner
   accepts that disclosed residual risk. Missing a required representative
   check is **INCONCLUSIVE** and blocks release; never count it as a pass.
5. **Review before handoff.** Implementer self-reviews code **and tests**
   against the original requirements and attaches the evidence above. The
   receipt lists `requirement | test node/command | faulty behavior |
   observed faulty and corrected outcomes | remaining limitation` for each
   critical check. A clean table without the actual failed/pass run and its
   candidate identity is not an executable verification receipt.
   Return the exact candidate and test receipt to the reviewer. The fresh
   review challenges both the tests and implementation; separately
   authorized independent execution uses an isolated copy of that candidate.
   Unsupported required scope, missing decisive live evidence, failed
   checks or unresolved safety findings block release; report a review
   candidate instead. BBK retirement remains a separate owner decision.

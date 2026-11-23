# AtlaWire delivery test plan

Companion to [the delivery plan](delivery-plan.md). These
are instructions for the implementer, not a test result.

**Target:** An agent who has only the installed command can learn it, execute
supported reads without handling secrets, and distinguish a valid result, an
empty result, another page, and a failure. The final artifact covers all
required operations in the agreed versioned inventory, with additive
workflows kept separate.

Use [the execution order](delivery-plan.md#execution-order) for the next
implementation slice and [the full functional matrix](#6-full-functional-matrix)
to reconcile every exposed workflow. This plan covers the final tool, not just
the new SDK adapter. Existing tests count if they prove the listed contract
against a known candidate; do not recreate them to complete the matrix.

## 1. Lock the candidate and the evidence

1. Record the commit and tracked **and untracked** candidate changes. Install
   and test that candidate, not a different edit, a stale console launcher, or
   clean `HEAD` without the changes. Do not run a release gate while workers
   still edit that candidate.
2. Use CPython 3.15 and record the interpreter, installed library version,
   resolved package location and console launcher. Use a synthetic home,
   explicit synthetic BBK credential path, loopback or dummy endpoints and a
   deliberately selected environment for **all** offline commands. Include
   subprocesses, manual probes and delegated work. Set and verify that
   environment **before invoking the real CLI**, even for input expected to be
   rejected before credentials. Use the underlying callable with an I/O trap
   for ad hoc validation if the CLI cannot be isolated yet. Do not assume
   passing mock tests prove egress restrictions. Use no real credential files,
   inherited product values, proxy/netrc state, or non-loopback test targets
   offline. A live request during an offline run is an isolation failure;
   stop, disclose it, and discard that run as release evidence.
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

### Windows execution profile: no project virtual environment

Use `C:/Python315/python.exe` and the libraries already visible to that
interpreter, including its user site. Run pytest, Ruff and Pyright with that
interpreter's `-m` entry points. Check `sys.prefix == sys.base_prefix` and
verify the exact `atlawire` launcher used by child processes. Do not activate
or create a project `.venv`, or use `uv run` or `uv sync`. Keep `uv.lock` for
dependency version evidence; checking the lock does not require syncing an
environment.

The owner has already removed `.venv`; do not repeat cleanup. Hatchling
1.33.0 is available in the Python 3.15 user site. The existing `pyproject.toml`
built `atlawire-0.1.0.dev0-py3-none-any.whl` offline and the archive's launcher
metadata and packaged manifest were checked. This was a **build check**,
not proof that the final CLI was installed or exercised from that wheel.
Use the same base interpreter and a separate approved install target for
the clean-wheel gate; do not change the existing installation to run it.

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
- Existing in-process SDK loopback cases are useful but not installed
  behavior. Add installed CLI controls for retry recovery and early
  oversized-body rejection, once per shared path rather than per route.
  Release the held-open handler in `finally` before server shutdown, and
  use a bounded child timeout that covers the chosen fixture. Teardown
  timeout or a handler error does not count as detecting a client defect.
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

1. **Focused green.** Start with [audit slice A](audit-follow-up.md#work-order-for-the-implementer):
   both file-output paths must preserve a destination created during
   publication and emit no receipt. Run this regression before changing
   production and unchanged after the fix, along with
   `tests/test_binary_read_cli_e2e.py` and `tests/test_bitbucket_attachment_cli_e2e.py`.
   Keep the known gzip failure named separately until its own repair; do not
   hide it or require unrelated fixes before committing the publish change.
   For the broader slice, from `D:/REPO/github/AtlaWire` in the isolated offline
   environment run:
   ```text
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_jira_reference_unit.py tests/test_jira_reference_cli_e2e.py
   C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests/test_sdk_unit.py tests/test_sdk_e2e.py tests/test_sdk_cli_e2e.py tests/test_facade_unit.py tests/test_facade_cli_e2e.py tests/test_catalog_unit.py
   ```
   Include the new installed-CLI test selection for the slice. Run affected
   compatibility tests with each batch. These commands are not the release
   suite and do not prove the current new CLI path by themselves.
2. **Full offline green and coverage reconciliation.** Run
   `C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q --basetemp=.planning/<new-run>/pytest tests`
   (replace `<new-run>` with a unique run directory whose parent exists).
   Selecting `tests` explicitly separates offline tests from opt-in `checks`.
   Run Ruff and Pyright scoped to the project; run the applicable dependency
   audit with its network access approved. Report failures instead of
   suppressing them. Reconcile the full functional matrix and the required
   inventory against advertised IDs and independently verified test cases.
   Run the full source suite with CLI children pinned to the candidate. That
   is the integrated code gate; it does not replace installed-wheel evidence.
   No unresolved in-scope classification, unexpected skip, or unsupported
   required operation counts as done. Report exclusions separately.
3. **Clean wheel proof.** Run `uv lock --check` without regenerating the lock
   as part of the check. Confirm the lock includes the same SDK pin as the
   project metadata. Build a versioned wheel with the installed backend:
   ```text
   C:/Python315/python.exe -B -m pip --isolated wheel --no-index --no-deps --no-build-isolation --wheel-dir <new-ignored-output-dir> .
   ```
   Use one wheel hash for release-equivalent checks; if it changes, rerun the
   checks bound to it. Install into an approved isolated target; run from
   outside the checkout. Before cases run, verify the actual CLI child and
   Python import resolve to that target rather than the editable install.
   `tests/_loopback.py` currently finds the launcher on `PATH` and inherits
   the parent environment; the source suite also adds `src` to its Python
   path. Pin the target explicitly, fail the gate if the launcher is missing,
   disable source injection, and pass only the approved OS/import settings
   plus synthetic fixture values to offline children. Reuse existing helpers
   rather than rewrite each test. Do not infer wheel identity from parent
   `sys.executable`, a matching version or `CliRunner`.
   **Review-candidate gate:** run section A and the section 2 slice.
   **Final gate:** also run each required ID's installed-loopback fixture and
   the shipped workflows at their real entry points; don't repeat every
   source-only unit test on the wheel.
4. **Real-server proof (`%gates-37`).** The owner runs the updated fixture-scoped live
   read-only runner for the same installed artifact using the saved
   credentials. Record the observed server versions and a sanitized outcome
   per run. The current nine-check runner is a baseline, not final
   evidence: its fixed module launch can select the editable install and
   it does not exercise all canonical paths. Prepare the final fixture list
   and prove the exact artifact launch **offline** before supplying real
   credentials. Keep the allowlist; use a fixed, verified artifact target,
   not an arbitrary executable or inherited `PYTHONPATH`. Before the run,
   name the representative IDs and expected
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

## 6. Full functional matrix

Freeze **three lists**, not one percentage: (1) required standard reads from
versioned references; (2) public CLI commands, Python entry points and retained
aliases from the installed artifact; (3) required BBK workflows, including
meaningful flags and library-only reads. Assign each item a matrix row, one
evidence owner and a disposition. Adding a CLI alias does not add another
standard read; an SDK method does not establish a supported route. Do not count
helpers as user-facing features, but test them through the workflows they serve.

The REST denominator is still open. Before implementing the product batches,
the integrator commits the versioned reference-based inventory alongside these
plans and asks the owner to resolve exclusions or unknown classifications.
Do not derive this file from the runtime manifest or observed CLI tree. For
each REST row, record `product + exact source/version | method + route |
required/excluded/unresolved + reason | operation ID | required/optional
inputs | success statuses, shape and continuation | advertised | adapter |
offline installed test | live status`. A runtime row is not a passing adapter
test. Keep independent fixtures small but sufficient to catch wrong resources,
discarded fields or invalid shape. For each workflow, record
`entry point/flags | fixture | expected output | failure/boundary | test node |
artifact/result`. Extend [the provisional BBK table](bbk-parity.md) with
its own workflow IDs and final-wheel comparison receipts. Do not substitute
CLI name matches, REST cases, or the five historical smoke comparisons.

Record offline and clean-wheel results as **pass / failed / not exercised /
not applicable**. For live REST proof distinguish **direct pass on this
wheel**, **not run directly; named representative path passed and residual
risk accepted by owner**, and **failed/inconclusive**. Link the direct or
representative receipt; an old receipt or another product's result does
not qualify. BBK workflows have their own direct comparison status. Explain
every exclusion; do not use “not applicable” for untested required scope.
Reconcile both directions: every required row has the prescribed evidence,
and every advertised row and retained alias has a documented contract.

This matrix was checked against all 65 current top-level commands and reviewed
for evidence gaps by DeepSeek Flash (`ses_df9f2ebb6ffeTR1Qao5D65wHqU`).
That is a plan check, not an executed functional pass or a frozen inventory.

| Area and existing functionality | What the full verification must demonstrate |
| --- | --- |
| **Installation and discovery (R1/R6):** console and `python -m atlawire`, version, root/product/command help, `--catalog`, `--describe`, `operations` | Test offline with no credentials and two different working directories. The final wheel includes its required resources; module location and launcher belong to that wheel, not the checkout or a different user-site install. One canonical command per required ID, executable argv from `--describe`, explicit page and failure semantics, no secret defaults, and correct invalid/conflicting-action exits. Use `tests/test_entrypoints.py`, `test_catalog_unit.py` and `test_read_slice_cli_e2e.py` as starting points. |
| **Canonical and compatibility APIs (R1/R2):** `read`, `read-operation`, `api-get`, `api-request`, documented Python calls/wrappers | Cover one exact wire fixture per registered required ID; one matching CLI/Python case on the wheel; one case per retained compatibility contract. Test the fixed allowlist, no cause-based switch to another transport, validation and expected outputs. Reject raw session/dispatch exposure and a wrong product or excluded route without sending any request. Reuse `test_operations*`, `test_read_slice*`, `test_sdk*`, `test_semantic_post_cli_e2e.py` and `test_manifest_unit.py`; a manifest self-comparison is not external evidence. |
| **Owner setup and credentials (R3/R4):** saved/provider, env-only, explicit URL matching, `auth login` where the deployment is supported | Test distinct pairs for products even on one host, context path and explicit override, missing/invalid/partial config, and refusal before request. A valid environment-only pair works without `--base-url`. Ordinary reads never prompt. Exercise hidden input, browser fallback, unsupported enrollment, cancellation, failed authenticated probe, protected store update and retained other entries. Verify read-only behavior without issuing a write. |
| **Jira discovery and search (R2/R5):** `jira-me`, `jira-projects`, `jira-users`, `jira-issue-types`, `jira-priorities`, `jira-resolutions`, `jira-status-categories`, `statuses`, `jql`, `mine`, `jira-author-comments` | Check known identity and reference IDs, permission-dependent fields, JQL/filter/author behavior, ambiguous identities, empty/limited/page continuation and partial errors. Inspect exact flags and filters, not only nonempty output. Reuse `test_jira_reference*`, `test_jira_mine_statuses_e2e.py`, `test_jql_e2e.py` and `test_jira_comments_search*`. |
| **Jira issue and metadata (R2/R5):** `issue`, `issue-comments`, `issue-changelog`, `issue-worklogs`, `issue-remote-links`, `transitions`, `jira-create-meta`, `jira-edit-meta`, `jira-transition-fields` | Check issue key/URL and projection, history/comment/worklog bounds, opaque transition IDs, late malformed metadata, no write or activity-history action, and JSON/Markdown/wiki behavior. Exercise required attachment download via the binary path; do not mistake attachment metadata for content. Reuse `test_jira_issue_extra*`, `test_jira_metadata*`, `test_jira_markdown*` and `test_jira_wiki*`. |
| **Confluence (R2/R5):** `spaces`, `cql`, `children`, `page`, `page-attachments`, `page-comments`, `page-labels`, `page-history`, `page-version`, `page-url`, `convert-body` | Prove expansion and paging, current vs exact historical version, links checked against the configured origin without automatic traversal, Storage/HTML conversion and safe rendered Markdown. Verify historical content, stable attachment metadata and documented content reads as distinct workflows. Use `test_confluence*`, `test_children_e2e.py`, `test_cql_e2e.py` and `test_page_storage_cli_e2e.py`. |
| **Bitbucket repository/reference reads (R2/R5):** `projects`, `repos`, `find-repos`, `file`, `files`, `ls`, `blame`, `branch`, `branches`, `tags`, `tag`, `last-modified`, `commit`, `commits`, `commit-changes`, `commit-diff`, `attachment-get`; documented raw/archive routes | Test exact repo/path/ref, encoded path segments, content bytes, stable IDs, object shapes, arbitrary next-page cursor and cap. Distinguish default branch vs missing branch and terminal vs capped pages. Bad cursor must be reached before the cap to prove rejection; exact-cap is a distinct success. Reuse `test_bitbucket*`, `test_branches_commits_e2e.py`, `test_files_cli_e2e.py`, `test_commit_*`, `test_blame_e2e.py`, and binary tests. |
| **Bitbucket PR and search workflows (R2/R5):** `pr` (show, files, comments, commits, diff, file), `prs`, `my-prs`, `pr-merge-status`, `pr-diff-complete`, `pr-review`, `search`, `grep-repo`, `scan-extension` | Trace known PR/files/commit identifiers and pinned refs end to end. Test whole-diff truncation, per-file fallback and its own failure, role/status filters, no hidden workspace clone, regex/case/path and listing-only behavior, plugin absence vs no matches, capped work and stable match evidence. Reuse `test_pull_request*`, `test_pr_review*`, `test_repo_grep*`, `test_repo_scan*` and `test_search*`. |
| **Cross-product workflows (R5):** `find`, `whoami`, `selftest` | Match each product's health/results to its own configured pair. Test missing pair without blocking others, failed and successful terms for every product, an empty-but-successful term, all attempts failed, malformed later page, duplicate merge and total logical-read budget including extra pages. Keep earlier successful terms, not rows from a failed per-term page sequence. `selftest` has the documented `whoami` behavior. Reuse `test_federated*`, `test_whoami_cli_e2e.py` and `test_bbk_live_parity_contract.py`. |
| **Transport, retries and file publication (R2/R3):** JSON, text, no-content, binary, HTTP error and diagnostic paths | Check distinct `200`/documented `204`/unsolicited `206`, redirect refusal, interrupted framed body and truncated gzip, finite/nonfinite numbers, exact/over size, HTTP/transport error framing, no post-response retry, and no TLS verification retry. Drive the file collision after the existence check, assert original bytes, no receipt, and no owned staging file. Cover received-vs-absent HTTP status. Reuse `test_sdk_transport_e2e.py`, `test_binary_read_cli_e2e.py`, `test_bitbucket_attachment_cli_e2e.py` and the targeted cases in [audit follow-up](audit-follow-up.md). |
| **Output and diagnostics (R1/R3/R4):** raw JSON, text, Markdown, TSV, base64, file receipt and logs | JSON preserves ordinary data and is strict (independent finite-number check); compare renderer-visible text and inert markup rather than brittle substrings. Test Unicode, controls/bidi, error redaction from tool-owned sources, exact bytes, rotation/contended or failed log writes, and no change to the primary result when diagnostics fail. Reuse `test_bidi_output_e2e.py`, `test_output_sanitization.py`, `test_transformed_output_guard_cli_e2e.py` and the existing credential-disclosure regressions. |

Run one **agent task walk-through** without source access from a clean wheel:
learn syntax with help/catalog; find a known issue, page and repository by
search or `find`; retrieve the exact issue, page revision and pinned PR or
file; ask for a second documented page; explain an empty result and a
controlled failure; download the known binary and verify its receipt. Fixtures
can share a scenario across rows but must carry distinct identities and product
contexts so a wrong-source result fails. This complements per-ID tests; it
does not replace them. Confirm the owner setup path separately.

### Test depth, execution order and reporting

1. **Per commit:** run just the behavior-specific node(s) and affected suites
   on the checked implementation. On critical bugs, keep the same regression
   between the failing and passing runs. Use the frozen contract to adjudicate
   test-only defects. For an argv NUL Windows cannot launch, test the callable
   and keep a launchable CLI negative control; do not call an OS launch failure
   a successful validation test.
2. **Integrated offline gate:** use the full command in section 5. Enforce
   app and child isolation while passing required non-secret Windows runtime
   settings and the intended Python user site. A subprocess check needs the
   intended launcher, not just a module import. Verify live-runner allowlist
   accept/reject behavior offline; its mocks prove runner behavior, not server
   behavior. Record executed tests and skips separately.
3. **Coverage and test quality:** measure full **branch** coverage of
   `atlawire`, with subprocess data combined and the source mapped to the
   tested build. Verify a known child's execution is actually represented
   (for example, the module entry point). Check specifically file publication,
   SDK error handling, credential pairing, cross-product partial paths and
   pagination. Missing coverage identifies an investigation, not an automatic
   production defect. Use section 4's behavioral sensitivity checks; do not
   add cosmetic tests or invent a percentage floor.
4. **Wheel then real servers:** run the installed-agent scenario and required
   route/workflow matrix on the exact wheel using synthetic settings first.
   Record one artifact hash for offline and owner-run live evidence. Run
   representative live checks per product and materially different
   response/adapter path, including paging, semantic reads, media and the
   required BBK comparisons. Do not run synthetic faults against a live
   installation. Produce a small sanitized receipt for each gate; record any
   missing access/version/fixture as inconclusive and stop release sign-off.

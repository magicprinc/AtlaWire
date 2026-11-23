# AtlaWire audit follow-up and repair handoff

**Baseline:** `16b739a`, `D:/REPO/github/AtlaWire`, Windows, Python 3.15.2,
`atlassian-python-api` 5.0.5, Requests 2.34.2, urllib3 2.8.0. This tool serves
shell users and agents making read-only calls to self-hosted Jira, Confluence,
and Bitbucket. This is a review of the previous audit, not a new whole-repository
audit or a replacement for [the approved delivery plan](delivery-plan.md).
The working tree already had untracked `pytest-audit-cov/` and
`pytest-audit-full/`; do not stage, inspect their contents, or delete them here.

**Feedback for the original reviewer:** Distinguish a red test from a product
defect, a registered route from a supported operation, and an editable install
from a wheel test. A duplicate helper is not the file-output problem: both can
overwrite a file the user explicitly asked us to preserve. Lead with a
counterexample and a small fix; do not turn the headings of the old review into
one refactor.

## Correct the previous review

| Old conclusion | Verified correction |
| --- | --- |
| “13 failures, eight real bugs” | The prior aggregate is reported, not freshly measured. A fresh targeted run gave **165 passed, 10 failed**. Three failures in that run are demonstrably test-side; other cases need the distinctions below. Do not infer a defect count from the failure count. |
| Three runner/batch failures are environmental | The focused Flash run reproduced three: two child-environment defects and one real **live-check validator bug**. The runner's `jira-create-meta` guard expects four arguments, but the check itself sends three (`checks/test_live_read_batch.py:320–325,1199`). It rejects a valid read before execution. The Windows version child omits `SystemRoot` (`tests/test_live_read_only_runner.py:655–674`); the nested pytest child drops the selected user site when replacing the profile (`tests/test_live_read_batch_contract.py:960–1000`). Do not weaken the runner's allowlist. |
| `tags` and `last-modified` return the wrong exit code | In `tags`, page two reaches the requested cap, so `bitbucket.py:2301–2303,2344–2348` deliberately does not need the cursor. Change the malformed fixture to leave one row still needed and have a positive exact-cap control (`tests/test_bitbucket_extra_cli_e2e.py:307,384`). The NUL case never reaches `last-modified`: Windows `CreateProcess` rejects the argv. Exercise NUL through the callable with a no-request assertion and keep installed E2E cases for controls the OS can pass. |
| Empty Jira transition ID and active wiki HTML/links are production bugs | `jira_metadata.py:162–163` already rejects the empty ID; `"" not in message` can never be true. The HTML test requires `\<img` then forbids its `<img` substring; test inertness, not the substring. The link snapshot fails on an extra escape in a non-link; no active unsafe link was shown. Keep the active-link/HTML guarantees. Check the two real output differences (a literal separator between inline code spans and prose indentation) against the documented rendering behavior before editing the converter. |
| Two malformed late Jira rows are accepted | Reproduced. The rows are objects with **numeric IDs**, not non-objects (`tests/test_jira_metadata_unit.py:515,755`). The validators check only outer type and optional `fields` (`jira_metadata.py:202–217`). Verify the pinned Jira schemas and existing compatibility cases, then check the documented ID type locally. Do not require unrelated keys or tighten opaque string input to numeric-only. |
| `find` must keep rows from page one of a failed page sequence | `tests/test_federated_cli_e2e.py:416` protects the opposite boundary for a failed product/term. Keep successful *other* product/term results and report the failed sequence. Do not publish partial pages from it unless the owner changes that contract. The actual release gaps are below. |
| 162 operations do not accept query; all routes are functionally covered | The registry reports **202** entries (152 generic JSON, 36 object, 7 array, 7 binary), **180 with no declared query fields**, and **3** IDs in the canonical catalog. `query:[]` is already visible in `--describe`; it does not distinguish “documented none” from “not implemented”. This is not a count of missing fields or a verified REST denominator. Generic JSON accepts an arbitrary finite shape, including an error-looking object, but some legitimate payloads are generic too. Do not add a global `errorMessages` heuristic; enforce each documented shape where known. |
| `facade.py` is dead; remove it or just export it | It is a tested prototype and a directly importable module. The approved target is **one** Python/CLI dispatcher and the documented `AtlaWire.call`; exporting the existing class unchanged would publish its second registry (`facade.py:201,446`). Do not delete it or bless it as canonical as an audit fix. |
| `read-operation` missing POST, and two transports, are themselves bugs | `read-operation` explicitly promises fixed GET, raw legacy JSON (`cli.py:719–725`); approved compatibility behavior can differ. Keep the command and its tests. Only one replacement should be advertised as canonical. Do not migrate legacy readers or merge response envelopes as cleanup. |
| Manifest is stale; catalog tests are all circular; module entry point is untested | Local regeneration matched `manifest.json` **byte-for-byte**. The generator reads **zero tracked inputs** in its `.planning/` source directory, so a clean checkout cannot establish freshness from those files. Manifest tests prove projection/wiring, not coverage against versioned API docs, and exercise the legacy mocked transport (`tests/test_manifest_unit.py:99–110,113–157`). Catalog tests include independent fixtures (`tests/test_catalog_unit.py:43–88,112–140,177–196`). `tests/test_entrypoints.py:17–49` really runs `python -m atlawire` for help/version; 0% in a selection without these tests is not a gap. |
| 24% coverage and no facade data indicate broad test weaknesses | The selected SDK tests cannot measure repository coverage. A file path passed to `--cov`, or subprocess coverage not collected, is a measurement problem, not a product defect. PATH-based tests can use a different installed copy (`tests/_loopback.py:90–104`). Tie coverage, subprocesses and CLI import location to a known build before ranking gaps. Ruff/Pyright counts are prior observations; no tracked `.github` workflow was seen, which does not establish the absence of external CI. |

## Findings the previous review missed or under-ranked

1. **%binary-publish-1 — data loss, reproduced.** `attachment-get --out` and
   canonical `read --out` check `exists`, then call an overwriting `os.replace`
   (`cli.py:1682–1701`, `sdk.py:386–446`). A writer placing a file at the target
   during publication loses it; both commands can return a receipt. Both use a
   predictable nonexclusive staging name. Current tests precreate the final
   path; the legacy cleanup assertion also looks for `.part` without the PID,
   so a leaked actual staging file would pass
   (`test_binary_read_cli_e2e.py:73–95`, `test_bitbucket_attachment_cli_e2e.py:892–905`).
   Prefer one small shared local publication primitive: exclusively create an
   owned sibling temp, then publish **without replacement**. Evaluate a standard
   library hard-link publish on supported filesystems, or another verified
   no-replace primitive. Unsupported publication must fail safely; no
   check-plus-replace fallback. Keep read transports and receipt shapes separate.

2. **%binary-integrity-1 — false success, reproduced.** The SDK binary path
   accepts `206` as a complete file (`sdk.py:405–447`). The CLI returned exit 0,
   the partial bytes and a success receipt to a local `206` fixture; JSON
   already rejects it (`sdk.py:628–638`). Honor each operation's declared
   success status; cover unapproved `206` and `204` and a valid 200. Separately,
   `attachment-get` accepted a gzip member without its trailer despite a
   matching HTTP `Content-Length` (fresh installed-CLI test). A standalone
   loopback using the locked Requests/urllib3 stack, without AtlaWire, also
   accepted that same type of truncation; the standard library decoder
   rejected it. Before attributing the exact upstream cause, isolate the
   dependency layer. Prefer a standard decoder or verified library option,
   preserve decoded-size limits and valid compressed/identity responses, and
   do not change every legacy reader.

3. **%sdk-errors-1 — broken machine output, reproduced.** Both canonical JSON
   and binary reads lose the JSON error envelope when a loopback peer closes
   early after sending part of a declared body. `iter_content` raises
   `ChunkedEncodingError` outside the existing handling (`sdk.py:529–535,
   640–654,697–706`, `sdk.py:426–453`); no binary file is published, but an
   uncaught exception reaches Click. The SDK JSON decoder also lets standard
   numeric syntax `1e999` become `Infinity` in a success envelope
   (`sdk.py:151–157`, `cli.py:993`). Use one small error mapping at the SDK
   read boundary; preserve known status, sanitize diagnostics and never retry
   after a partial body. Check finite numbers at decode time so failure still
   has the response status. Two nearby retry cases need focused tests:
   a non-ASCII digit in `Retry-After` raises `ValueError` in `_retry_after`;
   certificate errors are a `ConnectionError` subclass and enter the retry
   branch instead of stopping (`sdk.py:502–517,731–744`). No new retry layer.

4. **%read-boundary-1 — read-only API breach, reproduced without a write.**
   `client_for` is a public export documented in the README. Its name filter
   forwards the raw authenticated session (`__init__.py:3–12`,
   `sdk.py:203–249`), and `tests/test_sdk_unit.py:70–74` explicitly asserts
   exposure rather than checking closure. An exported “read-only” client must
   not hand out the raw transport. Before changing that public surface,
   inventory real consumers and agree on a migration to fixed, declared reads;
   do not keep extending the denylist or just hide one attribute while still
   forwarding arbitrary SDK attributes. Verify locally with synthetic
   credentials and a no-request oracle. No write probe is needed or authorized.

5. **%find-partial-1 — false total failure and unavailable-target failure,
   reproduced.** `len(errors) == 3` means each product had *some* failure, not
   that no product/term succeeded. A controlled run with a failed and an
   empty-but-successful term per product raised total failure
   (`federated.py:190–208,225–247`). The CLI also aborts before contacting any
   healthy product when another pair is absent (`cli.py:388–407,658–669`;
   `federated.py:183–187,465–479`). Keep the output shape for this repair;
   record at least one completed product/term separately from presence of rows,
   record unavailable products distinctly, and preserve same-product credential
   pairing. Keep caller-wide input validation before any network. Bound total
   logical reads, including extra pages, in the composite as the approved plan
   requires (`delivery-plan.md:510–540`); no scheduler. `complete:true` must
   not claim exhaustiveness beyond the known per-term results.

6. **%cli-contract-1 — canonical usage can fail before any useful call,
   reproduced.** `read --token-from-env` with a valid matching
   `ATLAWIRE_<PRODUCT>_URL/TOKEN` pair but no explicit `--base-url` returns
   `credentials_error`, no request: `read` never loads the product URL before
   passing it to the resolver (`cli.py:370–376,784–789,899–902`; compare
   `read-operation` at 729–736). Discovery actions eagerly exit and mask
   conflicts; both flag orderings returned success with different documents
   (`cli.py:230–301`). Missing required canonical options produce text instead
   of JSON. Canonical validation is also split: names are validated before
   credentials, some typed values and output requirements after them
   (`cli.py:840–929`, `operations.py:1918–1921`). Reuse the registry's
   validation and the existing JSON boundary; check no credential access on
   invalid input. Do not raw-scan argv: a flag-looking value is not an action.

7. **%coverage-contract-1 — release evidence remains incomplete.** The approved
   grouped CLI, shared Python dispatcher, documented pagination and `auth login`
   are not delivered by the current canonical slice (`delivery-plan.md:53–109,
   141–189,413–419`; `operations.py:1680–1796`). `read` should not silently
   ignore `--out` on JSON. Binary input/response options, documented query
   fields and continuation need route-specific verification, not boilerplate.
   BBK gap claims and percentages are unverified without a required inventory
   and representative live evidence from the same installed wheel. Treat
   exclusions by semantics and permissions, not by copying a segment denylist
   or assuming every GET should be shipped.

## Work order for the implementer

Do not implement all rows together. Start with item A. Record each completed
slice and its check in the work log and make one narrowly staged commit with a
message naming the observable behavior. Stop for owner approval on the
public-API changes in C and F. Keep `atlassian-python-api==5.0.5`, the current
transport boundaries, stable IDs and legacy output unless the owner approves a
change. No new framework/dependencies, bulk formatter/linter fixes, broad
credential scanning or BBK changes.

| Slice | Smallest deliverable | Decisive check |
| --- | --- | --- |
| **A. File publication** | Only the shared no-clobber primitive, the two call sites and their tests. Keep `--base64` behavior, existing byte limits and receipt fields. Update `attachment-get --help` and its README example: the current help still says it never writes a file and requires `--base64` (`cli.py:1746–1759`). | For both entry points, create the competing destination **after** the early check and **before** publication with a synchronization point, not a sleep. Existing bytes unchanged, no receipt, no owned temp remains. Existing-file and exact-byte success controls. Assert the real staging glob or ownership, not a guessed name. |
| **B. SDK body and retry boundaries** | Reject incomplete/undeclared binary statuses and map interrupted body reads locally. Separate the numeric/retry edge cases and legacy gzip into small commits. Only touch relevant transport branches. | Installed loopback: declared-length close after a prefix (binary and JSON), unsolicited `206`, unapproved `204`, valid binary, exact/over cap, JSON `1e999` vs a valid finite exponent. Check exit, one sanitized envelope, known status, no receipt or temp, no second request. Unit: invalid `Retry-After` falls back, certificate failure makes one attempt, normal transient retry still recovers. Gzip: complete and truncated members on the same pinned dependency, same test must fail on the bad baseline. |
| **C. Read-only public boundary** | Bring the documented `client_for` exposure to the owner first; propose a fixed surface on the existing dispatcher. Keep only verified required reads and compatible wrappers, not a generic SDK proxy. | Representative documented reads still work. Public transport and unsupported operations are absent/rejected without any request. No remote mutation tests. Verify independent callable/CLI contract evidence before release. |
| **D. `find` and canonical usability** | First commit: fix success accounting and unavailable targets, then document/test a total read cap before calling the workflow complete. Separate CLI commits: resolve the selected env URL; enforce canonical parse and action contracts locally. | `find`: mixed outcomes across two terms for **each** product, including a successful empty term; one absent pair with other requests observed and correctly scoped; all fail; later-page failure with another term's rows retained; documented cap with bounded request count. CLI: env-only and saved-store cases; missing/unknown option, both action orders, valid help, literal flag-looking value and binary-only option on JSON; exact JSON/error exit 2 and no request or credential access on invalid calls. |
| **E. Existing reds and measurement** | Fix invalid fixtures/assertions separately from product fixes. For the live-check guard, correct only the `jira-create-meta` argument positions; retain shape and exact-key validation. Seed the two child environments with required non-secret Windows or selected user-site values, not the parent environment wholesale. Verify the metadata and wiki contracts before editing either reader. | `tags` happy/cap/cursor-fault controls; Jira bad and valid late-row IDs; Markdown semantic inertness/visible text. Runner tests must accept the real three-element plan, reject extra options and bad keys before any subprocess, and exercise the nested assertions. Run affected modules, then full offline suite with explicit executable, synthetic settings, unique ignored basetemp and real exit status. Measure branch coverage with explicit package and subprocess collection; report actual coverage scope. |
| **F. Close delivery, not by rewrite** | Get the owner decision on the approved grouped CLI/Python surface versus the current `read ID` syntax. Use the existing registry/dispatcher, not a second facade. Freeze the required versioned routes and BBK workflows in reviewable tracked evidence; keep provisional entries explicit. Make generation reproducible from approved tracked inputs. Implement one representative operation per product plus a documented page, semantic POST and binary/text cases before incrementally adding the rest. | Use independently sourced expected args, an opaque continuation and captured HTTP calls, including valid empty data vs failure. A generation-only compare is not an applicability or shape test. Use `--describe` argv as written on a clean installed wheel outside the checkout; compare Python and CLI for one operation. Then the owner runs approved read-only server checks on that same wheel. Keep remaining gaps explicit; no BBK retirement approval inferred. |

Local focused command pattern (from the project root, after selecting the
checked CLI/interpreter and preparing the synthetic environment):

```text
C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q --tb=short --basetemp=.planning/<new-run>/pytest <exact selection>
```

## Evidence at handoff

- Fresh above pytest pattern, `test_bitbucket_attachment_cli_e2e.py` truncated
  gzip case, two `test_bitbucket_extra_cli_e2e.py` cases (tags cursor and NUL),
  plus all of `test_jira_metadata_unit.py`, `test_jira_wiki_unit.py`,
  `test_jira_wiki_cli_e2e.py`, `test_binary_read_cli_e2e.py` and
  `test_federated_cli_e2e.py`: **exit 1, 165 passed, 10 failed, 0 skipped**,
  19.84 s, `D:/REPO/github/AtlaWire`. Synthetic home and nonexistent fallback
  credentials; no plugin autoload. CLI installation resolved to the working
  tree, not a clean wheel.
- Controlled probes used `C:/Python315/python.exe -B`, existing loopback and
  Click runner, synthetic values, and project-local scratch; completed with
  exit 0. Observed `206` success + file, both overwrites at publication,
  truncated body exceptions for JSON and binary, nonfinite JSON success,
  missing env URL resolution, false `find` failures and order-dependent
  discovery success. Read-only proxy exposure checked by attribute inspection
  without sending any request. Retry header reproduced directly; TLS retry
  is a source/type finding, not a connection experiment.
- Separate stdlib/Requests gzip loopback probe, `C:/Python315/python.exe -B`,
  exit 0: both passed the valid member; the Requests/urllib3 stack accepted the
  missing trailer, while `gzip.decompress` raised `EOFError`. This verifies
  the dependency-stack behavior, not an upstream patch or release.
- DeepSeek Flash routine offline run (`ses_dfa01571fffeMa6XHYuHNkswJN`), same
  project root and interpreter, using the pytest pattern above with `-rs
  --tb=line` instead of `--tb=short`, selecting `tests/test_entrypoints.py`,
  `tests/test_live_read_only_runner.py` and
  `tests/test_live_read_batch_contract.py`: **exit 1, 137 passed, 3 failed,
  1 skipped**, twice. The skip was the console launcher absent from that
  deliberately narrow `PATH`. Failed nodes:
  `test_fixed_prefix_runs_installed_cli_outside_checkout`,
  `test_new_command_plans_are_fixed`, and
  `test_live_failures_hide_sentinels_under_showlocals`. No live commands were
  run; this is supplemental test evidence, not a second architectural review.
- No fresh full-suite coverage, clean wheel, live parity, or exhaustive
  operation/SDK verification in this follow-up. No unrelated work reviewed or
  changed. **Verdict: fix the confirmed blockers; release verification remains
  INCONCLUSIVE.**

# AtlaWire: agent readiness review and 90% plan

**Baseline:** local commit `0f42aa3`, 1,386 offline tests passing on the CPython 3.15
user installation. This review is read-only; it does not authorize live requests,
writes, dependency changes, publication or Git history changes.

**Related material:** [current handoff](../HANDOFF.md),
[web-study application](2026-11-20_WEB_STUDY_APPLICATION.md),
[parity baseline](2026-11-20_BBK_PARITY_BASELINE.md), and [TODO.md](../../TODO.md).

## 1. Verdict

The read-only command surface is broad and the offline evidence is substantial, but the
product is **not yet 90% ready for unsupervised agent use**. The decisive gap is not
command count: it is proof that the existing commands work against the real Jira,
Confluence and Bitbucket deployments, and that an agent can discover and use them
safely without setup help.

Recommended path: **freeze the read-only feature set, validate it live, publish a
one-page agent quickstart, run a small measured pilot, and let observed failures drive
the next cycle.** Do not add profiles, cross-issue comment search, automatic PR diff
fallback, writes or full legacy parity before that pilot. This matches the YAGNI goal:
improve what agents actually need, not everything that could be built.

A sanitized ChatGPT HIGH consultation independently recommended the same option
(gated pilot first). Its detailed advice is recorded in section 9.

## 2. What is verified, and what is not

Verified on this machine at `0f42aa3`:

- 30 installed CLI commands are discoverable through `atlawire --help`.
- 1,386 offline tests pass, including installed-CLI loopback tests.
- Ruff lint, Ruff security rules on runtime source, formatting, Pyright, the lockfile
  and `git diff --check` pass.
- The latest P0 fix rejects HTTP 206 before decoding; the regression produced exit 0
  and a row on the old code and now produces a static error with empty stdout.
- The installed CLI is `C:\Users\magic\AppData\Roaming\Python\Python315\Scripts\atlawire.EXE`;
  the project `.venv` was not used.

Not verified:

- Any request to a real Jira, Confluence or Bitbucket instance.
- The actual authentication mode (Bearer PAT versus Basic), permissions, TLS chain,
  proxy, DNS and reverse-proxy path on those instances.
- Live response shapes for plugin search, blame, nested browse children, the PR
  dashboard, Confluence macros and capped PR diffs.
- Behaviour on an agent host other than this Windows/Python 3.15 installation.
- A reproducible package artifact: the current install is editable from this checkout.
- CI, strict Pyright configuration and a published supported-version matrix.
- The 26 local commits are not pushed; untracked design and reference material remains
  in `.development/` and `docs/`.

A passing offline suite proves the modeled scenarios, not deployment compatibility.

## 3. Review of the latest simple-agent work

The HTTP 206 patch is correct and well scoped:

- `_check_status` now rejects 206 for every complete-document reader, so a partial body
  cannot be interpreted as a successful result.
- JSON GET and POST share the guard; raw text keeps the same diagnostic.
- The transport test covers GET, POST and a 206 with invalid JSON, which proves the
  status check precedes decoding.
- The installed-CLI test asserts one request, exit 1, exact static stderr, empty stdout
  and no token/sentinel leakage.
- The pre-fix failure was reproduced for the intended reason: exit 0 with a comment row.
- The commit is focused (`5 files, +69/-9`) and does not mix unrelated refactors.

Residual risks, not defects in this patch:

- No live 206 behaviour has been observed.
- Other unexpected statuses (202/204/207) still reach the JSON decoder rather than a
  specific protocol error; that is a separate contract decision, not part of this fix.
- There is no CI gate, so future changes can regress without the full local run.
- The raw-text path reads into a 1 MiB cap, but JSON responses have no decoded byte
  cap or operation-wide budget yet.

The patch is accepted for the pilot baseline. Independent review by a stronger model is
still desirable before release, as requested.

## 4. Findings, ordered by risk

### F1 — P0 blocker: live authentication, TLS and proxy are unproven

Every command uses `Authorization: Bearer <token>` and `trust_env=False`. If the target
requires Basic authentication, a corporate proxy, a private CA, or a different header,
the tool will fail before returning any data. Public documentation indicates PATs are
available on Jira 8.14+, Confluence 7.9+ and Bitbucket 5.10, but the actual token type,
header scheme, permissions and network path must be confirmed on the target. Do not
assume a token that works for `bbk` is accepted by AtlaWire without a check.

**Action:** confirm authentication mode, proxy/CA and target versions with the owner;
run one read-only `jira-me`, one `page`, and one `projects`/`repos` call before anything
else. If Bearer fails, fix authentication explicitly; do not add a silent fallback.

### F2 — P0 blocker: no live smoke for the in-scope read commands

Offline fixtures cannot prove plugin search, bare-array blame, nested browse children,
the dashboard, PR diff caps or Confluence macros. These are exactly the shapes most
likely to differ on the installed versions.

**Action:** run the 12-check live smoke set in section 7 and record sanitized evidence.
Fix mismatches with focused compatibility patches and offline regressions.

### F3 — P1: agent distribution and installation are undefined

The package is unpublished and installed editably from this checkout. Local commits are
ahead of the remote, and earlier history contains unrelated material. A same-machine
pilot is feasible now; remote agents need a versioned wheel and an approved distribution
channel, plus network access to the instances.

**Action:** choose a same-machine pilot first, pin the commit, and document the exact
interpreter/CLI path. Defer remote distribution and publication until history/provenance
is cleared by the owner.

### F4 — P1: no agent quickstart or canonical skill

`atlawire --help` lists 30 flat commands, but there is no one-page guide covering setup,
the top recipes, output modes, limits or known non-features. The README status paragraph
is stale and the shared `bitbucket` skill still describes `bbk`. Agents will either
guess or fail.

**Action:** add a concise quickstart with 5–7 recipes, output/limit semantics, known
limitations and a feedback section. Update the README status. A project-local skill can
follow after owner approval; do not rewrite the global skill yet.

### F5 — P1: credential ergonomics and leakage risk

Agents must set six environment variables and pass `--token-from-env` on every command.
That is workable, but a paste of a token into a prompt, shell argument or log would
leak it. Profiles/keyring are not implemented and are not required for a same-machine
pilot.

**Action:** document a safe env-var setup and a rule that tokens never appear in prompts
or command arguments. Keep `trust_env=False`. Defer profiles/keyring until the pilot
shows repeated setup friction.

### F6 — P1: limited/default results can look complete

`search` defaults to one page; `jql`, `prs`, `files` and others return up to a limit and
print `# N row(s)` without a completeness flag. Agents may treat a limited or
first-page result as exhaustive. Existing fail-closed behavior is good, but the
successful-limited case needs clear documentation.

**Action:** state limits and “first page only” in the quickstart and command help; add
an opt-in metadata/envelope only if pilot reports show misinterpretation. Do not break
existing JSON/TSV shapes.

### F7 — P2: missing workflows that may matter later

Cross-issue Jira comment search, a cross-product `whoami`/doctor, the `review` packet,
automatic PR diff fallback, and local `scan`/`grep` are not implemented. Some are legacy
`bbk` workflows; none is proven necessary for the first pilot. Workarounds exist:
`jql` + `issue-comments`, `pr files` + per-file `diff`, and the three identity/list
commands.

**Action:** list them as deferred candidates, collect requests, and implement only when
a top task is repeatedly blocked and no reasonable workaround exists.

### F8 — P2: release engineering is incomplete

There is no CI, no non-editable wheel check, no strict Pyright profile, and no
supported-version matrix. For a local pilot the full local suite and static checks are
sufficient; for a broader release they are not.

**Action:** keep the exact-commit full-suite gate for the pilot. Add CI and a wheel smoke
test when the owner authorizes a remote/published distribution.

### F9 — P2: documentation ownership is unfinished

`.development/` reference copies and `docs/INDEX.md` are untracked or copied from `bbk`.
They are useful evidence but not canonical agent documentation. The quickstart should be
the single agent-facing source; the deeper references can remain local until the cutover
is approved.

**Action:** make the quickstart and README canonical for agents; do not publish internal
references or local paths. Defer the full documentation cutover.

### F10 — P3: performance and cost are unmeasured

Recursive `files`, a full `find-repos` walk, and per-issue comment traversal can be slow
on large instances. No cache or concurrency is implemented, by design. Do not optimize
speculatively; measure only if the pilot shows a task-level problem.

**Action:** record task time/calls in the pilot; optimize only a measured bottleneck.

## 5. What “90% ready” means

90% means **at least 90% of a representative set of real read-only agent tasks complete
correctly without human intervention or an unplanned workaround**. It does not mean 90%
of `bbk` features. The scope is frozen for the pilot except for correctness, security,
compatibility and high-impact usability fixes.

### Ten-point readiness rubric

| # | Criterion | Status at `0f42aa3` |
| --- | --- | --- |
| 1 | Read-only scope frozen and documented; deferrals explicit | Pending |
| 2 | Full offline suite and static checks green on a pinned commit | **Pass** |
| 3 | Installed CLI works on the intended Python 3.15 runtime | **Pass locally** |
| 4 | Live smoke passes for Jira, Confluence and Bitbucket | **Fail/pending** |
| 5 | Auth/permission failures are understandable; no secret leakage | Offline pass; live pending |
| 6 | No known silent partial-success defects in in-scope commands | Pass for tested cases; live caps pending |
| 7 | Agent quickstart, known limitations and feedback template exist | **Fail/pending** |
| 8 | A fresh agent completes 5 representative tasks using only the docs | **Fail/pending** |
| 9 | No open P0/P1; remaining P2/P3 documented with workarounds | Pending |
| 10 | Pilot metrics and weekly triage are owned and scheduled | **Fail/pending** |

Current position: 3 of 10. The missing seven are mostly live validation and agent
packaging, not more commands. Reach 9 of 10 before calling the product 90% ready.

## 6. Scope freeze

### In scope for the pilot

- Jira: `issue` (JSON/Markdown), `jql`, `mine`, `statuses`, `transitions`,
  `issue-comments`, `jira-me`.
- Confluence: `page` (JSON/Markdown), `cql`, `spaces`, `children`.
- Bitbucket: `projects`, `repos`, `branch`/`branches`, `commits`, `file`, `files`, `ls`,
  `blame`, `commit`, `commit-changes`, `commit-diff`, `search`, `pr` (show, files,
  comments, commits, diff, file), `prs`, `my-prs`, `find-repos`.
- Cross-cutting: JSON/TSV output, bounded paging, fail-closed errors, instance-bound
  destinations, explicit env credentials.

### Deferred, with workaround

| Deferred | Workaround / reason |
| --- | --- |
| Cross-issue Jira comments | `jql` to find issues, then `issue-comments`; demand-driven |
| `whoami` / doctor across products | `jira-me`, `projects --limit 1`, `spaces --limit 1`; add only if setup failures recur |
| Profiles / keyring | Explicit env vars; no credential-management redesign before the pilot |
| Automatic PR diff fallback | `pr files` + explicit per-file `pr … diff PATH`; document caps |
| Writes / transitions execution | Read-only pilot; separate safety contract later |
| Raw REST passthrough | Fixed-product read commands only; separate allowlist/gate later |
| Cache / catalog | No persistent cache; explicit refresh later only after live listing evidence |
| Full `bbk` parity, `scan`/`grep`, `review` packet | Use `bbk` or compose existing reads; demand-driven |
| Remote distribution / publication | Same-machine pilot first; owner clears history/provenance before push |

## 7. Plan to 90%

### Phase 0 — Owner decisions (blocking, no code)

Confirm, in writing:

1. Target product versions (Jira 8.22, Confluence version, Bitbucket 5.10) and the
   authentication mode/header actually used (Bearer PAT, Basic, other).
2. Network path: direct, VPN, proxy, private CA. If a proxy/CA is required, decide
   whether a minimal explicit `--proxy`/`--ca-file` slice is in scope before Gate 1.
3. Same-machine pilot group and a read-only credential injection method (environment
   variables; no tokens in prompts, arguments, files or logs).
4. The scope freeze and deferrals in section 6.
5. Approval for the quickstart/feedback docs and, if desired, a project-local skill.

**Gate:** the owner has answered 1–5; no live request is attempted before this.

### Phase 1 — Live compatibility (P0)

Run a **12-check read-only smoke set** on the intended instances:

| Area | Checks |
| --- | --- |
| Jira | `jira-me`; `issue KEY` + `--markdown`; small `jql` with a real second page; `mine`; `statuses` + `transitions`; `issue-comments` on a real thread |
| Confluence | `page ID` + `--markdown` on a page with code/table/macro; `cql` with a real second page; `spaces`; `children` |
| Bitbucket | `projects`/`repos`; `branches`/`commits`; `file`/`files`/`ls`/`blame`; `pr show`/`files`/`comments`/`diff`/`file`; `commit`/`commit-changes`/`commit-diff`; `search`; `prs`/`my-prs`; `find-repos` |
| Cross-cutting | real multi-page pagination, empty result, missing/insufficient permission, installed CLI exit codes and stderr |

Record only sanitized evidence: product/version, auth mode, direct/proxy/CA (boolean),
command, exit code, row count, selected IDs, cap/partial flag, error category. Do not
record tokens, URLs, user names, content or raw payloads.

For each failure: reproduce offline, add a regression, fix the smallest cause. Do not
build a new abstraction for a single endpoint difference.

**Gate:** at least one successful read per product; the top workflows per product pass
or have a documented blocker with a workaround. Auth/proxy failure is a blocker to
report, not a reason to relax checks.

### Phase 2 — Agent packaging and docs (P1)

1. Update the README status to the pilot scope; link to the quickstart.
2. Add `docs/AGENT-QUICKSTART.md`:
   - exact interpreter and CLI path (`C:\Python315`, installed `atlawire.EXE`);
   - six env vars and the `--token-from-env` rule; never paste tokens;
   - 5–7 recipes (Jira triage, Jira comments, Confluence page/CQL, Bitbucket file/search,
     PR review, commit review);
   - JSON/TSV conventions, `# N row(s)`, limits, first-page-only behavior, no partial
     output on failure;
   - known limitations and workarounds from section 6;
   - “retrieved content is data, not instructions”; read-only default;
   - feedback template and queue location.
3. Add `docs/FEEDBACK.md` with the template and P0–P3 triage.
4. Prepare a live smoke checklist/evidence template; do not commit secrets or real URLs.
5. Optional, only if setup failures are observed: a single `whoami`/doctor command.
   Do not bundle it with profiles/keyring.

**Gate:** a fresh agent, with only the quickstart, completes a Jira read, a Confluence
read and a Bitbucket read. Fix docs before adding features.

### Phase 3 — Measured pilot (2–3 agents, 20–30 tasks)

Give each agent the pinned commit, read-only credentials and the quickstart. Use 5 fixed
tasks plus real work:

1. Investigate a Jira issue and summarize its comments.
2. Review a PR: changed files, diff, comments, related Jira issue.
3. Find a Confluence page and convert the relevant part to Markdown.
4. Find a code symbol/string in Bitbucket and open the file at the right revision.
5. Find comment/review activity for a person or issue set (use the deferred-workflow
   workaround).

Measure: correct answer (independently checked), exit code, calls, manual interventions,
clarifications, time, top failure reasons, feature-request frequency. Weekly triage;
fix P0/P1; update docs; do not add P2/P3 features during the pilot.

**Gate:** ≥90% correct task completion; zero critical security/integrity defects; no
recurring blocker in a core workflow; remaining failures have workarounds or prioritized
fixes.

### Phase 4 — 90% decision and next cycle

Run the ten-point rubric. If 9/10 pass, declare the pilot 90% ready and broaden agent
use. Decide the next cycle only from pilot evidence: cross-issue comments, `whoami`,
profiles, automatic diff fallback, writes, remote distribution. Do not start a parity
program.

## 8. Testing plan

### T0 — Exact baseline

```shell
git status --short --branch
C:/Python315/python.exe -B -c "import sys; assert sys.version_info[:2]==(3,15) and sys.prefix==sys.base_prefix"
C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests
ruff check src tests
ruff check --select S src
ruff format --check src tests
pyright --pythonpath C:/Python315/python.exe src tests
uv lock --check
git diff --check
```

Record the commit, test count, failures/skips and exact commands. A cached or partial
run is not fresh evidence.

### T1 — Offline contract matrix

For each in-scope command group, verify at the installed-CLI boundary:

| Case | Expectation |
| --- | --- |
| Happy path | Expected rows/fields, exact destination/context, one logical operation |
| Empty result | Exit 0 with an empty list/header, not an error |
| Server-capped page | Advance by rows consumed; no skipped page |
| Later-page failure | Nonzero exit, empty stdout, sanitized stderr |
| Malformed row/metadata | Nonzero exit, empty stdout, no traceback |
| Redirect | Refused, no credential forwarding |
| 401/403/404 | Distinct, understandable errors; no payload echo |
| Limit reached | Clear row header/limit semantics; no false completeness claim |
| Encoding | Valid Unicode preserved; lone surrogates rejected before output |
| Credential selection | Only the selected product token/URL is used in loopback tests |

Most cases exist. Audit the matrix against the 30 commands and add only missing cases;
do not duplicate the same pager test for every endpoint.

### T2 — Live read-only smoke

Use the 12-check set in Phase 1 with a dedicated read-only identity. Store sanitized
evidence; compare IDs/counts/fields with `bbk` on the same scope. Do not capture content
or private URLs. Run once per target version/auth configuration; repeat after any
transport or adapter change.

### T3 — Negative live checks

Where safe and authorized: invalid token, an object the identity cannot see, a missing
key/page, a 429 if it occurs naturally. Assert the error category and no secret echo. Do
not induce destructive writes or broad load. Do not retry 429 during the pilot.

### T4 — Agent usability

Fresh sessions, same model/settings, only the quickstart. Five fixed tasks from Phase 3.
Independently check the expected answer. Record success, calls, clarifications, time and
failure reason. A task that “exit 0” but returns the wrong issue is a failure.

### T5 — Feedback regression

Every accepted bug report becomes a failing offline test before the fix, then passes;
every feature request gets a written disposition (accepted/deferred/rejected with reason).
Run the full suite on the candidate before the local commit.

### T6 — Release/pilot gate

Use the ten-point rubric. Block on any P0, any silent partial success, any credential
leak/misroute, or a broken existing output contract. Do not block on deferred features
that are explicitly out of scope and have workarounds.

## 9. ChatGPT HIGH consultation and disposition

A sanitized temporary ChatGPT consultation (GPT-6, High effort) was asked to choose
among: (A) hand off the current read commands after live smoke and a quickstart;
(B) add `whoami`/doctor and profiles first; (C) add cross-issue comments first;
(D) complete full legacy parity first.

Recommendation: **A — a gated agent pilot**. Key points and disposition:

| Advice | Disposition |
| --- | --- |
| 90% = ≥90% of representative read-only tasks succeed correctly, not 90% of legacy features | Adopt as the definition in section 5 |
| Gate 1: live smoke on all three services, understandable auth errors, quickstart, pinned version | Adopt; Phase 0/1/2 |
| Gate 2: ≥90% task success, zero critical defects, no recurring blocker | Adopt; Phase 3/4 |
| Top risks: real-server compatibility/auth, silent incompleteness, agent trust boundaries | Adopt as F1/F2/F6 and the quickstart security rules |
| Defer profiles/keyring, cross-issue comments, automatic PR fallback, writes, full parity | Adopt; section 6 |
| Same-machine pilot first; remote needs a reproducible artifact and approved channel | Adopt; F3 |
| Minimal doctor only if live setup failures recur; do not bundle with credential redesign | Adopt; optional Phase 2 |
| Feedback: 3–5 agents, 20–30 tasks, weekly triage, feature admission rule | Adopt; Phase 3 and section 10 |

The consultation is design input, not execution evidence. Its Confluence PAT version
claim was checked against public Atlassian documentation (PATs from Confluence 7.9);
the target version and actual header still require live confirmation. No private data
was sent.

## 10. Feedback loop and YAGNI rule

### Report template

```text
Task/goal:
Command(s) and arguments:
Expected:
Actual:
Exit code:
Sanitized stderr:
Environment: product/version, auth mode, OS/Python, AtlaWire commit
Frequency/impact:
Workaround:
```

One queue, two labels: bug vs feature request. Keep reports free of tokens, URLs, user
names and content; use synthetic IDs for examples.

### Triage

| Priority | Meaning | Action |
| --- | --- | --- |
| P0 | Security, unintended mutation, credential leak/misroute, silent data corruption | Stop the affected pilot; fix immediately |
| P1 | Core task blocked, wrong result or silent omission | Fix before expanding the pilot |
| P2 | Repeated workaround or high-value missing capability | Rank by observed demand; batch into the next cycle |
| P3 | Rare/convenience/legacy parity | Defer; record the disposition |

Feature admission rule: add a capability only when it repeatedly blocks a meaningful
task, has no reasonable existing-command workaround, and is small enough to maintain.
Otherwise document the workaround and wait for more evidence.

### Metrics

- Correct task completion rate (primary; ≥90% for Gate 2).
- Critical defects (target 0).
- Manual interventions/clarifications per task.
- Calls, retries and time per task (baseline, not a token claim).
- Top five failure reasons and command-selection mistakes.
- Feature-request frequency by topic.

Judge correctness against independently checked expected outcomes, not exit code alone.
Do not claim token savings without matched fresh-session measurements.

## 11. Owner decisions required

1. Confirm the actual auth mode/header for each product and whether the current Bearer
   implementation works; if not, authorize the minimal auth fix.
2. Confirm direct network or proxy/CA; if proxy/CA is required, decide whether to add
   explicit options before Gate 1.
3. Confirm the Confluence version and PAT availability.
4. Approve the same-machine pilot, read-only credential injection and the scope freeze.
5. Approve the quickstart/feedback docs and, if desired, a project-local skill.
6. Decide whether `whoami`/doctor is required before the pilot. Recommendation: no;
   use the three existing probes and add it only if setup failures recur.

## 12. Immediate next actions for the implementer

Until the owner answers Phase 0, do only offline work:

1. Write `docs/AGENT-QUICKSTART.md` with setup, 6–7 recipes, output/limit semantics,
   known limitations, security rules and the feedback template.
2. Write `docs/FEEDBACK.md` with the template and P0–P3 triage.
3. Update the README status and link to the quickstart; verify every example against
   the actual CLI help and behavior.
4. Prepare the live smoke checklist/evidence template; do not include secrets or real
   URLs in the repo.
5. Add an offline test that `atlawire --help` lists the expected top-level commands and
   exits 0, if not already covered.
6. Run the full suite and static checks on the exact commit; commit the docs/pilot
   baseline locally. Do not push.

Do not implement cross-issue comments, profiles/keyring, automatic PR diff fallback,
writes or remote distribution until the pilot produces evidence.

## 13. Evidence limits

This review used the local checkout at `0f42aa3`, the existing offline suite and static
checks, the implementation handoff, the parity baseline, and public Atlassian docs.
It did not read credentials, call a live instance, run a write, inspect internal URLs,
or publish anything. The 90% rubric is a planning tool, not a measured product score;
the pilot supplies the real measurement.

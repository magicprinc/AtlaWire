# Applying the web-tools study to AtlaWire

**Status: design reviewed; implementation scope and live checks await owner approval.**

## Evidence and scope

The source is the separate `best_search_crowl_get-content/result.md` study, with its
`selection.md` and `pilot/modsearch_parity.md`. It evaluated public web research tools,
not self-hosted Atlassian APIs. Its two Russian queries and small fixture set do not
prove general search quality, scalability, provider cost, or AtlaWire compatibility.
Neither tested crawler passed its bounded-crawl contract.

AtlaWire's existing priorities and unresolved contracts are in [TODO.md](../../TODO.md);
the [Atlassian CLI comparison](2026-11-20_ATLASSIAN_CLI_RESEARCH.md) recommends parity,
completeness, secure instance binding, and safe writes before new interfaces.

A sanitized temporary ChatGPT consultation used GPT-6, High thinking effort. It
recommended local-first REST, explicit incompleteness, bounded work, provenance, and
exact account identity before fuzzy discovery. This is a design opinion, not executed
evidence; it suggested a new common result envelope and partial-result returns, which
must not silently replace AtlaWire's current output and fail-closed contracts.

## Product decision

Use the study to improve AtlaWire's retrieval contracts and acceptance tests, not to
expand its runtime stack. Keep the synchronous CLI/library, product-specific REST
adapters and shared HTTP policy. Public web tools remain development tools for public
documentation; they are not an AtlaWire fallback. The study did not measure token
savings in fresh sessions or prove that a smaller response preserves all useful data.

1. **Evidence-led parity first.** Make the acceptance matrix map each actual workflow
   to offline and separately authorized live evidence. Distinguish documented,
   tested with a fixture, and exercised on a target deployment. Record the version,
   authentication method, endpoint and observable outcome without recording private
   URLs or payloads. Compare useful output with `bbk`, not the number of commands.
2. **Completeness and source.** Document index coverage, requested scope, result limits,
   and where values came from. Distinguish a scope with no matches, a requested top-N
   result, and a failed or incomplete scan. Keep existing JSON/TSV shapes and
   fail-closed output. Consider machine-readable errors or opt-in metadata separately;
   do not add a common result envelope just to mirror a web tool.
3. **End-to-end bounds.** Current transport has connection/read timeouts and individual
   page caps, but these are not an overall deadline, response-size limit for JSON, or
   total request budget across a multi-issue search. Design those separately and test
   capped, repeated, malformed, slow, and late-failing pages. Prove the bounds at the
   installed CLI entry point before enabling broad fan-out.
4. **Explicit local data boundary.** Keep private URLs, queries, responses and credentials
   off public search/rendering services. Current explicit bearer sessions
   disable environment-derived settings, including proxy discovery; corporate proxy,
   CA, and authentication behavior require approved tests. A single configured
   destination per command is not yet a credential profile bound to that destination.
   Test that binding, including overrides, before claiming it. Keep TLS verification on.
5. **Fallback only for a proven gap.** Prefer documented instance APIs. For example,
   a future file-enumeration alternative to indexed Bitbucket search needs explicit
   scope, a request budget, and different coverage documentation. It must not
   automatically follow a `401`/`403` or make an incomplete walk look complete.

## What not to import

- No web crawler, cloud renderer, multi-engine search service, Wikipedia integration,
  proxy rotation, or hosted LLM for private Atlassian data based on this study.
- No claim that a bounded API traversal is equivalent to tested website crawling.
- No dependency, cache, background index, generic plugin registry, or additional MCP
  merely because a separate web-research pilot considered it.
- No silent multi-provider fallback or automatic fuzzy identity selection. `401`/`403`
  and an empty result must remain distinguishable.

## Jira cross-issue comments: recommended first slice

The legacy workflow searches issues by **issue update time**, reads complete threads
when embedded comments are truncated, then sorts by comment creation time. Exact user
matching and fuzzy/transliterated candidate resolution are separate concerns. The
existing single-issue reader (`a46195b`) addresses thread pagination only.

| Option | Trade-off | Recommendation |
| --- | --- | --- |
| Copy legacy fuzzy resolution and early stopping | Convenient for Cyrillic names; a single visible prefix hit can still be the wrong person. More resolution rules and more failure modes to prove at once. | Reject implicit selection and do not copy the early stop. |
| Exact account, one explicit project, fully inspected candidate set | Easier to explain and test; requires a known login or the current user, and cannot replace unconstrained `bbk comments` yet. | First slice. Keep `bbk` available for broader workflows. |
| Exact search plus a separate fuzzy candidate finder | Restores name discovery without conflating suggestion and identity, but adds a second permission/paging contract. | Later: return bounded candidates, require explicit account selection even with one visible match. |

### Proposed contract and boundaries

- **Resolve once.** A supplied exact login uses the configured instance's
  [`GET /user?username=…`][jira-user]; current user uses [`GET /myself`][jira-self].
  Project a private authoritative identity and match it to the original
  `comment.author`, never `updateAuthor`, display name, email, or a substring.
  Prefer the server's user `key` if the target proves both routes supply it.
  [`GET /issue/{key}/comment`][jira-comments] declares `author.key`, but its example
  omits it; neither this documentation nor `jira-me` proves the live join. Keep
  `jira-me` and `issue-comments` output unchanged. If keys are missing or identity
  cannot be compared, do not guess or silently skip possible matches. A weaker
  exact-login-only mode would require a separate decision and must not be sold as
  rename-safe. Do not assume deleted users are resolvable or request extra privileges.
- **Preserve the date contract.** `--days` restricts *issue updates*, as in `bbk`.
  An older comment on a recently updated issue may qualify. Compare comment
  creation times as UTC instants with fractional precision, not strings or integer
  seconds, and break equal instants deterministically by issue key and comment ID.
  Apply the result limit only to the global ranked matches in the inspected scope.
  Defer a comment-created window to a separate, explicit option if needed.
- **Use a complete thread reader.** Page [`GET /search`][jira-search] for candidates
  in the project and read the dedicated comment endpoint in the same session.
  Reuse the issue comment page checks with a narrow internal seam to retain
  author identity. Do not compose the public `jql` or `issue-comments` results:
  they discard required metadata or identities, and repeated public calls would
  create separate sessions and budgets. Embedded comments are a later optimization,
  only if they match the dedicated endpoint's visibility and can prove completeness;
  do not treat missing embedded data as empty.
- **Bound the whole traversal.** One search operation owns a total request budget,
  debited before every attempted identity lookup, issue page or comment page. Bound
  decoded response bytes before parsing, and hold at most bounded working pages,
  identity/duplicate checks and the best N results. Start serial with no automatic
  retries. Use an elapsed-time budget to stop new work and check during reads; a
  Requests inactivity timeout is not a hard wall-clock deadline. If a hard stop is
  required, it needs a separately verified mechanism, including blocking I/O.
- **Publish only after completion.** Reject a detectable page inconsistency, budget
  exhaustion or read failure with nonzero exit, sanitized stderr, and empty stdout.
  Publish the agreed projection with preserved legacy identifiers and locally
  constructed comment links; never request links from a response. Success is limited
  to Jira's visible, observed project/window results. Offset pagination is not a
  point-in-time snapshot, even with stable totals, unique IDs and fixed ordering.

### Adversarial review and acceptance

| Plausible defect | Decisive check |
| --- | --- |
| Wrong person selected for a renamed login, shared display name, or recently edited comment | Same author key under a different login must still match; another key with the same display name, or a matching `updateAuthor`, must not. An unresolved login or a missing comparable key must fail without a successful empty result. |
| `--days` silently changes to a comment-created window, or top-N stops at the first matches | Include a qualifying old comment on a recently updated issue; put a newer matching comment on a later page. Assert exact IDs and deterministic order across time zones, fractional seconds and ties. |
| Known partial data is reported as complete | A capped issue page and a capped thread must advance by rows consumed. Then replay a page, change a total, return an empty intermediate page or fail a later request. Assert exact attempts, no extra requests at the cap, and empty stdout. A same-count concurrent replacement can still evade detection; document it. |
| Per-endpoint limits mask a global budget reset or a slow response | Consume budget across identity, search and multiple threads; assert no next attempt. Test a decoded oversized response and separately check elapsed-budget behavior, including an active slow response. |
| Safe-looking output hides the wrong destination or erases context | Installed CLI tests assert configured context and bearer selection, synthetic sink untouched, and matching source IDs/links; error text excludes request, response and credentials. |

Do not port the legacy top-N early stop: after reading one issue with a recent edit
and an old comment, a later issue can still contain a newer matching comment. Even
the legacy timestamp comparison needs an upper bound relating issue `updated` to
every relevant `comment.created`, and a rule for ties and reordering. That bound
has not been established. Likewise, one visible fuzzy candidate is not proof of
identity if accounts are filtered, hidden or the result is capped.

## Execution and release gates

1. Approve the project-scoped, exact-identity slice and the intended output. Separately
   authorize a minimal read-only check on the intended Jira instance: current/exact
   account resolution and comparable comment author keys, visible offsets and totals.
   Record only sanitized observations. Missing evidence blocks live compatibility,
   not offline preparation.
2. Build the smallest offline reference workflow. DeepSeek implements the agreed
   scenarios and runs focused checks. Primary review evaluates the design, code and
   tests against separate expected results; demonstrate that accepting the wrong
   author, stopping early, and resetting the shared budget are detected. Run one
   full regression on the milestone candidate.
3. Compare representative read workflows on the authorized real instances before
   claiming replacement or adding caches. Record result identity, qualifiers and
   request counts; measure latency or output size only if they would change a decision.
   Keep corporate TLS/proxy, credentials, and supported-version claims explicit.

No cross-issue implementation, external configuration change, or live query is
authorized by this note.

[jira-self]: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/#myself-getUser
[jira-user]: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/#user-getUser
[jira-search]: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/#search-search
[jira-comments]: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/#issue-getComments

# AtlaWire plans: open objections for independent review

Status: implementer's objections, for a fresh reviewer. Not a plan revision.
Plans under review: [delivery plan](delivery-plan.md) and
[test plan](test-plan.md), committed at `ec453bb`.

Each item states the requirement, why I object, and the smallest change that
would resolve it. Items are ordered by how much they can distort the build.

## 1. `%scope-30` — "All standard reads" is still not a closed, testable set

The goal is every official standard non-admin read for Jira 8.22, Confluence
6.6 and Bitbucket 5.10. The plans define evidence per operation and rules for
unresolved rows, but never freeze a concrete, versioned list of IDs that the
build must satisfy. The three mapping files disagree with each other and with
the SDK (`application-properties` is mapped yet excluded by the SDK; the
Bitbucket denominator omits its own semantic POST; Jira carries one uncertain
route).

Without a frozen denominator, "complete" remains a judgement, and two
implementers can both claim success with different surfaces. Prose rules like
"report exclusions separately" do not prevent that.

**Proposed:** a committed machine-readable manifest (one row per required ID:
product, method, route, response kind, exclusion reason) that the test suite
compares against the registry. Any ID present in the manifest but absent from
the registry fails the gate; any registry ID absent from the manifest is either
additive or a scope error.

**Question for the reviewer:** should the initial release deliberately ship a
smaller, frozen subset with the full inventory as a tracked backlog, instead
of claiming full coverage while it is still being filled in?

## 2. `%library-role-31` — The plans never decide which transport is canonical

The delivery plan says to use the pinned SDK for covered reads and one fixed
SDK fallback for gaps. At the same time the verified strict path in the
repository (`bearer_session` + `get_json_object` + shape validation) already
implements status handling, redirect refusal, size caps and per-route
validation, while the SDK path has open defects: it followed a redirect, lost
the final HTTP status on exhausted retries, and returned `None` for an empty
`200`.

The plans do not say which of the two wins, or whether both may coexist. That
choice decides retry semantics, error codes, and how many tests each route
needs.

**Proposed:** canonical reads use exactly one transport. Either (a) the strict
in-repo transport, with the SDK used only for high-level convenience calls
already proven safe, or (b) the SDK with an explicit subclass/session that
refuses redirects, owns retries, bounds reads and preserves status. Do not
ship both as equally supported paths for the same operation.

## 3. `%verify-32` — The plans promise detail the current CLI cannot yet supply

`--describe` must show defaults, bounds, allowed values, pagination guidance,
permission/version conditions, and a runnable example. The registry holds
types, patterns and query bounds, but no pagination guidance, permission
notes, or response-field descriptions. The plans treat that content as a
mechanical by-product of one registry; it is not present yet.

**Proposed:** define the minimum `--describe` payload that must be authored per
operation, and where it lives. Otherwise an implementer will either generate
thin, misleading descriptions or hand-write a second documentation store,
which the same plan forbids.

## 4. `%errors-33` — Exit codes and "always JSON" conflict at the edges

The plan states: canonical read and `--describe` always print one JSON
document, with `2` for usage/configuration and `1` for execution. But:

- Click emits its own text for unknown options and missing required
  arguments before any callback runs.
- `--catalog` is described as JSON with exit `0`, while `--describe` of an
  unknown ID is exit `2`. Both are eager group flags; the plan does not say
  which wins if both are supplied, or whether `--help` plus `--describe`
  should be an error.
- The plan excludes "process termination and broken stdout" from the JSON
  promise but does not say how a partially written document is signalled.

**Proposed:** state the one supported invocation shape (exactly one of
`--catalog`, `--describe`, `--help`, or a read command), what happens on
conflict, and either route Click parse failures through the JSON boundary or
explicitly document that argument-parsing text is outside the machine contract.

## 5. `%retry-34` — Numbers are set, provenance is not

The plan fixes three total attempts, five seconds cumulative wait, and
`Retry-After` honored only within budget. Those are reasonable defaults, but
the plan does not say whether they are measured requirements, guesses, or
inherited from the legacy transport. It also does not say which layer sleeps,
whether the connect timeout counts toward the wait budget, or how a
`Retry-After` in HTTP-date form is handled.

**Proposed:** label the numbers as chosen defaults, name the single owner, and
specify HTTP-date parsing, jitter, and whether retries apply to `--allow-http-loopback`
test targets identically.

## 6. `%binary-35` — Binary policy is specified but unowned

The plan requires declared binary kinds, base64 for small bodies, destination
plus receipt for large ones, no overwrite, no partial file, and cleanup on
failure. The registry today has no binary response kind, no destination
parameter, and no operation that uses it. The plan therefore specifies a
subsystem with no consumer yet.

**Proposed:** defer the binary contract to the first binary operation, with
only the safety invariants fixed now (no overwrite, no partial publish, no
link-derived destinations). Otherwise the implementer will build unused
machinery, which the plan elsewhere forbids.

## 7. `%setup-36` — Setup is required for handoff but has no acceptance owner

`atlawire auth login` is required for handoff but not for the first read slice.
The plan requires a browser launcher, hidden prompt, `GetPassWarning` failure,
atomic replacement, preservation of unrelated fields, and a synthetic test
harness. It does not say how the browser page is chosen per product/version,
who verifies it against a real deployment, or what happens when the product
offers only OAuth and not PAT.

**Proposed:** state the concrete supported setup methods per product for the
target versions, and mark any unsupported combination explicitly. A required
feature with unspecified product-level behavior will be implemented wrongly.

## 8. `%gates-37` — Release gates mix evidence and judgement

The test plan requires a full offline suite, a wheel install, real-server
proof, and a sensitivity receipt. It does not define pass thresholds for
"complete coverage": must every required ID have a live check, or is one live
check per adapter kind plus per-ID loopback acceptable? Both readings appear in
the text.

**Proposed:** one sentence per gate stating exactly what evidence closes it and
what may remain inconclusive without blocking, plus who accepts the residual
risk.

## 9. `%catalog-38` — Two catalogs, unclear canonical surface

The plan keeps the existing Click `commands` metadata and adds an `operations`
list, while also requiring product help groups (`atlawire bitbucket repository
get --help`). That is three discovery surfaces (help tree, command catalog,
operation list) over one registry. The plan does not say which one an agent
should prefer, or which is authoritative when they disagree.

**Proposed:** name the authoritative discovery surface, make the others
explicit projections of it, and state the precedence rule when the generated
help and the operation list disagree.

## 10. `%testscope-39` — "Prove the test can fail" is unbounded

The fault table requires a failing pre-fix run for each critical boundary, but
some behaviours have no runnable pre-fix state and the plan allows a
"controlled faulty variant" in an approved isolated copy. It does not say who
approves that copy or how the variant is kept out of the delivered tree.

**Proposed:** fix the approval and location for temporary faulty variants, and
state that only the surviving regression is delivered, with its failing-run
evidence stored outside the production tree.

## 11. `%docs-40` — Documentation obligations are spread and duplicated

The plans require README, quickstart, `--help`, `--describe`, `--catalog`, a
shipped short guide, and per-operation descriptions. Several of these repeat
the same facts. The plan forbids "a second hand-maintained catalog" but does
not say which document owns setup, which owns error codes, and which owns
per-operation semantics.

**Proposed:** assign one owner per fact and make everything else a projection
or a link, so drift is detectable rather than merely discouraged.

## 12. `%dates-41` — The plans still read as time-boxed

"Today", "first useful checkpoint", and "to meet a date" appear in the delivery
plan. The same document says date pressure must not lower acceptance criteria.
Leaving scheduling language in an engineering contract invites shortcuts.

**Proposed:** remove the scheduling sentences or move them to a separate
status note, so the plan contains only gates and evidence.

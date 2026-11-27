# Tester pass — task-first review, 2026-11-27

Asked as a user: *«I ask the library a question and I want the answer, cheaply.»*
Load assumed: one agent, one task at a time, one self-hosted deployment.

Measured with the live CLI on the configured deployment; sizes are stdout bytes.
Content was never printed, only sizes, counts and key names.

## The owner's own example, end to end

«Which repositories use X, where is the query manager described, which tickets
touch it, who did it, where is the documentation».

| Step | Command | Bytes |
| --- | --- | --- |
| where it is mentioned | `find <term> --limit 5` | 4 836 |
| where the code is | `repo-search <term> --json` | 46 878 |
| projects | `repos AB --limit 100 --json` | 772 |
| tickets | `jql 'text ~ "…"' --limit 20 --json` | 5 654 |
| who did it | `commits AB/<slug> --limit 20 --json` | 8 005 |
| documentation | `cql 'text ~ "…"' --limit 10 --json` | 1 859 |
| the ticket | `issue <KEY>` | 12 617 |
| ticket history | `issue-changelog <KEY>` | 859 |

**8 calls, 81 KB**, assembled by the caller. There is no single "tell me about
X" command — and that is the correct design: the four discovery calls are
independent, so an agent runs them in parallel, whereas one command would run
them in sequence. The recipe is now in `docs/AGENT-SKILL.md`.

## Fixed in this round

| Finding | Before | After |
| --- | --- | --- |
| `jql --json` dropped the server's `total` | 3 rows, no total, looked complete | `{"rows", "truncated", "total": 1740}` + stderr note |
| `--json` silently ignored beside `--fields` | object envelope, flag meaningless | exit 2 with the reason, before any request |
| `--catalog` as the documented starting point | 271 872 B | `--catalog --brief` 35 143 B |
| `search --json` context dominance | 69 390 B (context 62%, hits 36%) | `--context 0` 27 649 B, `--context 1` 29 278 B |
| stale `202 операции` in `AGENT-SKILL.md` | wrong count | 317 |

## Still open (not fixed this round)

| Finding | Evidence | Why not fixed |
| --- | --- | --- |
| `operations` (345 KB) has no brief form | one call, 34 326 words | `--catalog --brief` covers discovery; `--describe <id>` covers one operation. Revisit only if it is actually reached for. |
| `issue` is 12 617 B by default, 473 B with `--fields summary` | 27× | both forms exist and the cheap one is now documented; changing the default would break callers that want the card |
| argument conventions differ between commands | `repository AB slug` vs `pr AB/slug 7`; 4 of my 8 first attempts were usage errors | changing a public CLI shape is a breaking change; the convention table is in the skill table instead |
| `repo-search` default 200 rows | 46 878 B; `--limit 1` is 750 B | the flag exists; defaults are a product decision |
| no Confluence page-attachment download | reported in `.config/feedback/2026-11-27-confluence-attachment-download.md`; WADL has no documented download route | needs a BBK-observed route and the same proof the Bitbucket one carries, not a guess |

## Test-harness defect found while testing (mine, not the product's)

Several of my loopback fixtures answered a POST without reading the request
body. On Windows that resets the connection, which surfaced as an intermittent
`Request failed; check connectivity and TLS settings.` attributed to the product.

Isolation: the product's own transport passed 30/30 attempts against a single
server, `search_code` 10/10 on a fresh server, and plain `requests` 30/30 — so
the churn was the harness. All such fixtures now read the body first, and the
suites were repeated three times to confirm stability.

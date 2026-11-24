# repo-search live report — 2026-11-24

One self-hosted Bitbucket Server 5.10 deployment, read-only, one project, one
query (`class`). Aggregates only; no payloads, hosts, or identifiers.

Command shape:

```python
search_repositories(
    base_url,
    "class",
    token=...,
    project=PROJECT,
    engine=...,
    fetch=...,
    limit=200,
    max_repos=...,
    path_glob="*.java",
)
```

| Engine | Fetch | Rows | Repos in result | Repos scanned / total | Files scanned | Seconds |
|---|---|---|---|---|---|---|
| index | — | 200 | 6 | 6 / 6 | 200 | 1.3 |
| bytes | files | 200 | 2 | 4 / 7 | 216 | 27.6 |
| bytes | archive | 200 | 2 | 3 / 7 | 179 | 10.0 |

Observations:

- All three modes returned the 200-row cap, so `status="truncated"` and
  `complete=false` in every run, as documented.
- Both `bytes` modes returned matches from at least two repositories, which is
  the cross-repository requirement.
- Archive mode was about 2.8× faster than per-file reads on the same bounded
  scope (10.0 s vs 27.6 s), at the cost of one larger response per repository.
- The index engine reports the repositories present in its results
  (`repositories_total` = 6), not the project inventory; the bytes engines
  report the enumerated inventory (7).

Limits of this evidence: one deployment, one query, one project, default branch
only. It does not prove other versions, permissions, or larger scopes.

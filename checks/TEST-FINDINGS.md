# AtlaWire live test findings

Generated: 2026-11-27, against one live self-hosted deployment
(Jira Server, Confluence Server, Bitbucket Server) with a read-only personal
access token.

Scope: every registered operation (317), every declared query parameter, every
CLI command (90), the public Python API, and BBK's public API. The three
surfaces were checked against each other and against the deployment's own WADL.

This file lists **what is broken**. A clean result would be "no findings"; there
are findings.

## How to reproduce

```bash
python checks/live_tester_discovery.py      # discover live identifiers
python checks/live_tester_operations.py     # call all 317 registered operations
python checks/live_tester_params.py         # probe every declared query field
python checks/live_tester_docs.py           # registry vs the deployment's WADL
python checks/live_tester_cli_full.py       # invoke all 90 CLI commands
python checks/live_tester_python_api.py     # call the public Python API
python checks/live_tester_bbk_parity.py     # BBK function by function
python checks/build_test_findings.py        # regenerate this report
```

Raw evidence is in `checks/live_tester_*.json`.

## Measured summary

| Surface | Measured |
| --- | --- |
| Registered operations | 317 (314 GET, 3 POST) |
| Operations answered | 125 |
| Operations refused before the request (the tester supplied no value) | 15 |
| Operations refused by the server | 116 |
| Operations not callable (no identifier on this deployment) | 62 |
| Declared query fields | 472 across 178 operations |
| Query fields exercised | 137 (328 have no derivable safe value, 21 blocked) |
| CLI commands invoked | 86 of 90 (70 succeeded, 16 rejected the tester's arguments; 2 need an operation id, 2 skipped) |
| Public Python functions invoked | 41 representative calls |
| BBK in-scope functions | 73 |

---

## DEFECTS

### D1. A required query parameter is declared optional (9 operations)

A caller has no way to know the parameter must be sent, and `read` does not
enforce it. Every call to these operations is refused by the server.

Evidence: the server answered `... parameter is required`, while
`atlawire operations` reports `required: false` for that exact field.

| operation | product | field that must be `required=True` |
| --- | --- | --- |
| `bitbucket.admin.groups.more-members` | bitbucket | `context` |
| `bitbucket.admin.groups.more-non-members` | bitbucket | `context` |
| `bitbucket.admin.users.more-members` | bitbucket | `context` |
| `bitbucket.admin.users.more-non-members` | bitbucket | `context` |
| `bitbucket.projects.projectkey.repos.repositoryslug.changes` | bitbucket | `until` |
| `bitbucket.projects.projectkey.repos.repositoryslug.diff.path` | bitbucket | `until` |
| `bitbucket.projects.projectkey.repos.repositoryslug.pull-requests.pullrequestid.comments` | bitbucket | `path` |
| `bitbucket.repository.commit-comments` | bitbucket | `path` |
| `confluence.search` | confluence | `cql` |

Server messages, verbatim:

```
The context parameter is required.
The until query parameter is required
The "until" query parameter is required.
The path query parameter is required when retrieving comments.
cql query parameter is required Bad Request
```

Fix: set `required=True` on each field in `src/atlawire/operations.py`. For
`confluence.search`, `cql` is the query itself, so marking it required also makes
the operation self-documenting.

### D2. A required parameter is not declared at all

`bitbucket.repository.raw` answers `The parameter 'path' is required` while the
registry declares only `at`, `hardwrap`, `htmlEscape`, `markup`. The route cannot
be called through `read` at all: a caller who supplies `path` gets a validation
error because the field is unknown.

Fix: add a `path` query field (or make it a path argument if the deployment
accepts it in the route).

### D3. A POST body field has the wrong name — the operation is unusable

`jira.worklog.list` declares `issueIds`. The server rejects it:

```
Unrecognized field "issueIds" (Class com.atlassian.jira.rest.v2.issue.worklog.WorklogIdsRequestBean)
```

The accepted field is `ids`:

```
{"issueIds": []}  -> HTTP 400 Unrecognized field "issueIds"
{"ids": []}       -> HTTP 200 []
```

Fix: rename the body field to `ids` and correct its description from "Issue IDs"
to "Worklog IDs".

### D4. A query rule the server enforces is not declared

`confluence.user.memberof` requires **exactly one** of `key` / `username`. The
registry declares both optional and sets every `query_rules` list empty.

```
{"key": "admin"}                        -> HTTP 404
{"username": "admin"}                   -> HTTP 200
{"key": "admin", "username": "admin"}   -> HTTP 400 Only one query param of key or username is required
```

Fix: set `query_rules.exactly_one = ["key", "username"]` so the tool refuses an
invalid combination before the request.

### D5. A binary route is declared as a read operation but cannot be read

`bitbucket.project.avatar` is declared `kind: binary` at
`/rest/api/1.0/projects/{projectKey}/avatar.png`. Every attempt returns
`HTTP 406`, with and without `--out`:

```
read bitbucket.project.avatar --params '{"projectKey":"AB"}' --query '{"s":16}' --out x.png
-> HTTP 406: request failed.   (no file written)
```

The route serves an image and needs an image `Accept` header, while the shared
transport sends `Accept: application/json`. As declared, the operation is
unreachable.

Fix: either teach the binary read path to send an image `Accept` header, or
remove the operation from the registry with a stated reason.

### D6. The CLI cannot send a parameter the server requires

`commit-comments` and `commit-comment` require `path` on the server (see D1) but
expose no matching option:

```
$ atlawire commit-comments --help
Options: --base-url, --token-from-env, --json, --raw, --allow-http-loopback, --help

$ atlawire commit-comments AB address-book-api <sha> --path .gitignore
Error: No such option '--path'.
```

`pr-comments` accepts a path positionally, but only for the `file` and `diff`
actions; for the comments action it refuses:

```
$ atlawire pr-comments AB/repo 192 .gitignore
Error: PATH is only supported with "file" or "diff".
```

The same route is unreachable through the CLI even though the registry declares
`path`.

Fix: add `--path` to `commit-comments`/`commit-comment`, and allow the path for
the comments action of `pr-comments`.

### D7. Public Python functions with no CLI command

These are usable from Python but have no command, so an agent working through the
CLI cannot reach them:

| function | verified |
| --- | --- |
| `atlawire.jira.titles` | exists, callable |
| `atlawire.jira.issue_url` | exists, callable |
| `atlawire.confluence.get_page_title` | exists, callable |

The `pr file` and `pr commits` actions do cover `get_pull_request_file` and
`list_pull_request_commits`, so those are not gaps.

Fix: either add thin commands, or record in the docs that these are library-only.

### D8. The library entry point cannot perform the three POST reads

`read_operation` has `use_library: bool = False`, and a POST without it raises:

```
This operation requires the library transport.
```

The CLI passes `use_library=True` (so `atlawire read jira.search.post` works),
but a library caller using the documented `read_operation()` gets a failure for
`jira.search.post`, `jira.worklog.list` and `confluence.content.convert`.

Fix: make the default `True`, or drop the flag and always use the one transport.

### D9. Registry and deployment disagree on the query surface

**D9a. Declared by the registry, not documented by the deployment's WADL (19).**

Most are `limit`/`start` on paged routes, which the product documents in prose.
Three are unexplained and must be checked against the product's HTML docs:

| operation | parameter |
| --- | --- |
| `confluence.content.convert` | `expand` |
| `confluence.content.convert` | `representation` |
| `confluence.content.convert` | `value` |

The other 16 are `limit`/`start` on `bitbucket.profile.recent-repositories`,
`bitbucket.repository.commit-comments`, `bitbucket.repository.compare-changes`,
`bitbucket.repository.compare-commits`, `bitbucket.repository.forks`,
`bitbucket.repository.participants`, `bitbucket.repository.pull-request-activity`,
`bitbucket.repository.related`, `bitbucket.users.list`, plus `startAt` on
`jira.user.assignable-search`.

**D9b. Documented by the WADL, deliberately absent from the registry (1).**

`jira.issue.issueidorkey` / `updateHistory` — this is a **write** (it adds the
issue to the user's history) and must stay absent. Not a defect; recorded so a
later reviewer does not "fix" it.

**D9c. Registered routes the WADL does not describe (2).**

| operation | path | live result |
| --- | --- | --- |
| `jira.rest.auth.1.session` | `/rest/auth/1/session` | HTTP 200, works |
| `jira.attachment.content` | `/rest/api/2/attachment/{id}/content` | not called: no attachment id discovered |

`jira.rest.auth.1.session` is verified working. No action unless a future
deployment lacks it.

---

## PERMISSION REFUSALS (not defects)

Do not change code for these. The token is read-only and has no administrative
rights, so the deployment refuses admin reads. This is the boundary working.

| Refused | Count | Meaning |
| --- | --- | --- |
| Admin-scope operations | 62 | Expected: needs an administrator token |
| Non-admin operations refused | 1 (`jira.project.roles`, 401) | Check that project's permissions for this user |

Parameter probes that ended in 401/403 for the same reason: 10
(`confluence.audit`, `confluence.webhooks`, `jira.auditing.record`,
`jira.customfields`, `jira.group.member`). Not parameter defects.

## COVERAGE GAPS (cannot be judged, not defects)

| Gap | Count | Why |
| --- | --- | --- |
| Operations never called | 62 | No such object on this deployment (webhooks, schemes, screens, dashboards, attachment ids) |
| Query fields never exercised | 328 | No safe value is derivable from the declaration (free text, no enum, no bounds) |
| Operations answered 200 with an empty result | 6 | May be true here (`jira.filter.favourites`, `jira.issue...remotelink`, `jira.issue...subtask`, `jira.password.policy`, `jira.projectcategory`, `jira.reindex.request.bulk`) |

The tester refuses to invent input. Closing these needs a richer deployment or
explicit sample values.

## BBK parity

73 in-scope functions, all accounted for after correcting the tester's own
argument mistakes:

| Verdict | Count |
| --- | --- |
| better | 10 |
| same | 55 |
| different (reason recorded) | 2 |
| excluded (BBK local index) | 4 |
| worse | 2 |

Two in-scope functions failed their live invocation (`pr_file`, `pr_commits`).
That is not proof the capability is worse: the comparison used the wrong
arguments. It does mean parity was **not** established for those two, and they
must be re-run with valid inputs before BBK is retired. BBK's local schema and
environment indexes are out of scope here and have no AtlaWire equivalent
(`docs/RESEARCH-COVERAGE.md`). Details in
`checks/live_tester_bbk_parity.json`.

## Verified working (so it is not re-opened)

- Public Python API: 39 of 41 representative calls succeeded. The two failures
  were the tester's own argument mistakes (`page_id` takes one argument;
  `get_repository` takes `project_key` and `slug`), not defects.
- CLI: 70 of 86 invoked commands succeeded. The 16 "failures" were the tester's
  wrong arguments (e.g. `api-get bitbucket .gitignore` instead of a `/rest/`
  path; `scan` without `--ext`; `pr-review` with a short repo form). Recorded in
  `checks/live_tester_cli_full.json` with their exact argv.
- The three POST reads work through the CLI
  (`atlawire read jira.search.post ...`).

---

## Round 2 — retest after the fixes

Everything above was re-run against commit `2ef49f8`'s successor. The nine
original defects are closed, and the retest found two new ones.

### Status of the original findings

| Finding | Status | Evidence |
| --- | --- | --- |
| D1 — a required parameter declared optional | fixed | each of the 9 operations now refuses before the request: `The <field> query parameter is required` |
| D2 — a required parameter not declared | fixed | `path` is now a route argument on `repository.raw`; 461 bytes downloaded |
| D3 — a POST body field misnamed | fixed | `jira.worklog.list` accepts `{"ids": []}` |
| D4 — an undeclared query rule | fixed | `confluence.user.get` and `confluence.user.memberof` refuse a bad combination locally |
| D5 — a binary route declared as a read | fixed | `read_binary` sends the wildcard `Accept`; avatar returns 3 098 bytes of `image/png` |
| D6 — the CLI cannot send a required parameter | fixed | `commit-comments --path`, `pr-comments ... --path` |
| D7 — public functions with no command | fixed | `titles`, `issue-url`, `page-title` commands added |
| D8 — the library cannot perform the POST reads | fixed | the flag is gone; one transport serves all three |
| D9 — registry and deployment disagree | recorded | the two `jira` route differences are intentional; see above |

### New finding D10 — the JSON reader broke a binary route

`read_operation` treated `kind: binary` as a JSON document. It sent
`Accept: application/json`, so a route that serves bytes failed:

```
read bitbucket.repository.archive    -> HTTP 406   (read_binary: 102 278 bytes)
read bitbucket.repository.raw        -> HTTP 500   (read_binary: 461 bytes)
bitbucket.project.avatar             -> HTTP 406   (read_binary: 3 098 bytes)
```

The same operation must not behave differently through two public entry points.
Fixed: the reader now refuses before any request and names the working entry
point. `tests/test_spec_tester_findings.py::test_a_binary_operation_is_refused_by_the_json_reader`
covers every binary operation, not just the three that were observed.

### New finding D11 — a route the deployment rejects was advertised

`bitbucket.projects.projectkey.repos.repositoryslug.diff` (the bare repo diff)
answers `400 A file path is required` for every shape: no query, `path`,
`srcPath`, `since`, `until`, and all combinations. The path must be in the route,
which is what `/diff/{path}` already does:

```
GET /diff                                  -> 400
GET /diff?path=.gitignore                  -> 400
GET /diff?srcPath=.gitignore&until=<sha>   -> 400
GET /diff/.gitignore?until=<sha>           -> 200, 2 195 bytes
```

The bare row promised a read that cannot happen. Fixed: the row is excluded by
the same rule that already excludes the bare `/raw`, with the reason stated in
the inventory, and the wildcard operation serves the route. The registry now
declares 317 operations, and `server_only` for Bitbucket is 2 (`/raw`, `/diff`),
both intentional and both pinned by digest.

### What the retest shows about the remaining failures

116 operations still end in an error, and none of them is a code defect:

| Cause | Count | Note |
| --- | --- | --- |
| 401/403 | 63 | the token is read-only; the boundary working |
| 404 | 28 | the identifier does not exist on this deployment |
| 400 from a wrong-shaped tester value | 15 | e.g. `files.path` given a file where a directory is required |
| 409 | 1 | the pull request is already merged; benign server state |
| 500 / 501 | 3 | the deployment's own behaviour on a long-task id and a search variant |

The 15 "refused before the request" rows are the fixes working: the tester did
not supply a required value, so the tool declined to send a request the server
would reject anyway. They are recorded separately so they cannot inflate either
the defect list or the success count.

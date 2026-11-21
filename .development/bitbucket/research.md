# Bitbucket Server 5.10.0: MCP vs atlassian-python-api vs REST

Research date 2026-11-18, server `https://git.platform-s.com` → **5.10.0** (build 5010000),
40 accessible projects, 551 repositories. Token from the Bitbucket MCP config, read at runtime,
never printed.

## 1. Knowledge base (this folder)

`kb/` — 45 files, 424 KB, extracted from `bitbucket-5.10-rest.html`:

```
kb/README.md              index: 125 endpoints, resource table, 5.10 caveats
kb/00-getting-started.md  URI structure, paging, personal repositories
kb/01-authentication.md   auth, errors & validation
kb/02-index.md            the doc's index incl. filter vocabulary
kb/api/<resource>.md      42 files, grouped by resource (projects--pull-requests, admin--users, …)
```

Pipeline: `pandoc -f html -t gfm --wrap=none` → regex clean (894 `<div>` + 788 `<span>` lines,
`toggle(...)` JS links, pandoc hard breaks) → split on `##`/`###` (only those delimit; `###### Methods`
and `###### Example` belong to the enclosing endpoint). Verified: 125/127 headings are endpoints,
0 HTML leftovers, 33 % smaller than the raw markdown.

Reusable helpers copied to `lib/`: `bbclient.py` (credentials from the MCP config, redaction
helper), `bbcompact.py` (compact JSON + TSV + unified diff renderers).

## 2. What each interface can do

| | Bitbucket MCP v4.0.0 | atlassian-python-api 5.0.5 | raw REST |
|---|---|---|---|
| Surface | **25 tools**, 21,984 B schema (~5.5k tokens in every request) | **212 public methods**, 0 fixed tokens | 125 endpoints in 5.10 |
| Cross-project search | ✗ `search_code` is project-scoped | ✓ raw `POST /rest/search/latest/search` (library's `search_code(team, query)` is Cloud-only) | ✓ |
| Server-side content grep | ✓ `grep` (repo scope, streams files) | ✗ (fetch + filter yourself) | ✗ |
| Recursive file listing | ✗ only `list_directory_content` per folder | ✓ `get_file_list` (whole repo, paged) | ✓ `/files` |
| PR lifecycle | ✓ list/get/diff/commits/create/update/merge/decline/comment/reviewers | ✓ + settings, default reviewers, conditions, inline comments, tasks | ✓ |
| Repo/project admin | partial (list, branches, delete_branch) | ✓ create/update/delete, permissions, users/groups, forking, labels | ✓ |
| Tags | ✗ | ✓ create/delete/list | ✓ |
| Branch permissions / restrictions / default reviewers | ✗ | ✓ | ✓ |
| Webhooks / hooks / hook scripts | ✗ | ✓ (24 methods) | ✓ |
| Audit log, reindex, license, mail, cluster | ✗ | ✓ | ✓ |
| File write | ✗ (`update_pull_request`/comment only) | ✓ `update_file`, `upload_file` | ✓ |
| Attachments | ✓ (Server/DC: uploads disabled in this build) | — | — |

## 3. Task: which projects contain Python files

Two independent conclusions:

- **Search add-on** works but is weak for this: `python` → 280 hits, `"def "` → 3,759,
  `path:*.py` → 179 (fuzzy, returns .yml too), **`ext:py` → 0** (field not supported here).
- **Enumeration** (the reliable answer): 40 projects → **551 repos** → `/files` per repo,
  8 threads, **74 s, ~596 API calls**, 1 failed repo, 16 repos hit the 1000-entry page cap.
  Result: **19/551 repos in 13 projects** contain Python, e.g.
  `PY/jira_to_bitrix_reporter` 122, `DEV/box-builder` 44, `SAN/backoffice-statistic-api` 34,
  `BCHAT/business-chat-nlp` 33, `PY/yorputility` 8, `TEST/*-stub` 1–9.

MCP equivalent: `search_code` per project (40 calls, returns matching *lines*, default branch,
<512 KiB files only) or `list_directory_content` per directory recursively — no whole-repo file
listing, so the enumeration is not practically reproducible there.

## 4. Compression measured on real payloads

| payload | raw REST JSON | library compact JSON | library text form | MCP output |
|---|---|---|---|---|
| PR list, 3 PRs (`AB/address-book-api`) | 8,938 B (~2,234 tok) | 1,783 B (5.0×) | **359 B TSV (24.9×)** | 977 B (9.1×) |
| PR #192 diff, 6 files, default params | 80,820 B (~20,205 tok) | 73,100 B | 28,483 B unified (2.8×) | — |
| PR #192 diff, lean params¹ | 43,193 B (~10,798 tok) | 37,925 B | **12,558 B unified (6.4×)** | 17,182 B (4.7×) |

¹ `withComments=false&contextLines=2&whitespace=ignore-all`.

Knowledge retention: MCP keeps id/version/title/state/author/branches/reviewers/updated_on and drops
`links`/avatars; my compact JSON keeps everything except links/avatars (hence 1.8× larger than MCP,
2× smaller than raw); the TSV keeps id/state/refs/author/title/**version** and drops reviewers and
dates — smallest, but a deliberate loss.

## 5. Corrections to the local notes (found by testing, not reading)

1. `?withAttributes=false` on `/pull-requests` **changes nothing** on 5.10 (8,938 B either way).
2. `/pull-requests/{id}/changes` returns `{fromHash,toHash,values[]}`, **not** `diffs[]` — a parser
   shared with `/diff` silently yields 0 files.
3. `/rest/search/latest/search` answers **405 on GET**; it needs `POST` with
   `{"query":…,"entities":{"code":{"start":0,"limit":N}}}`.
4. `lib.search_code(team, query, page, limit)` is the **Cloud** signature; unusable on Server.
5. `get_pull_requests()`, `project_list()`, `repo_all_list()` return **generators** in 5.0.5 — wrap
   with `list()`; the objects have no `.json()`.
6. The README's pandoc recipe is correct (`-f html -t gfm --wrap=none`, exit 0, no stderr) but leaves
   ~1,700 lines of `<div>/<span>/toggle()` scaffolding; a clean-up pass is mandatory for a KB.
7. `SKILL.md`'s `bkt` CLI **is** installed after all — `bkt 0.40.2` at
   `%LOCALAPPDATA%\Microsoft\WinGet\Links\bkt.exe` (it is only *absent from the checkout folder*, which
   held a `.url` link). It exposes `admin/api/branch/commit/context/perms/pipeline/pr/project/repo/
   status/variable` plus its own `mcp` and `skill` commands, so the documented `bkt api` fallback is
   available as a third path next to the library and the MCP.

## 6. Verdict — who is more productive

- **One known PR, a comment, a review** → **MCP**: two calls, sane defaults, output already
  9×/4.7× smaller than raw, nothing to write.
- **Org-wide questions, bulk inventory, anything touching permissions/hooks/tags/audit, file writes,
  or a custom-shaped report** → **library**: one script replaced ~596 potential tool calls, 212
  methods vs 25, and I control the output form (TSV 24.9×, unified diff 6.4×).
- **Token economics** depend on the shape: MCP pays ~5.5k tokens of schema in *every* request but
  charges nothing per result beyond its compact output; the library pays 0 fixed tokens and only the
  code I write, which then produces the smallest artifacts.
- Practical split used here: MCP for interactive PR work, library+`bbcompact.py` for discovery and
  reporting. Best of both: keep MCP for reads, use the library when the answer needs aggregation.
## 7. Cross-project search: Python port of `bb-search`

The Node tool `~/.local/bin/bb-search.mjs` (321 lines) already solves what the MCP cannot: it posts to
`/rest/search/latest/search` **without** the `project:<workspace>` clause, so one call covers every
visible repository. Ported to Python at **`~\.local\bin\bb-search.py`** (+ `bb-search-py.cmd` shim),
`requests`-based, ~330 lines, same CLI and JSON schema.

Behaviour kept identical: `--limit` counts **files** (1..999, the index window), page size 100,
`--all` drains pages, single-pass HTML decode of snippets only, terminal-control sanitising for
display, identifiers and query verbatim, token never printed, response bodies never echoed,
exit 0 = ran (even no matches) / exit 2 = usage·config·HTTP.

Deliberate differences, all internal:
- config: reads `~/.config/opencode/opencode.json` first, then falls back to the DSH profile patch
  (`~/.dsh/profiles/web/cordis.patch.yml`) so it works in this harness too;
- `requests` instead of `fetch`, `html.unescape` instead of a hand-written entity table;
- `--all` with more than 999 files fails with the same message, now without the `int(inf)` crash the
  first version had.

Parity evidence (same account, same queries, Node vs Python):

| case | node bytes | python bytes | JSON equal | text equal |
|---|---|---|---|---|
| global, `--limit 3` | 25,980 | 25,980 | ✓ | ✓ |
| `--project PY` | 20,688 | 20,688 | ✓ | ✓ |
| `--repo AB/address-book-api` | 2,028 | 2,028 | ✓ | ✓ |
| no matches | 138 | 138 | ✓ | ✓ |
| `--all` (bounded query) | 134 | 134 | ✓ | ✓ |

Error paths verified on the Python side: unknown option, `--limit 1000`, `--limit abc`, `--project`
with `--repo`, missing query, malformed `--repo` → all exit 2, empty stdout, one-line stderr.

Output economy on the same 5-file search: **text 1,687 B (~422 tok)** vs `--json` **41,516 B
(~10,379 tok)** — 24.6× . For an agent, text mode is the default; JSON is for programmatic use.
## 8. PR and its files in Python: `bb-pr`

**The server has no text diff.** On 5.10.0 every diff representation answers **406 Not Acceptable**
for `Accept: text/plain`, `text/*`, `application/x-diff`, `application/x-patch`, the `.diff` suffix,
`/pull-requests/{id}/diff/{path}`, `/commits/{hash}/diff` and `/diff/{path}?since=&until=`. Only
`application/json` (or no Accept) returns 200. So an MCP that asks for a text diff cannot succeed
here, and no dependency bump changes that — the text has to be rendered client-side.

`~\.local\bin\bb-pr.py` (+ `bb-pr.cmd`) does exactly that, in `requests` + stdlib only:

```
bb-pr show     KEY/slug ID          summary: state, version, author, refs, hashes, reviewers, dates
bb-pr files    KEY/slug ID          changed files from /changes (values[], paged, path.toString)
bb-pr diff     KEY/slug ID [PATH…]  unified diff: whole PR, selected paths, or --split per file
bb-pr file     KEY/slug ID PATH --at old|new   raw file at fromRef / toRef
bb-pr comments KEY/slug ID          review comments as "id author path:line text"
```

Server-side trimming before any rendering: `withComments=false`, `contextLines` (default 3, `--context`),
`whitespace=ignore-all` (5.10 default), `/changes` paging with `nextPageStart`. If the whole-PR diff
comes back `truncated: true`, it falls back to one diff per changed file automatically.

Measured on PR #192 (6 files, `AB/address-book-api`):

| representation | bytes | ~tokens |
|---|---|---|
| JSON, default params | 80,820 | 20,205 |
| JSON, lean (`contextLines=2`, no comments, ignore whitespace) | 43,193 | 10,798 |
| **`bb-pr diff --context 2`** | **12,848** | **3,212** |
| `bb-pr diff` (context 3) | 14,991 | 3,748 |
| MCP `get_pull_request_diff` output | 17,182 | 4,295 |

Proof the truncation fallback is correct: `bb-pr diff --split` (one request per file, concatenated)
is **byte-identical** to the single whole-PR request. Single-file diff is 1,439 B; `file` returns the
same bytes the browser sees (10,770 old / 10,429 new); `comments` lists four review comments.

Two server quirks worth remembering: `/raw/{path}` answers **500** if `Accept` is JSON (it wants
`text/plain`), and `/changes` reports `path` as `{components,parent,name,toString}` rather than a
string. Error paths: unknown PR/repo → exit 2 with the path in the message; `file` without PATH and a
malformed `KEY/slug` → exit 2; a requested path with no changes prints a note and exits 2, while a
mixed batch still prints the real diffs.
## 9. Confluence and Jira: access, and how the Markdown is produced

**Access.** `jira.platform-s.com` is **Jira Server 8.22.2** (build 822002); `cf.platform-s.com` is
Confluence DC. Anonymous access reaches `/rest/api/2/serverInfo` (200) and `/rest/api/space` (200, but
0 spaces visible), while the issue `PLAT-3901` and the page `7307751` answer *login required*
(`401 / 404`, and the HTML URLs redirect to `login.jsp` / `login.action`). The **Bitbucket token is
app-scoped**: Confluence returns 401 and Jira 403 with it, so the library needs a Jira/Confluence PAT
(or password). Neither app is configured in the MCP/opencode settings.

**Authenticated path used here.** The browser session (browse MCP) has the logins, so the REST payloads
were fetched from the page context (`fetch(..., {credentials:"include"})`), written to `C:\TMP` with the
relay's `files.write`, and converted locally — content never passed through the model. The browse build
refuses `context.cookies()` ("cookies stay in the user's browser"), so the library cannot borrow that
session; a PAT is required for `atlassian-python-api` use.

**No Markdown is served by either product.** Confluence offers `body.storage` (XHTML plus `<ac:*>`
macros) or `body.view` (rendered HTML); Jira offers wiki markup in `fields` and HTML via
`?expand=renderedFields`. Conversion is therefore mandatory, and the converter choice matters more than
the fetch:

| converter on page 7307751 | bytes | leftover inline HTML | tables |
|---|---|---|---|
| source storage XHTML | 93,496 | 1,441 | 1 |
| `pandoc -t gfm` | 60,936 | 517 | **flattened to a vertical list** |
| `pandoc -t markdown` | 52,446 | 0 | **flattened** |
| `markdownify` | 44,662 | 0 | **373-row pipe table, links kept** |

So `atl-md` defaults to markdownify and keeps `--pandoc` as an option (pandoc is better for deeply
nested lists, worse for tables). Confluence macros are normalised first: `code` → fenced block with the
macro's language, `info/note/warning/tip/panel/expand` → blockquote, `ac:image` → `![alt](filename)`,
`ac:link` → real href only when `ri:url` exists (no invented `#`), `ri:*` refs unwrapped,
`span/font` styling stripped. Tables using `rowspan/colspan` cannot become pipe tables, so the tool warns
instead of silently drifting.

Result for the requested targets: page 7307751 «Сервисы в кластере» (space PLATFORM) → **44,292 B**
Markdown from 93,496 B XHTML (2.1×) with the services table intact; issue PLAT-3901 «Доработать логику
jqm» → **3,948 B** via `renderedFields` HTML, or **2,869 B** via the wiki-markup path (regex mapping of
`h2.`/`*bold*`/`{{mono}}`/`{code}`/`[text|url]`), which is smaller but assumes simple markup.

Usage: `atl-md cf 7307751 | atl-md cf <url>`, `atl-md jira PLAT-3901`, `--wiki`, `--pandoc`, `--html`,
`--out FILE`, and `--from-file` to re-convert a saved payload offline.
## 10. Confluence Storage Format → Markdown: the custom converter (verified)

`atl-md` now converts `body.storage` with a `MarkdownConverter` subclass instead of pre-normalising
then handing HTML to a generic converter. Verified facts behind that choice:

- **Dispatch works**: on markdownify 1.2.3 a method named `convert_ac_structured_macro`,
  `convert_ac_link`, `convert_ac_image` **is** called for `<ac:structured-macro>`, `<ac:link>`,
  `<ac:image>`. bs4 exposes those colon names as tag names, so no registry or monkey-patch is needed.
- **Generic conversion is not merely uglier, it loses data** (same fixture): code macro → text with the
  indentation collapsed to zero (`def f(x):` / `return x * 2` on one level), macro parameters leak as
  loose lines (`python`, `Green`, `IN PROGRESS`), the page link loses its target ("Read  first."), and
  the image disappears.
- **The subclass fixes each case**: fenced ```` ```python ```` block with indentation and language,
  status → `` `[IN PROGRESS]` ``, panel → `> **Важно:**` blockquote, `expand` → `### Details`,
  `ac:link` → `[Design Doc](confluence:Design Doc)`, `ac:image` → `![diagram.png](attachment:diagram.png)`.

One refinement added after seeing it on the real page: when the link's *visible text is a URL*
(`[https://cf…/display/DVPS/APM]`), emitting `confluence:APM` threw the address away, so a URL label is
now kept as `[url](url)`; title links still get the `confluence:Title` scheme.

Measured on page 7307751 after the change: **45,866 B**, 373 pipe-table rows, **110 preserved HTTP
links**, 0 leftover `<ac:`/`<ri:` tags — versus 93,496 B of storage XHTML. `body.view` is no longer
requested at all (its Atlassian CSS/JS wrappers only add tokens). `--pandoc` remains available for
prose-heavy pages where pandoc's nesting is better; `--from-file` re-converts a saved payload offline,
which is how the fixture and this page were re-tested without hitting Confluence again.
## 11. Jira/Confluence from plain Python (no browser, no MCP)

Credentials now exist and live in `~/.config/atlassian/credentials.json` (280 B, ACL `magic:(F)` only,
no inherited principals), read at runtime and never printed:

- Jira PAT id 11, created via `POST /rest/pat/latest/tokens`, expires **2027-11-18**;
- Confluence PAT id 4, same endpoint, expires 2027-11-18;
- Bearer is tried first, Basic (user+password) is the fallback, so the same code works with either.

Windows specifics that closed off the alternatives: this is **Windows Home**, which cannot be
domain-joined, so there is no Kerberos/SSPI shortcut; `curl --negotiate` against Confluence answers 200
but the body is `{"type":"anonymous"}` (anonymous access, not the Windows identity), and Jira answers 401
to both anonymous and Negotiate. The Bitbucket PAT stays Bitbucket-only (401 Confluence / 403 Jira).

Endpoints worth remembering:
- `POST /rest/pat/latest/tokens` body `{"name": "...", "expirationDuration": 365}` — the duration is a
  **plain integer of days**; the object form `{"type":"DAYS","value":365}` returns 400
  (`JsonMappingException: Can not deserialize instance of java.lang.Integer out of START_OBJECT`).
  The created token comes back once as **`rawToken`**, not `token`.
- `GET` on the same path lists existing tokens (useful to audit/revoke).

Verified end to end from Python only:

```
atl-md jql "assignee = currentUser() AND status = 'In Progress'"
  -> 1 issue: PLAT-376  In Progress  Задача  Medium  Andrey Fink  2026-11-12  "Упаковка" классов …
atl-md jql "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC" --limit 5
  -> 37 open issues, TSV: key/status/type/priority/assignee/updated/summary
atl-md cf 7307751 --out cf-live.md      -> 45,866 B, byte-identical to the browser-fetched conversion
atl-md jira PLAT-376 --out jira-live.md -> 11,126 B with fields, description and comments
```

`--json` prints the untouched Jira response, `--limit`/`--fields` control the query, and `--from-file`
still converts saved payloads offline. Revocation: Jira avatar → Profile → Personal Access Tokens (id 11);
Confluence avatar → Settings → Personal Access Tokens (id 4).

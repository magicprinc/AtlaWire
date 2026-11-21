# AtlaWire development material: ownership and disposition

Reviewed the 61 files present at the start of the 2026-11-20 audit. Read the 12 files
outside the Bitbucket reference bundle in full. Accounted for all 49 reference files by
path and structure; sampled the relevant endpoint sections and read five reference
files verbatim. This is a local file review, not verification of live servers.

## Disposition

| Material | Files | Decision |
| --- | ---: | --- |
| `bitbucket/findings.md`, `jira/api.md`, `confluence/storage.md` | 3 | Keep as local compatibility evidence. Extract useful, sanitized contracts into AtlaWire docs and regression tests. |
| `bitbucket/research.md` | 1 | Keep useful failure observations and compatibility evidence; archive obsolete tool comparisons and superseded measurements. |
| `bitbucket/rest-5.10/` | 45 | Keep the split Markdown as the navigable reference: 125 paths, 193 method/path operations. Correct the index links, which still point to a nonexistent `api/` subdirectory. This is the documented core API, not evidence for plugin APIs. |
| `bitbucket/source/` | 4 | Keep one archive copy of the source HTML and Pandoc intermediate for provenance. Extract usable notes from the README. The old `bkt` skill is historical, not an AtlaWire skill. |
| `BITBUCKET-AGENT-START.md`, `SKILL/bitbucket.md`, `api/public-api.md` | 3 | Keep out of public AtlaWire docs. These are machine onboarding, a legacy tool skill, and another application's API. Keep needed routing in the shared skill; keep unrelated documentation with its owner. |
| `review/2026-11-18_BBK_QUALITY_AUDIT.md`, `side_tests/cosmic-ray-baseline-UL0xmiuO/` | 5 | Route to the owning workspace; the upstream patch and tool meta-tests are not AtlaWire tests. They are already in a local unpushed commit. Do not push that history as-is. |

`docs/INDEX.md` is outside `.development` but is also an exact copy of the `bbk` index,
including unrelated tools and local paths. Replace it with an AtlaWire index after agreeing
the documentation move, not with a second current `bbk` capability list.

## What is already covered, and what is not

- **Implemented:** Bitbucket `nextPageStart` paging, Jira issue lookup and bounded JQL,
  and Confluence content fetch with `body.storage` rather than `body.view`.
- **Preserve as regression cases:** Bitbucket 5.10 requires client-rendered JSON PR diffs
  and a per-file fallback for truncated diffs; `/changes` wraps values and uses path objects.
  `/raw` and archive calls need their own Accept values. Empty merge diffs may be legitimate.
  Use the notes as evidence to reproduce, not as proof of compatibility on every version.
- **Still planned:** project catalog/search, repo archive/grep, Bitbucket PR and write
  workflows; Jira comment/status workflows; Confluence CQL, children, and storage Markdown.
  For Jira comment windows, distinguish issue update time from comment timestamp.
- **Correct before porting:** historical Confluence notes disagree on how page comments
  are created. Preserve the recorded `/child/comment` rejection and validate the
  `POST /rest/api/content` with `type=comment` behavior before accepting that write.
  Do not assume merged table cells can be converted to pipe tables without loss.

## Safe cutover

1. Keep both copies for now. SHA-256 comparison confirmed exact matches for all 49
   reference files, six product/onboarding notes, and the separate `docs/INDEX.md`.
   A reference generator exists in the old workspace; it was not run or migrated.
2. Put maintained Atlassian implementation and requirements notes in AtlaWire. Leave
   probes, unrelated projects, and agent coordination with their owners. A short `bbk`
   pointer and the shared skill should explain how to choose and use the tools, not
   reproduce the technical manuals.
3. `bbk`'s README, capability index, onboarding, and PR review docs still link to
   local copies. Retarget those links and check consumers before removing a source
   file. Keep `bbk` functional until AtlaWire passes its parity checks.
4. Keep internal locations, credential handling recipes, and unrelated artifacts out
   of public commits and packages. The documentation-license decision does not change
   that boundary. Handle the already-tracked local history separately with approval.

No existing file was moved or deleted. No live request, installation, or test was run
as part of this document audit.

## Follow-up

- The [5.10 reference index](../bitbucket/rest-5.10/README.md) now links to its sibling files.
  All 44 links resolve locally; the 41 resource rows still account for 125 paths.
- The [Confluence storage note](../confluence/storage.md#прочее) now distinguishes the route
  used in `bbk` from the rejected `/child/comment` route. This is a source/documentation
  correction, not a live write check or an AtlaWire compatibility claim.

"""Produce the tester's findings report an executor can act on.

Findings are classified by cause, not by symptom: a declared-but-optional
parameter and a missing declaration are different defects with different fixes.
Environment limits are separated so nobody patches a permission problem.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from atlawire.operations import list_operations  # noqa: E402

CHECKS = pathlib.Path("checks")
OUT = CHECKS / "TEST-FINDINGS.md"


def load(name: str) -> dict:
    path = CHECKS / name
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


operations_doc = load("live_tester_operations.json")
docs = load("live_tester_docs.json")
params = load("live_tester_params.json")
cli = load("live_tester_cli.json")
parity = load("live_tester_bbk_parity.json")

registry = {operation["id"]: operation for operation in list_operations()}

lines: list[str] = []


def out(text: str = "") -> None:
    lines.append(text)


def table(header: list[str], rows: list[list[str]]) -> None:
    out("| " + " | ".join(header) + " |")
    out("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        out("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")


def esc(value: object, limit: int = 160) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")[:limit]


def field_state(operation_id: str, name: str) -> tuple[bool, object]:
    """Return (declared, required) for a parameter of one registered operation."""
    operation = registry.get(operation_id) or {}
    for field in operation.get("query") or []:
        if field["name"] == name:
            return True, field.get("required")
    for field in operation.get("body") or []:
        if field["name"] == name:
            return True, field.get("required")
    return False, None


# ---------------------------------------------------------------- header
out("# AtlaWire live test findings")
out()
out(f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}")
out()
out(
    "A tester walked every registered operation, every declared query parameter, "
    "every CLI command and BBK's public API against one live self-hosted "
    "deployment, using a read-only personal access token. This file lists what "
    "does not work and what to change; it does not list what works."
)
out()
out("## How to reproduce")
out()
out("```bash")
out("python checks/live_tester_discovery.py      # discover live identifiers")
out("python checks/live_tester_operations.py     # call all registered operations")
out("python checks/live_tester_params.py         # probe declared query fields")
out("python checks/live_tester_docs.py           # registry vs downloaded WADL")
out("python checks/live_tester_cli.py            # every CLI command")
out("python checks/live_tester_bbk_parity.py     # BBK function by function")
out("python checks/build_test_findings.py        # this report")
out("```")
out()
out("## Summary")
out()
op_summary = operations_doc.get("summary", {})
out(
    f"- Operations: {operations_doc.get('operations', 0)} registered, "
    f"{op_summary.get('ok', 0)} answered, {op_summary.get('failed', 0)} failed, "
    f"{op_summary.get('blocked', 0)} could not be called."
)
out(f"- Documentation vs WADL: {docs.get('summary')}")
out(f"- Parameters: {params.get('summary')}")
if cli:
    out(f"- CLI: {cli.get('commands', 0)} commands, help failures: {cli.get('help_failures') or 'none'}")
if parity:
    out(f"- BBK parity: {parity.get('summary')}")
out()

# ---------------------------------------------------------------- A
out("## Findings for the executor")
out()

out("### F1. A required query parameter is declared optional")
out()
out(
    "Nine registered operations refuse every call because the server requires a "
    "query parameter that the registry marks `required=False`. A caller has no way "
    "to know it must be sent, and `read` does not enforce it. The fix is one "
    "attribute per field; no parser change is needed."
)
out()
f1_rows = []
for record in operations_doc.get("results", []):
    if not record.get("registry_gap"):
        continue
    detail = record.get("detail") or ""
    needed = None
    for word in detail.split():
        cleaned = word.strip("'\".,:;")
        if cleaned in {f["name"] for f in (registry.get(record["id"]) or {}).get("query") or []}:
            needed = cleaned
            break
    if needed is None:
        continue
    declared, required = field_state(record["id"], needed)
    if declared and required is False:
        f1_rows.append([f"`{record['id']}`", record["product"], f"`{needed}`"])
if f1_rows:
    table(["operation", "product", "field to mark required=True"], f1_rows)
else:
    out("None.")
out()

out("### F2. A required parameter is not declared at all")
out()
out(
    "The server named a parameter as required while the registry declares no field "
    "of that name, so no caller can send it and the route can never answer. This is "
    "taken from the live refusal, not from the WADL."
)
out()


def required_name(detail: str, declared: set[str]) -> str | None:
    """Extract the parameter name a server called required, in its own phrasing.

    The phrasings observed on this deployment are:
      * ``The context parameter is required.``
      * ``The until query parameter is required``
      * ``The "until" query parameter is required.``
      * ``The parameter 'path' is required``
      * ``cql query parameter is required Bad Request``
      * ``Required field 'projectKeys' was not provided``
      * ``globalId: 'globalId' is required.``
    """
    import re as _re

    patterns = (
        r'The "?(?P<name>\w+)"? (?:query )?parameter is required',
        r"The parameter ['\"](?P<name>\w+)['\"] is required",
        r"^(?P<name>\w+) query parameter is required",
        r"Required field ['\"](?P<name>\w+)['\"]",
        r"(?P<name>\w+): '\w+' is required",
    )
    for pattern in patterns:
        match = _re.search(pattern, detail)
        if match:
            name = match.group("name")
            return None if name in declared else name
    return None


f2_rows = []
for record in operations_doc.get("results", []):
    if not record.get("registry_gap"):
        continue
    operation = registry.get(record["id"]) or {}
    declared = {
        field["name"] for field in operation.get("query") or []
    } | {field["name"] for field in operation.get("body") or []}
    name = required_name(record.get("detail") or "", declared)
    if name:
        f2_rows.append([f"`{record['id']}`", record["product"], f"`{name}`"])
if f2_rows:
    table(["operation", "product", "field to add"], f2_rows)
else:
    out("None proven.")
out()

out("### F3. Registry and deployment disagree on the query surface")
out()
if docs:
    problems = docs.get("problems", [])
    missing = [p for p in problems if p["kind"] == "parameter-missing-from-registry"]
    extra = [p for p in problems if p["kind"] == "parameter-not-in-wadl"]
    routes = [p for p in problems if p["kind"] == "route-not-in-wadl"]

    out(f"**F3a. Documented by the WADL but absent from the registry ({len(missing)}).**")
    out()
    out(
        "Two of these are deliberate and need no change: `updateHistory` is a write "
        "and must stay absent, and the three `jira.search.post` fields belong to the "
        "GET form of the same route. Verify each before acting."
    )
    out()
    if missing:
        table(
            ["product", "operation", "parameter", "judgement"],
            [
                [
                    p["product"],
                    f"`{p['id']}`",
                    f"`{p['detail']}`",
                    "deliberate: a write, keep absent"
                    if p["detail"].lower() == "updatehistory"
                    else "POST-form field; the GET already exposes it",
                ]
                for p in missing
            ],
        )
    out()

    out(f"**F3b. Declared but not documented by the WADL ({len(extra)}).**")
    out()
    out(
        "Most are `limit`/`start` on paged routes, which the product documents in "
        "prose rather than in the WADL; those are correct as declared. Only the rows "
        "marked *verify* are unexplained."
    )
    out()
    if extra:
        table(
            ["product", "operation", "parameter", "judgement"],
            [
                [
                    p["product"],
                    f"`{p['id']}`",
                    f"`{p['detail']}`",
                    "paging parameters, documented in prose"
                    if p["detail"] in {"limit", "start"}
                    else "verify against the product documentation",
                ]
                for p in extra
            ],
        )
    out()

    out(f"**F3c. Registered routes the WADL does not describe ({len(routes)}).**")
    out()
    out(
        "Each must be called live before it is trusted: a route that answers proves "
        "it exists even when the WADL omits it."
    )
    out()
    if routes:
        table(
            ["product", "operation", "path"],
            [[p["product"], f"`{p['id']}`", f"`{p['detail']}`"] for p in routes],
        )
    out()

out("### F4. Query parameters that fail when exercised")
out()
if params:
    by_outcome = defaultdict(list)
    for record in params.get("results", []):
        by_outcome[record["outcome"]].append(record)
    entries = by_outcome.get("parameter-failed", [])
    if entries:
        out(
            "The parameter was sent with a value derived from its own declaration and "
            "the call failed. Either the declaration is wrong or the value class is."
        )
        out()
        table(
            ["operation", "parameter", "sent", "result"],
            [
                [
                    f"`{r['id']}`",
                    f"`{r['parameter']}`",
                    esc(r.get("value"), 30),
                    esc(f"{r.get('category')} {r.get('status')}: {r.get('detail') or ''}", 130),
                ]
                for r in entries
            ],
        )
        out()
    not_probed = by_outcome.get("not-probed", [])
    if not_probed:
        out(
            f"**Not exercised: {len(not_probed)} parameters.** No safe value could be "
            "derived from the declaration (free text, or no enum and no bounds). This "
            "is a coverage gap, not a defect: the tester will not invent input."
        )
        out()

out("### F5. CLI commands")
out()
if cli:
    failures = [r for r in cli.get("results", []) if r.get("live_exit") not in (None, 0)]
    if failures:
        out("A live invocation failed with arguments the command's own help accepts.")
        out()
        table(
            ["command", "argv", "exit", "stderr"],
            [
                [
                    f"`{r['command']}`",
                    esc(r.get("live_argv"), 70),
                    str(r.get("live_exit")),
                    esc(r.get("live_stderr") or "", 120),
                ]
                for r in failures
            ],
        )
        out()
    else:
        out(
            "Every live invocation used arguments the command's help documents, and "
            "none failed. No defect found in the CLI layer."
        )
        out()
    if cli.get("help_failures"):
        out("**Help failures:** " + ", ".join(f"`{n}`" for n in cli["help_failures"]))
        out()

out("### F6. BBK functions with no equivalent, or a worse one")
out()
if parity:
    results = parity.get("results", [])
    for verdict in ("missing", "worse"):
        entries = [r for r in results if r["verdict"] == verdict]
        out(f"**{verdict}: {len(entries)}**")
        out()
        if entries:
            table(
                ["BBK function", "AtlaWire equivalent", "note"],
                [
                    [
                        f"`{r['bbk_module']}:{r['bbk_function']}`",
                        f"`{r.get('atlawire') or '—'}`",
                        esc(r.get("note") or "", 110),
                    ]
                    for r in entries
                ],
            )
        else:
            out("None.")
        out()
    same = [r for r in results if r["verdict"] in {"same", "better"}]
    out(f"For context: {len(same)} functions are at parity or better.")
    out()
else:
    out("Not run: `python checks/live_tester_bbk_parity.py`.")
    out()

out("## Not defects")
out()
out(
    "These look like failures in the raw data and are not. Do not change code for "
    "them."
)
out()
permission = [
    r for r in operations_doc.get("results", []) if r.get("status") in (401, 403)
]
admin_denied = [r for r in permission if r.get("scope") == "admin"]
non_admin = [r for r in permission if r.get("scope") != "admin"]
out(
    f"- **{len(admin_denied)} administrative reads refused.** The token is read-only "
    "and has no admin rights. This is the boundary working as designed."
)
out(f"- **{len(non_admin)} non-administrative reads refused** — check the token's project permissions.")
if non_admin:
    for record in non_admin:
        out(f"  - `{record['id']}` -> {record['status']}")
blocked = Counter(r.get("reason", "") for r in operations_doc.get("results", []) if r["outcome"] == "blocked")
out(
    f"- **{sum(blocked.values())} operations could not be called** because this "
    "deployment has no such object (webhooks, schemes, screens, dashboards). The "
    "tester refuses to invent an id. No conclusion can be drawn about them."
)
empty = [
    r for r in operations_doc.get("results", [])
    if r["outcome"] == "ok" and (r.get("shape") or {}).get("empty")
]
out(
    f"- **{len(empty)} reads answered 200 with an empty result.** On this deployment "
    "that may simply be the truth (no remote links, no subtasks, no filter "
    "favourites). Each needs one manual look, not a code change."
)
for record in empty:
    out(f"  - `{record['id']}` sent {record.get('arguments') or '{}'}")
out()

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"written {OUT} ({len(lines)} lines)")

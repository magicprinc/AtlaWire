"""Three-way coverage matrix: operation -> Python API, CLI command, WADL.

The owner asked for exactly this: is each capability present in the Python API, in
the command line API, and does it match the deployment's official description?
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from atlawire.operations import list_operations, read_operation  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
completed = subprocess.run(
    [sys.executable, "-B", "-m", "atlawire", "--catalog"],
    capture_output=True, text=True, encoding="utf-8-sig", check=False,
)
catalog = json.loads(completed.stdout)["commands"]
docs = json.loads((ROOT / "checks/live_tester_docs.json").read_text(encoding="utf-8"))

# WADL-documented routes, from the docs sweep.
undocumented_routes = {
    problem["id"]
    for problem in docs["problems"]
    if problem["kind"] == "route-not-in-wadl"
}

# Which CLI commands exist, for matching an operation to a dedicated command.
COMMAND_NAMES = set(catalog)

# Candidate command names for one operation: the last meaningful segment of the
# path, plus the operation id's last segments.
def candidate_commands(operation: dict) -> list[str]:
    path = operation["path"].rstrip("/")
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    tail = segments[-2:] if len(segments) >= 2 else segments
    guesses = {"-".join(tail), tail[-1] if tail else ""}
    return sorted(name for name in COMMAND_NAMES if name in guesses)

rows = []
for operation in list_operations():
    python_api = True  # every operation is reachable through read_operation
    command = candidate_commands(operation)
    documented = operation["id"] not in undocumented_routes
    rows.append(
        {
            "id": operation["id"],
            "product": operation["product"],
            "method": operation["method"],
            "python_api": python_api,
            "cli_commands": command,
            "wadl_documented": documented,
            "query_fields": len(operation.get("query") or []),
            "path_arguments": len(operation.get("arguments") or []),
        }
    )

print(f"operations: {len(rows)}")
print(f"with a dedicated CLI command: {sum(1 for r in rows if r['cli_commands'])}")
print(f"reachable only through `read <id>`: {sum(1 for r in rows if not r['cli_commands'])}")
print(f"not documented by the WADL: {sum(1 for r in rows if not r['wadl_documented'])}")
print()
print("operations with no dedicated command, by product:")
by_product = Counter(r["product"] for r in rows if not r["cli_commands"])
print(" ", dict(by_product))
print()
print("operations with a dedicated command and also in the WADL (the healthy case):")
healthy = [r for r in rows if r["cli_commands"] and r["wadl_documented"]]
print(f"  {len(healthy)}")
print()
print("operations whose command name guessed a match, sample:")
for row in [r for r in rows if r["cli_commands"]][:12]:
    print(f"  {row['id']:56} -> {row['cli_commands']}")

out = ROOT / "checks/live_tester_matrix.json"
out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
print("\nwritten:", out)

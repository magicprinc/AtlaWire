"""Probe documented query parameters the way a careful tester would.

For every operation that declares query fields, the documented default is sent
first, then a boundary or alternative value, and the answers are compared. A
parameter that never changes the answer, or that fails, is recorded: the first
is a documentation or wiring defect, the second a broken parameter.

Run:
    python checks/live_tester_params.py [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atlawire.credentials import load_saved_credentials  # noqa: E402
from atlawire.http import AtlaWireError  # noqa: E402
from atlawire.operations import list_operations, read_operation  # noqa: E402
from live_tester_discovery import discover  # noqa: E402
from live_tester_operations import argument_value  # noqa: E402


def probe_value(field: dict[str, object]) -> object | None:
    """Return one alternative value for a declared query field."""
    kind = field.get("type")
    allowed = field.get("enum") or []
    if allowed:
        return allowed[-1]
    if kind == "integer":
        minimum = field.get("minimum")
        maximum = field.get("maximum")
        if isinstance(minimum, int) and minimum > 1:
            return minimum
        if isinstance(maximum, int) and maximum >= 1:
            return 1
        return 1
    if kind == "boolean":
        return "true"
    return None


def call(operation_id: str, product: str, arguments: dict[str, str], query):
    saved = load_saved_credentials(product, allow_http_loopback=False)
    try:
        payload = read_operation(
            operation_id,
            saved.base_url,
            token=saved.token,
            arguments=arguments,
            query=query,
        )
    except AtlaWireError as exc:
        return None, exc
    return payload, None


def size_of(payload: object) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return len(payload)
    return 0


def run(out: Path) -> int:
    pool = discover()
    results = []

    for operation in list_operations():
        declared = operation.get("query") or []
        if not declared:
            continue

        arguments = {}
        blocked = None
        for argument in operation.get("arguments") or []:
            value, source = argument_value(
                operation["product"], operation["path"], argument["name"], pool
            )
            if value in (None, ""):
                blocked = f"{argument['name']}: {source}"
                break
            arguments[argument["name"]] = str(value)
        if blocked:
            results.append(
                {"id": operation["id"], "outcome": "blocked", "reason": blocked}
            )
            continue

        for field in declared:
            name = field["name"]
            record = {
                "id": operation["id"],
                "product": operation["product"],
                "parameter": name,
                "type": field.get("type"),
                "declared_default": field.get("default"),
                "enum": field.get("enum"),
            }
            alternative = probe_value(field)
            if alternative is None:
                record.update(
                    outcome="not-probed",
                    reason="no safe alternative value is derivable from the declaration",
                )
                results.append(record)
                continue

            baseline, baseline_error = call(
                operation["id"], operation["product"], arguments, {name: "1"}
                if field.get("type") == "integer"
                else {}
            )
            changed, changed_error = call(
                operation["id"], operation["product"], arguments, {name: alternative}
            )

            if changed_error is not None:
                record.update(
                    outcome="parameter-failed",
                    value=str(alternative),
                    category=changed_error.category,
                    status=changed_error.http_status,
                    detail=(changed_error.detail or "")[:200] or None,
                )
            elif baseline_error is not None:
                record.update(
                    outcome="baseline-failed",
                    value=str(alternative),
                    category=baseline_error.category,
                    status=baseline_error.http_status,
                )
            else:
                before, after = size_of(baseline), size_of(changed)
                record.update(
                    outcome="ok",
                    value=str(alternative),
                    baseline_size=before,
                    changed_size=after,
                    observable_difference=before != after,
                )
            results.append(record)
            print(
                f"{record['outcome']:18} {operation['id']} {name}={alternative}"
            )

    summary = Counter(record["outcome"] for record in results)
    document = {
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "parameters_probed": len(results),
        "summary": dict(summary),
        "results": results,
    }
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nsummary: {dict(summary)}")
    print("written:", out)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("checks/live_tester_params.json")
    )
    options = parser.parse_args()
    raise SystemExit(run(options.out))

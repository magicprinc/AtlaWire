"""Declare the query parameters each server documents, from its own WADL.

`read <id>` rejects every query name it has not declared, so a documented
parameter was unreachable through the typed surface: the server accepts `expand`,
`fields`, `depth` and hundreds more, while the registry admitted none of them.
This tool turns the WADL's own parameter list into a packaged data file that the
registry merges, so the typed surface matches what the deployment serves.

Hand-written declarations always win: they carry constraints the WADL does not
state (enums, path-shaped values, "one of these" rules), and a generated row must
never loosen them.

    python -B tools/build_query_surface.py
    python -B tools/build_query_surface.py --check
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

# The tools run both as scripts and loaded by path from the test suite, so the
# sibling module is resolved explicitly instead of relying on the caller's path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wadl_surface as wadl

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".development"
OUTPUT = ROOT / "src" / "atlawire" / "query_params.json"

SCHEMA = "atlawire-query-surface/v1"
PREFIX = wadl.REST_PREFIX


def _routes(product: str) -> dict[tuple[str, str], list[wadl.Param]]:
    """Return (method, comparison route) -> documented query parameters."""
    _, methods = wadl.load(product)
    return wadl.served_queries(methods)


def _declared_operations() -> dict[str, tuple[str, str, str, set[str]]]:
    """Return id -> (product, method, route, already-declared query names)."""
    from atlawire import operations

    declared: dict[str, tuple[str, str, str, set[str]]] = {}
    for described in operations.list_operations():
        product = str(described["product"])
        route = str(described["path"]).removeprefix(PREFIX[product])
        names = {
            str(item["name"])
            for item in described["query"]  # type: ignore[union-attr]
            if item.get("source") != "server-wadl"
        }
        declared[str(described["id"])] = (
            product,
            str(described["method"]),
            route,
            names,
        )
    return declared


def build() -> dict[str, object]:
    """Return the query-surface document keyed by operation id."""
    source_record = json.loads(
        (BASE / "api-surface-source.json").read_text(encoding="utf-8")
    )
    per_product = {product: _routes(product) for product in PREFIX}
    declared = _declared_operations()

    surface: dict[str, list[dict[str, object]]] = {}
    for operation_id in sorted(declared):
        product, method, route, already = declared[operation_id]
        served = per_product[product]
        params: list[wadl.Param] = []
        for variant in wadl.route_variants(route):
            params.extend(served.get((method, variant), []))
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        for param in params:
            if param.name in already or param.name in seen:
                continue
            seen.add(param.name)
            row: dict[str, object] = {"name": param.name, "type": param.kind}
            if param.default is not None:
                row["default"] = param.default
            rows.append(row)
        if rows:
            surface[operation_id] = sorted(rows, key=lambda item: str(item["name"]))

    return {
        "schema": SCHEMA,
        "note": (
            "Query parameters each deployment documents for a registered route, "
            "taken from its own WADL. Merged into the registry only for names a "
            "hand-written declaration does not already cover. Regenerate with "
            "tools/build_query_surface.py."
        ),
        "source": {
            product: {
                "wadl_sha256": block["sha256"],
                "server_version": block.get("server_version"),
            }
            for product, block in source_record["products"].items()
        },
        "operations": surface,
    }


def render(document: Mapping[str, object]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the file is stale"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    document = build()
    rendered = render(document)
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8") if args.output.exists() else None
        )
        if current != rendered:
            print(f"query surface outdated: {args.output.relative_to(ROOT)}")
            return 1
        print("query surface current")
    else:
        args.output.write_text(rendered, encoding="utf-8")

    operations = document["operations"]
    if not isinstance(operations, dict):
        print("query surface has no operations object")
        return 1
    total = sum(len(rows) for rows in operations.values())
    integers = sum(
        1 for rows in operations.values() for row in rows if row["type"] == "integer"
    )
    print(f"operations: {len(operations)}  parameters: {total}  integer: {integers}")
    per_product: dict[str, int] = {}
    for operation_id in operations:
        product = operation_id.split(".", 1)[0]
        per_product[product] = per_product.get(product, 0) + 1
    print("operations by product:", dict(sorted(per_product.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

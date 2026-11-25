"""Report where our registry disagrees with the API the servers actually serve.

The API surface comes from each deployment's own WADL, so a difference here is a
fact about the product, not about a docs page. Three questions:

1. Registered, the server serves it, but we declare fewer query parameters than
   the server documents — the caller cannot pass what the route accepts.
2. Registered, but the server does not serve that method at that path.
3. Served as a GET, not registered at all.

    python -B tools/check_api_surface.py
    python -B tools/check_api_surface.py --check   # non-zero on a regression
"""

import argparse
import hashlib
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
INDEX = BASE / "api-surface.json"

PREFIX = wadl.REST_PREFIX
normalize = wadl.normalize
route_variants = wadl.route_variants

# Parameters deliberately not offered on a read surface because sending them
# changes state. They are neither declared nor counted as an undeclared gap: the
# question "can a caller send what the server documents?" is answered "no, on
# purpose", and `check_read_only.py` fails if one ever reappears in the registry.
NOT_OFFERED_PARAMS = frozenset({"updatehistory"})

# `route_variants` is re-exported for the tests, which pin the rule that a glued
# optional suffix covers two routes while a trailing placeholder stays distinct.

BASELINE = {
    # Counts, plus the identity of both difference lists and the WADL they were
    # read from. Only the deliberately deferred routes remain: a binary body and
    # one state-changing GET.
    "bitbucket": {
        "matched": 100,
        "undeclared_param_routes": 0,
        "server_only": 0,
        "server_only_sha": "e3b0c44298fc1c14",
        "registry_only": 0,
        "registry_only_sha": "e3b0c44298fc1c14",
        "wadl_sha256": "9942abd00c3aedaf",
    },
    "confluence": {
        "matched": 44,
        "undeclared_param_routes": 0,
        "server_only": 1,
        "server_only_sha": "43e09becea01acfe",
        "registry_only": 0,
        "registry_only_sha": "e3b0c44298fc1c14",
        "wadl_sha256": "f5c08e2b952650f1",
    },
    "jira": {
        "matched": 171,
        "undeclared_param_routes": 0,
        "server_only": 2,
        "server_only_sha": "39b600fed2ab32fe",
        "registry_only": 2,
        "registry_only_sha": "67ede67ab0463047",
        "wadl_sha256": "1106c2469ec3dca8",
    },
}


def registry_index() -> dict[str, dict[tuple[str, str], set[str]]]:
    """Return product -> (method, route) -> declared query field names."""
    from atlawire import operations

    index: dict[str, dict[tuple[str, str], set[str]]] = {}
    for described in operations.list_operations():
        product = str(described["product"])
        route = str(described["path"]).removeprefix(PREFIX[product])
        fields = {str(field["name"]) for field in described["query"]}  # type: ignore[union-attr]
        # Our registry writes the same optional suffix the WADL does
        # (`compare/diff{path:.*}`), so it covers the same two routes.
        for variant in route_variants(route):
            index.setdefault(product, {})[(str(described["method"]), variant)] = fields
    return index


def compare() -> dict[str, object]:
    document = json.loads(INDEX.read_text(encoding="utf-8"))
    registry = registry_index()
    report: dict[str, object] = {}
    for product, block in document["products"].items():
        # The index keeps the documented placeholder names (`{projectKey}`),
        # while the registry is normalized to `{}`. Comparing raw would match
        # almost nothing, so both sides go through the same normalizer.
        served: dict[tuple[str, str], set[str]] = {}
        for method in block["methods"]:
            offered = {
                name
                for name in method["query"]
                if str(name).lower() not in NOT_OFFERED_PARAMS
            }
            for route in route_variants(method["route"]):
                served.setdefault((method["verb"], route), set()).update(offered)
        ours = registry.get(product, {})
        served_get = {key for key in served if key[0] == "GET"}
        registered_get = {key for key in ours if key[0] == "GET"}
        matched = served_get & registered_get
        undeclared = {
            f"{method} {route}": sorted(
                served[(method, route)] - ours.get((method, route), set())
            )
            for method, route in matched
        }
        undeclared = {key: names for key, names in undeclared.items() if names}
        report[product] = {
            "server_get": len(served_get),
            "registered_get": len(registered_get),
            "matched": len(matched),
            "server_only": sorted(f"{m} {r}" for m, r in served_get - registered_get),
            "registry_only": sorted(f"{m} {r}" for m, r in registered_get - served_get),
            "undeclared_params": undeclared,
        }
    return report


def lines(report: Mapping[str, object]) -> list[str]:
    output: list[str] = []
    for product, block in report.items():
        if not isinstance(block, dict):
            raise SystemExit(f"{product}: malformed report block")
        output.append(
            f"{product:10} server GETs={block['server_get']:<4} "
            f"registered={block['registered_get']:<4} matched={block['matched']:<4} "
            f"server-only={len(block['server_only']):<4} "
            f"registry-only={len(block['registry_only']):<3} "
            f"routes with undeclared params={len(block['undeclared_params'])}"
        )
    return output


def _digest(items: Sequence[str]) -> str:
    """Return a stable digest over a sorted list of route strings."""
    return hashlib.sha256("\n".join(sorted(items)).encode("utf-8")).hexdigest()[:16]


def problems(report: Mapping[str, object]) -> list[str]:
    """Return every disagreement that is not in the reviewed baseline.

    Counts alone can stay green while a rename replaces one route with another,
    so the identity of both difference lists is digested, and the WADL each
    product was read from is pinned by its digest.
    """
    found: list[str] = []
    source = json.loads((BASE / "api-surface-source.json").read_text(encoding="utf-8"))
    for product, block in report.items():
        if not isinstance(block, dict):
            raise SystemExit(f"{product}: malformed report block")
        baseline = BASELINE[product]
        actual = {
            "matched": block["matched"],
            "undeclared_param_routes": len(block["undeclared_params"]),
            "server_only": len(block["server_only"]),
            "registry_only": len(block["registry_only"]),
            "server_only_sha": _digest(block["server_only"]),
            "registry_only_sha": _digest(block["registry_only"]),
            "wadl_sha256": str(source["products"][product]["sha256"])[:16],
        }
        for key, expected in baseline.items():
            if actual[key] != expected:
                found.append(f"{product} {key}: baseline {expected}, now {actual[key]}")
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on any drift")
    parser.add_argument("--verbose", action="store_true", help="print every difference")
    args = parser.parse_args(argv)

    report = compare()
    for line in lines(report):
        print(line)
    if args.verbose:
        for product, block in report.items():
            if not isinstance(block, dict):
                raise SystemExit(f"{product}: malformed report block")
            for name in ("server_only", "registry_only"):
                for item in block[name]:
                    print(f"  {product} {name}: {item}")
            for route, names in block["undeclared_params"].items():
                print(f"  {product} undeclared: {route}: {names}")

    if not args.check:
        return 0
    found = problems(report)
    if found:
        print(f"api surface drift: {len(found)} difference(s) from the baseline")
        for item in found:
            print(f"  {item}")
        return 1
    print("api surface matches the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())

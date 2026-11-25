"""Declare the administrative and system reads each deployment exposes.

These routes sit outside the non-administrative scope the library advertised, but
they are still read-only and the server itself decides whether the caller may see
them: some answer 200 to this token and some answer 401/403. Hiding them meant a
consumer had to reach for `api-get` and lost validation, paging and the operation
id. They are declared here with `scope="admin"` instead, so `read` requires an
explicit `--allow-admin` and nothing administrative becomes implicit.

Three routes are deliberately not declared:

* a binary body (Jira `/email-templates`, Confluence `/audit/export`) - a JSON
  reader would fail on it, and the binary path is a separate feature;
* Jira `GET /issue/{key}/subtask/move` - documented as a GET but state-changing,
  so declaring it as a read would let a read command move a subtask.

    python -B tools/build_admin_surface.py
    python -B tools/build_admin_surface.py --check
"""

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wadl_surface as wadl

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "atlawire" / "admin_operations.json"
SCHEMA = "atlawire-admin-surface/v1"

W = wadl.W
UNSAFE = re.compile(r"[^a-z0-9]+")
SEGMENT = re.compile(r"[A-Za-z0-9_.~\-]+")

# Routes that must never be declared as a read, with the reason recorded in the
# artifact so the exclusion is auditable rather than remembered.
DEFERRED = {
    ("jira", "GET", "/email-templates"): "binary archive body (application/zip)",
    (
        "confluence",
        "GET",
        "/audit/export",
    ): "binary archive body (application/zip, text/csv)",
    (
        "jira",
        "GET",
        "/issue/{issueIdOrKey}/subtask/move",
    ): "documented as a GET but changes state; the same path is a POST",
}

VERSIONS = {
    "jira": "Jira Server 8.22 REST API 2",
    "confluence": "Confluence Server 6.6 REST API",
    "bitbucket": "Bitbucket Server 5.10 REST API 1.0",
}


@dataclass(frozen=True)
class Candidate:
    product: str
    verb: str
    route: str
    doc: str
    binary: bool
    query: list[wadl.Param]


def _slug(product: str, route: str) -> str:
    words = [product]
    for part in route.split("/"):
        if not part:
            continue
        words.append(wadl.param_name(part[1:-1]) if part.startswith("{") else part)
    return ".".join(UNSAFE.sub("-", word.lower()).strip("-") for word in words)


def _arguments(route: str) -> list[dict[str, object]]:
    seen: list[tuple[str, bool]] = []
    for match in re.finditer(r"\{([^{}]*)\}", route):
        raw = match.group(1)
        name = wadl.param_name(raw)
        entry = (name, raw.endswith(":.*"))
        if entry not in seen:
            seen.append(entry)
    return [
        {
            "name": name,
            "pattern": SEGMENT.pattern,
            "allow_slash": allow_slash,
            "description": f"Path value for {name}.",
        }
        for name, allow_slash in seen
    ]


def _candidates(product: str) -> list[Candidate]:
    """Return every GET the WADL declares, with its response kind resolved."""
    from defusedxml import ElementTree

    root = ElementTree.parse(wadl.wadl_path(product)).getroot()
    resources = root.find(f"{W}resources")
    if resources is None:
        raise SystemExit(f"{product}: WADL has no resources element")
    found: list[Candidate] = []

    def walk(node, prefix: str) -> None:
        for resource in node.findall(f"{W}resource"):
            full = wadl.readable_route(f"{prefix}/{resource.get('path', '')}")
            for method in resource.findall(f"{W}method"):
                if method.get("name", "").upper() != "GET":
                    continue
                media: list[str] = []
                for response in method.findall(f"{W}response"):
                    for representation in response.findall(f"{W}representation"):
                        media.append(representation.get("mediaType") or "")
                text = " ".join(media).lower()
                binary = "json" not in text and any(
                    marker in text
                    for marker in ("image", "octet-stream", "zip", "csv", "text/plain")
                )
                found.append(
                    Candidate(
                        product=product,
                        verb="GET",
                        route=full,
                        doc=wadl.prose(method.find(f"{W}doc")),
                        binary=binary,
                        query=wadl._query_params(method),
                    )
                )
            walk(resource, full)

    walk(resources, "")
    return found


def build() -> dict[str, object]:
    from atlawire import operations

    # Only the non-administrative surface counts as "already declared". The admin
    # operations themselves are loaded by the registry from this very file, so
    # including them would make a second run see its own output and emit nothing.
    registered: dict[str, set[tuple[str, str]]] = {}
    for described in operations.list_operations():
        if described.get("scope") == "admin":
            continue
        product = str(described["product"])
        route = str(described["path"]).removeprefix(wadl.REST_PREFIX[product])
        for variant in wadl.route_variants(route):
            registered.setdefault(product, set()).add(
                (str(described["method"]), variant)
            )

    rows: list[dict[str, object]] = []
    deferred: list[dict[str, str]] = []
    used: set[str] = set()

    for product in wadl.PRODUCTS:
        for candidate in _candidates(product):
            variants = wadl.route_variants(candidate.route)
            if any(
                (candidate.verb, variant) in registered.get(product, set())
                for variant in variants
            ):
                continue
            reason = DEFERRED.get((product, candidate.verb, candidate.route))
            if reason is None and candidate.binary:
                reason = "non-JSON body"
            if reason is not None:
                deferred.append(
                    {
                        "product": product,
                        "method": candidate.verb,
                        "path": candidate.route,
                        "reason": reason,
                    }
                )
                continue
            base = _slug(product, candidate.route)
            operation_id = base
            suffix = 2
            while operation_id in used:
                operation_id = f"{base}-{suffix}"
                suffix += 1
            used.add(operation_id)
            # The WADL path is relative to its base (`/admin/cluster`); the
            # registry, the inventory and every other artifact use the absolute
            # route (`/rest/api/1.0/admin/cluster`), so the prefix is added here.
            absolute = wadl.REST_PREFIX[product] + candidate.route
            rows.append(
                {
                    "id": operation_id,
                    "product": product,
                    "method": candidate.verb,
                    "path": absolute,
                    "description": (
                        candidate.doc[:200]
                        if candidate.doc
                        else f"Administrative read: {candidate.route}."
                    ),
                    "documented_version": VERSIONS[product],
                    "arguments": _arguments(absolute),
                    "query": [
                        {"name": param.name, "type": param.kind}
                        | (
                            {"default": param.default}
                            if param.default is not None
                            else {}
                        )
                        for param in candidate.query
                    ],
                }
            )

    return {
        "schema": SCHEMA,
        "note": (
            "Administrative and system reads the deployments expose. Declared with "
            "scope=admin: `read` requires --allow-admin, so nothing administrative "
            "is implicit. Generated from each server's own WADL by "
            "tools/build_admin_surface.py."
        ),
        "operations": sorted(rows, key=lambda row: str(row["id"])),
        "deferred": sorted(deferred, key=lambda row: (row["product"], row["path"])),
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
            print("admin surface outdated")
            return 1
        print("admin surface current")
    else:
        args.output.write_text(rendered, encoding="utf-8")

    rows = document["operations"]
    deferred = document["deferred"]
    if not isinstance(rows, list) or not isinstance(deferred, list):
        print("admin surface has the wrong shape")
        return 1
    per_product: dict[str, int] = {}
    for row in rows:
        product = str(row["product"])
        per_product[product] = per_product.get(product, 0) + 1
    print(f"admin operations: {len(rows)}  deferred: {len(deferred)}")
    print("by product:", dict(sorted(per_product.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Split each server's WADL into per-route-group Markdown knowledge files.

The WADL is the deployment's own declaration of its API: routes, methods, query
parameters with types and defaults, and prose for most methods. This tool turns
it into files small enough to read on demand, mirroring how the vendored
Bitbucket reference is organised, and adds a machine-readable index.

    python -B tools/build_api_surface_docs.py
    python -B tools/build_api_surface_docs.py --check
"""

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# The tools run both as scripts and loaded by path from the test suite, so the
# sibling module is resolved explicitly instead of relying on the caller's path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wadl_surface as wadl

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".development"
UNSAFE = re.compile(r"[^a-z0-9]+")

GROUPS = {"jira", "confluence", "bitbucket"}
# Above this many methods a group is split by its second route segment: a file
# that big cannot be read on demand without loading everything around it.
SPLIT_ABOVE = 40
# Routes with no segments at all land here.
ROOT_GROUP = "root"
# Registered operations the server does not describe at the WADL's base paths,
# with where they really live. Keeping this list short and explicit is the point:
# everything else must be explained by the server's own document.
EXTRA_PATHS = {
    "jira": {
        "GET /attachment/{id}/content": "binary attachment body; the WADL describes the metadata route",
        "GET /attachment/{id}/expand/raw": "documented variant of the attachment route",
        "POST /search": "semantic read: JQL search with a body",
        "POST /worklog/list": "semantic read: worklogs for a set of issues",
        "GET /rest/auth/1/session": "session check under a different REST base",
    },
    "confluence": {
        "POST /contentbody/convert": "semantic read: storage-format conversion",
    },
    "bitbucket": {},
}


@dataclass
class Paths:
    group: str
    methods: list[wadl.Method]


def _slug(route: str) -> str:
    words = [part for part in route.split("/") if part]
    slug = "-".join(UNSAFE.sub("-", part.lower()).strip("-") for part in words)
    return slug or "root"


_SPLIT_GROUPS: set[str] = set()


def _group_of(route: str) -> str:
    """Return the group key for one route, honouring the split for big groups.

    A split uses the first two concrete segments, skipping placeholders: one
    deep resource (``/projects/{key}``) otherwise owns most of the file, and a
    66 KB group is exactly what the split exists to avoid.
    """
    segments = [part for part in route.split("/") if part]
    if not segments:
        return ROOT_GROUP
    first = segments[0]
    if first not in _SPLIT_GROUPS:
        return first
    # A leading placeholder is a parent reference, not a resource name
    # (`/projects/{projectKey}/repos`), so the first literal segment decides.
    literal = [part for part in segments[1:] if not part.startswith("{")]
    if not literal:
        return first
    return f"{first}--{_slug(literal[0])}"


def _groups(product: str) -> dict[str, Paths]:
    """Group one product's methods, splitting a group that grew too large."""
    _, methods = wadl.load(product)
    grouped: dict[str, Paths] = {}
    for method in methods:
        group = _group_of(method.route)
        grouped.setdefault(group, Paths(group=group, methods=[])).methods.append(method)

    big = {name for name, paths in grouped.items() if len(paths.methods) > SPLIT_ABOVE}
    if not big:
        return grouped
    global _SPLIT_GROUPS
    _SPLIT_GROUPS = big
    split: dict[str, Paths] = {}
    for name, paths in grouped.items():
        if name not in big:
            split[name] = paths
            continue
        for method in paths.methods:
            key = _group_of(method.route)
            split.setdefault(key, Paths(group=key, methods=[])).methods.append(method)
    _SPLIT_GROUPS = set()
    return split


def _render_group(product: str, paths: Paths, version: str) -> str:
    lines = [
        (
            f"<!-- {product} {version or 'version not reported'} - "
            f"resource group: {paths.group} -->"
        ),
        "",
        f"# `{paths.group}`",
        "",
        (
            f"{len(paths.methods)} method(s) as this deployment serves them."
            " Source: its own `application.wadl`."
        ),
        "",
    ]
    for method in sorted(paths.methods, key=lambda item: (item.route, item.verb)):
        lines.append(f"## {method.verb} {method.route}")
        lines.append("")
        if method.doc:
            lines.append(method.doc)
            lines.append("")
        if method.query:
            lines.append("| query | type | default |")
            lines.append("|---|---|---|")
            for param in method.query:
                default = "" if param.default is None else f"`{param.default}`"
                shown = param.raw_type or param.kind or "-"
                lines.append(f"| `{param.name}` | {shown} | {default} |")
            lines.append("")
        else:
            lines.append("No query parameters.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build(*, check_only: bool = False) -> tuple[dict[str, object], dict[Path, str]]:
    """Return the index document and every file's exact text.

    ``check_only`` suppresses the stale-file cleanup: a verification run must not
    mutate the tree, and a failure after a deletion would leave a group missing
    while reporting that nothing was written.
    """
    record = json.loads((BASE / "api-surface-source.json").read_text(encoding="utf-8"))
    products_source = record["products"]
    if not isinstance(products_source, dict):
        raise SystemExit("api-surface-source.json has no products object")

    index: dict[str, object] = {
        "schema": "atlawire-api-surface/v1",
        "note": (
            "Frozen from each deployment's own WADL. Routes, methods and query "
            "parameters below are what this server serves, not what a release "
            "note describes. Regenerate with tools/build_api_surface_docs.py."
        ),
        "fetched_at": record.get("fetched_at"),
        "products": {},
    }
    files: dict[Path, str] = {}
    products: dict[str, object] = {}

    for product in sorted(GROUPS):
        source = products_source.get(product)
        if not isinstance(source, dict):
            raise SystemExit(
                f"{product}: no source record; run fetch_api_surface.py --live"
            )
        # Confluence exposes no version endpoint over this REST API, so the
        # version stays null rather than being guessed from a mapping file. The
        # WADL's sha256 is the identity of what was actually read.
        version = source.get("server_version") or None
        grouped = _groups(product)
        folder = BASE / product / "api"
        # `_slug` is not injective (`a--b` and `a-b` both become `a-b`), so two
        # groups could claim one filename and one of them would vanish while the
        # index still listed both. Fail instead of overwriting.
        produced = {f"{_slug(name)}.md" for name in grouped}
        if len(produced) != len(grouped):
            raise SystemExit(f"{product}: two groups map to one file name")
        if not check_only:
            # A verification run must not create or delete anything under the
            # tree it is checking.
            folder.mkdir(parents=True, exist_ok=True)
            for stale_file in folder.glob("*.md"):
                if stale_file.name not in produced:
                    stale_file.unlink()

        methods: list[dict[str, object]] = []
        groups: list[dict[str, object]] = []
        for name in sorted(grouped):
            paths = grouped[name]
            text = _render_group(product, paths, version)
            target = folder / f"{_slug(name)}.md"
            files[target] = text
            methods.extend(
                {
                    "verb": method.verb,
                    "route": method.route,
                    "group": name,
                    "file": str(target.relative_to(ROOT)).replace("\\", "/"),
                    "query": [param.name for param in method.query],
                    "documented": bool(method.doc),
                }
                for method in paths.methods
            )
            groups.append(
                {
                    "group": name,
                    "file": str(target.relative_to(ROOT)).replace("\\", "/"),
                    "methods": len(paths.methods),
                    "bytes": len(text.encode()),
                }
            )

        extra = [
            {"operation": key, "why": why}
            for key, why in EXTRA_PATHS.get(product, {}).items()
        ]
        products[product] = {
            "server_version": version,
            "wadl": source.get("artifact"),
            "wadl_sha256": source.get("sha256"),
            "groups": groups,
            "methods": sorted(methods, key=lambda item: (item["route"], item["verb"])),
            "not_in_wadl": extra,
        }

    index["products"] = products
    return index, files


def render(index: Mapping[str, object]) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a file is stale")
    args = parser.parse_args(argv)

    index, files = build(check_only=args.check)
    index_path = BASE / "api-surface.json"
    files[index_path] = render(index)

    stale: list[str] = []
    for path, text in files.items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != text:
                stale.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            path.write_text(text, encoding="utf-8")

    for product, block in index["products"].items():
        if not isinstance(block, dict):
            raise SystemExit(f"{product}: index block is not an object")
        verbs = {}
        for method in block["methods"]:
            verbs[method["verb"]] = verbs.get(method["verb"], 0) + 1
        documented = sum(1 for method in block["methods"] if method["documented"])
        print(
            f"{product:10} v{block['server_version'] or '-':<8} groups={len(block['groups']):<3} "
            f"methods={len(block['methods']):<4} {verbs} documented={documented}"
        )

    if args.check:
        if stale:
            print(f"api surface outdated: {len(stale)} file(s)")
            for item in stale:
                print(f"  {item}")
            return 1
        print("api surface current")
    return 0


if __name__ == "__main__":
    sys.exit(main())

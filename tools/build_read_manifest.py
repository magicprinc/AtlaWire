"""Build the runtime read manifest from the versioned endpoint mappings.

The mapping files are analysis artifacts under `.development/<product>/`; this
script turns them into one compact, reviewed runtime list. Run it from the
repository root:

    C:/Python315/python.exe -B tools/build_read_manifest.py
    C:/Python315/python.exe -B tools/build_read_manifest.py --check

It writes `src/atlawire/manifest.json`. Binary, text and plugin-only endpoints
are reported as deferred with the reason instead of being silently dropped.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = ROOT / ".development"
OUTPUT = ROOT / "src" / "atlawire" / "manifest.json"

sys.path.insert(0, str(ROOT / "tools"))
import wadl_surface

# Endpoints whose body is not JSON, or which the core reference does not
# define. They stay in the release inventory with an explicit disposition.
# The shape test is shared with the admin generator so a file route cannot be a
# download in one artifact and a JSON read in the other.
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")

# Segments the canonical SDK adapter refuses. An advertised operation must not
# be unusable at runtime, so such routes are deferred with a reason instead.
_ADMIN_SEGMENTS = frozenset(
    {
        "admin",
        "application-properties",
        "applicationrole",
        "audit",
        "auditing",
        "cluster",
        "issuetypescheme",
        "issuesecurityschemes",
        "license",
        "logs",
        "mail-server",
        "notificationscheme",
        "permissions",
        "permissionscheme",
        "priorityschemes",
        "reindex",
        "screens",
        "settings",
        "workflow",
        "workflows",
        "workflowscheme",
    }
)


def load_rows() -> list[tuple[str, dict[str, object]]]:
    sources = (
        ("jira", "mapping-jira.json", "entries", "Jira Server 8.22.0 REST API 2"),
        (
            "confluence",
            "mapping-confluence.json",
            "operations",
            "Confluence Server 6.6.0 REST API",
        ),
        (
            "bitbucket",
            "mapping-bitbucket.json",
            "endpoints",
            "Bitbucket Server 5.10.0 REST API 1.0",
        ),
    )
    rows: list[tuple[str, dict[str, object]]] = []
    for product, name, key, _version in sources:
        document = json.loads((MAPPINGS / product / name).read_text(encoding="utf-8"))
        for row in document[key]:
            rows.append((product, row))
    return rows


def _version(product: str) -> str:
    return {
        "jira": "Jira Server 8.22.0 REST API 2",
        "confluence": "Confluence Server 6.6.0 REST API",
        "bitbucket": "Bitbucket Server 5.10.0 REST API 1.0",
    }[product]


def _deferred(path: str) -> str | None:
    lowered = path.lower()
    if wadl_surface.is_non_json_route(lowered):
        return "non-JSON body (archive, raw, download or avatar)"
    if wadl_surface.is_deployment_rejected_route(lowered):
        return "the deployment rejects every form of this route"
    segments = {part for part in lowered.split("/") if part}
    if segments & _ADMIN_SEGMENTS:
        return "administrative or system route"
    return None


def _slug(product: str, path: str) -> str:
    trimmed = path
    for prefix in ("/rest/api/2/", "/rest/api/1.0/", "/rest/api/"):
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
            break
    parts = [part for part in trimmed.strip("/").split("/") if part]
    words: list[str] = [product]
    for part in parts:
        match = _PLACEHOLDER.fullmatch(part)
        if match:
            words.append(match.group(1).lower().removesuffix(":.*"))
        else:
            words.append(part.lower())
    slug = ".".join(re.sub(r"[^a-z0-9]+", "-", word).strip("-") for word in words)
    return slug


def _description(product: str, row: dict[str, object]) -> str:
    group = row.get("group") or row.get("area") or row.get("id") or "endpoint"
    return f"{product.capitalize()} read: {group}."


def _arguments(path: str) -> list[dict[str, object]]:
    seen: list[tuple[str, bool]] = []
    for match in _PLACEHOLDER.finditer(path):
        raw = match.group(1)
        name = raw.removesuffix(":.*")
        entry = (name, raw.endswith(":.*"))
        if entry not in seen:
            seen.append(entry)
    return [
        {
            "name": name,
            "pattern": r"[A-Za-z0-9_.~\-]+",
            "allow_slash": allow_slash,
            "description": f"Path value for {name}.",
        }
        for name, allow_slash in seen
    ]


def build_document() -> tuple[dict[str, object], list[dict[str, str]], list[str]]:
    """Return the manifest document and its deferred/renamed diagnostics."""
    rows = load_rows()
    operations: dict[str, dict[str, object]] = {}
    deferred: list[dict[str, str]] = []
    duplicates: list[str] = []

    for product, row in rows:
        path = str(row["path"])
        method = str(row["method"]).upper()
        status = str(row.get("status", "")).lower()
        if status == "uncertain":
            deferred.append(
                {
                    "product": product,
                    "path": path,
                    "reason": "documented inconsistently",
                }
            )
            continue
        if method == "POST":
            deferred.append(
                {
                    "product": product,
                    "path": path,
                    "reason": "registered separately: semantic POST with declared body schema",
                }
            )
            continue
        reason = _deferred(path)
        if reason is not None:
            deferred.append({"product": product, "path": path, "reason": reason})
            continue
        base = _slug(product, path)
        operation_id = base
        if operation_id in operations:
            operation_id = f"{base}-{method.lower()}"
        suffix = 2
        while operation_id in operations:
            duplicates.append(f"{base} (renamed {operation_id}-{suffix})")
            operation_id = f"{base}-{suffix}"
            suffix += 1
        operations[operation_id] = {
            "id": operation_id,
            "product": product,
            "method": method,
            "path": path,
            "description": _description(product, row),
            "documented_version": _version(product),
            "kind": "json",
            "arguments": _arguments(path),
        }

    document: dict[str, object] = {
        "schema": "atlawire-read-manifest/v1",
        "source": "versioned endpoint mappings",
        "operations": [operations[key] for key in sorted(operations)],
        "deferred": deferred,
    }
    return document, deferred, duplicates


def render(document: dict[str, object]) -> str:
    """Return the exact committed on-disk text for one manifest document."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Manifest path to write or check.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed manifest differs from the regenerated one.",
    )
    args = parser.parse_args(argv)

    document, deferred, duplicates = build_document()
    rendered = render(document)
    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except OSError:
            print(f"manifest missing: {args.output}")
            return 1
        if current != rendered:
            print(f"manifest outdated: {args.output}")
            return 1
        print("manifest current")
    else:
        args.output.write_text(rendered, encoding="utf-8")

    operations = document["operations"]
    if not isinstance(operations, list):
        print("manifest operations are not a list")
        return 1
    print(f"operations: {len(operations)}")
    print(f"deferred: {len(deferred)}")
    for item in deferred:
        print(f"  {item['product']}: {item['path']} -> {item['reason']}")
    if duplicates:
        print(f"renamed duplicates: {len(duplicates)}")
        for item in duplicates:
            print(f"  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the runtime read manifest from the versioned endpoint mappings.

The mapping files are analysis artifacts under `.planning/`; this script turns
them into one compact, reviewed runtime list. Run it from the repository root:

    C:/Python315/python.exe -B tools/build_read_manifest.py

It writes `src/atlawire/manifest.json`. Binary, text and plugin-only endpoints
are reported as deferred with the reason instead of being silently dropped.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = ROOT / ".planning" / "2026-11-22-read-only-rest-and-bbk-parity"
OUTPUT = ROOT / "src" / "atlawire" / "manifest.json"

# Endpoints whose body is not JSON, or which the core reference does not
# define. They stay in the release inventory with an explicit disposition.
# Match the route's own shape, not a substring like "/content/": Confluence
# content routes are JSON.
_DEFERRED_SUFFIXES = ("/archive", "/raw", "/raw/", "/download")
_DEFERRED_MARKERS = ("/avatar", ".png", "/markup/preview")
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
        document = json.loads((MAPPINGS / name).read_text(encoding="utf-8"))
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
    if lowered.endswith(_DEFERRED_SUFFIXES):
        return "non-JSON body (archive, raw or download)"
    for marker in _DEFERRED_MARKERS:
        if marker in lowered:
            return f"non-JSON body ({marker})"
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


def main() -> int:
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
                {"product": product, "path": path, "reason": "documented inconsistently"}
            )
            continue
        if method == "POST":
            deferred.append(
                {
                    "product": product,
                    "path": path,
                    "reason": "semantic POST needs a documented body schema",
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

    document = {
        "schema": "atlawire-read-manifest/v1",
        "source": "versioned endpoint mappings",
        "operations": [operations[key] for key in sorted(operations)],
        "deferred": deferred,
    }
    OUTPUT.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
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

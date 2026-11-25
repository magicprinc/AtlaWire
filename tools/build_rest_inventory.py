"""Freeze the release REST inventory and check it against the runtime registry.

The versioned mapping files under `.development/<product>/` are the only
denominator this project has ever had. This script turns their 252 documented
read rows into one frozen artifact, `.development/rest-inventory.json`, with an
explicit disposition per row, and then checks two directions:

* every row it calls ``required`` has a registered runtime operation;
* every registered runtime operation is either ``required`` or named as one of
  the few deliberate additions that the mappings do not document.

The check is the point. A frozen number is only useful if drift in either
direction fails loudly, so ``--check`` compares bytes and then re-verifies the
freshly built document, not the file on disk.

Run it from the repository root:

    C:/Python315/python.exe -B tools/build_rest_inventory.py
    C:/Python315/python.exe -B tools/build_rest_inventory.py --check
"""

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = ROOT / ".development"
OUTPUT = MAPPINGS / "rest-inventory.json"

SCHEMA = "atlawire-rest-inventory/v1"
_PLACEHOLDER = re.compile(r"\{[^{}]+\}")

# The four audit GETs that Confluence's mapping excludes by a prose rule rather
# than by a row. They are named in `inventory_provenance.exclusion_rule`, which
# `_rule_text_names_every_audit_path` re-checks on every build, so this tuple
# cannot drift away from the evidence silently.
_CONFLUENCE_AUDIT = (
    "/rest/audit",
    "/rest/audit/export",
    "/rest/audit/retention",
    "/rest/audit/since",
)

# Bitbucket segments that make a route administrative or system-level, matching
# the runtime path validator. `/settings/...` is PROJECT_ADMIN-only in the 5.10
# reference; `application-properties` has no SDK builder at all.
_BITBUCKET_ADMIN_SEGMENTS = frozenset({"settings"})
_BITBUCKET_SYSTEM_SEGMENTS = frozenset({"application-properties"})

_VERSION = {
    "jira": "Jira Server 8.22.0 REST API 2",
    "confluence": "Confluence Server 6.6.0 REST API",
    "bitbucket": "Bitbucket Server 5.10.0 REST API 1.0",
}
_SOURCE = {
    "jira": ".development/jira/mapping-jira.json",
    "confluence": ".development/confluence/mapping-confluence.json",
    "bitbucket": ".development/bitbucket/mapping-bitbucket.json",
}

# One registered runtime operation has no documented row: the binary attachment
# reader. It is kept and named here instead of being folded into the required
# set, so the two-way check stays exact. Keys are normalized with the same rule
# as the registry, so placeholder names cannot break the comparison.
_REGISTERED_ADDITIONS_SOURCE = {
    ("jira", "GET", "/rest/api/2/attachment/{id}/content"): (
        "Binary attachment reader registered in the runtime registry; the "
        "versioned mapping documents the expand/raw variant instead."
    ),
}


# The frozen totals. A change in any of them is a release decision, not a
# routine regeneration, so the check fails until this table is updated.
_EXPECTED = {
    "documented_rows": 252,
    "required": 201,
    "excluded": 51,
    "unresolved": 0,
    "runtime_operations": 202,
}
# Per-product counts. Without them a global total could be satisfied by two
# compensating mistakes, one product short and another long.
_EXPECTED_PRODUCT = {
    "jira": {"required": 108, "excluded": 5},
    "confluence": {"required": 36, "excluded": 0},
    "bitbucket": {"required": 57, "excluded": 42},
}
# Digest of the sorted normalized exclusions per product. Counting excluded rows
# is not enough: swapping one for another keeps every total identical, so the
# identity of what was excluded has to be pinned too.
_EXPECTED_EXCLUDED_DIGEST: dict[str, str] = {
    "jira": "fe0a49d5fb2048de60981768d7a5bc9cab410630ff1788e67b1caf42d2abfa2c",
    "confluence": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "bitbucket": "864595cb50f98f93704cbe56854ed5dbaffa67ebf483dd06b1dd4ec175602460",
}

_REASON_TEXT = {
    "administrative": "Administrative, project-admin or system route.",
    "authorization-uncertain": "Only HTTP 200 is documented; authorization is unstated.",
    "documented-inconsistently": "Documented as a GET but changes state; the same path is a POST.",
    "system-route": "No SDK builder and the runtime path validator refuses the segment.",
}


@dataclass(frozen=True, slots=True)
class _Row:
    """One documented read row before it receives a disposition."""

    product: str
    method: str
    path: str
    mapping_status: str


def normalize_path(path: str) -> str:
    """Collapse placeholder names so two spellings of one route compare equal."""
    return _PLACEHOLDER.sub("{}", path.rstrip("/"))


def _is_audit_path(path: str) -> bool:
    """Match only the four audit routes the mapping names, exactly.

    A prefix test would also exclude an unseen child such as
    ``/rest/audit/records`` as administrative, which is a decision the mapping
    never made. Narrower is safer: an unnamed route stays required, and the
    two-way check forces an explicit decision the moment it appears.
    """
    return path in _CONFLUENCE_AUDIT


def _excluded_digest(rows: Sequence[Mapping[str, object]]) -> str:
    """Return a stable digest over the identity of the excluded rows."""
    keys = sorted(
        f"{row['method']} {normalize_path(str(row['path']))} {row.get('reason', '?')}"
        for row in rows
        if row["disposition"] == "excluded"
    )
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def _registered_additions() -> dict[tuple[str, str, str], str]:
    """Return the registered additions keyed the way the registry is keyed."""
    return {
        (product, method, normalize_path(path)): reason
        for (product, method, path), reason in _REGISTERED_ADDITIONS_SOURCE.items()
    }


def _read(product: str, name: str) -> Mapping[str, object]:
    document = json.loads((MAPPINGS / product / name).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit(f"unexpected mapping shape: {product}/{name}")
    return document


def _entries(document: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = document[key]
    if not isinstance(value, list):
        raise SystemExit(f"expected a list under {key}")
    return [item for item in value if isinstance(item, dict)]


def _mapping(document: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    value: object = document
    for key in keys:
        if not isinstance(value, dict):
            raise SystemExit(f"expected an object under {'/'.join(keys)}")
        value = value.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"expected an object under {'/'.join(keys)}")
    return value


def _strings(document: Mapping[str, object], *keys: str) -> list[str]:
    """Read a string list that sits under one or more mapping objects."""
    parent = _mapping(document, *keys[:-1]) if len(keys) > 1 else document
    value = parent[keys[-1]]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SystemExit(f"expected a string list under {'/'.join(keys)}")
    return list(value)


def _rows() -> list[_Row]:
    """Return every documented row, including the ones excluded by rule."""
    rows: list[_Row] = []

    jira = _read("jira", "mapping-jira.json")
    for entry in _entries(jira, "entries"):
        rows.append(
            _Row(
                "jira",
                str(entry["method"]).upper(),
                str(entry["path"]),
                str(entry.get("status")),
            )
        )
    for item in _strings(jira, "excluded", "authorizationUncertain"):
        method, _, path = item.partition(" ")
        rows.append(_Row("jira", method.upper(), path, "authorization-uncertain"))

    confluence = _read("confluence", "mapping-confluence.json")
    for entry in _entries(confluence, "operations"):
        rows.append(
            _Row(
                "confluence",
                str(entry["method"]).upper(),
                str(entry["path"]),
                str(entry.get("status")),
            )
        )

    bitbucket = _read("bitbucket", "mapping-bitbucket.json")
    for entry in _entries(bitbucket, "endpoints"):
        rows.append(
            _Row(
                "bitbucket",
                str(entry["method"]).upper(),
                str(entry["path"]),
                str(entry.get("status")),
            )
        )
    derivation = _mapping(bitbucket, "meta", "denominator_derivation")
    for item in _strings(derivation, "instance_admin_and_ops_get"):
        rows.append(_Row("bitbucket", "GET", item, "instance-admin"))
    for item in _strings(derivation, "project_repo_admin_level_reads"):
        rows.append(_Row("bitbucket", "GET", item.split(" (", 1)[0], "project-admin"))
    return rows


def _disposition(row: _Row) -> tuple[str, str]:
    """Return ``(disposition, reason)`` for one documented row."""
    if row.mapping_status == "authorization-uncertain":
        return "excluded", "authorization-uncertain"
    if row.mapping_status == "uncertain":
        return "excluded", "documented-inconsistently"
    if row.mapping_status in {"instance-admin", "project-admin"}:
        return "excluded", "administrative"
    if row.product == "confluence" and _is_audit_path(row.path):
        return "excluded", "administrative"
    if row.product == "bitbucket":
        segments = {part for part in row.path.split("/") if part}
        if segments & _BITBUCKET_ADMIN_SEGMENTS:
            return "excluded", "administrative"
        if segments & _BITBUCKET_SYSTEM_SEGMENTS:
            return "excluded", "system-route"
    return "required", ""


def _registry() -> dict[tuple[str, str, str], list[dict[str, object]]]:
    """Index the live registry by product, method and normalized path."""
    from atlawire import operations

    index: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for described in operations.list_operations():
        key = (
            str(described["product"]),
            str(described["method"]),
            normalize_path(str(described["path"])),
        )
        index.setdefault(key, []).append(described)
    return index


def _rule_text_names(rule: str, path: str) -> bool:
    """Match one audit path as a whole token, never as a prefix of a longer one.

    A plain substring test lets `/rest/audit` be "found" inside
    `/rest/audit/export`, so prose that dropped the bare path would still pass.
    """
    pattern = rf"{re.escape(path)}(?![\w/-])"
    return re.search(pattern, rule) is not None


def _rule_text_names_every_audit_path() -> list[str]:
    """Prove the hard-coded audit exclusion still matches the mapping prose."""
    document = _read("confluence", "mapping-confluence.json")
    provenance = _mapping(document, "inventory_provenance")
    rule = provenance.get("exclusion_rule")
    if not isinstance(rule, str):
        return ["confluence exclusion_rule is missing from the mapping"]
    return [
        f"confluence exclusion_rule does not name {path}"
        for path in _CONFLUENCE_AUDIT
        if not _rule_text_names(rule, path)
    ]


def build_document() -> dict[str, object]:
    """Build the frozen inventory document and its per-row dispositions."""
    registry = _registry()
    products: dict[str, object] = {}
    for product, version in _VERSION.items():
        rows = [row for row in _rows() if row.product == product]
        rows.sort(key=lambda row: (row.method, row.path))
        described_rows: list[dict[str, object]] = []
        by_reason: dict[str, int] = {}
        required = 0
        for row in rows:
            disposition, reason = _disposition(row)
            matches = registry.get(
                (product, row.method, normalize_path(row.path)),
                [],
            )
            entry: dict[str, object] = {
                "method": row.method,
                "path": row.path,
                "disposition": disposition,
                "mapping_status": row.mapping_status,
                "registered": bool(matches),
                "runtime_operation_id": matches[0]["id"] if matches else None,
                "response_kind": (matches[0]["response"]["kind"] if matches else None),
            }
            if reason:
                entry["reason"] = reason
                entry["reason_text"] = _REASON_TEXT[reason]
                by_reason[reason] = by_reason.get(reason, 0) + 1
            else:
                required += 1
            described_rows.append(entry)
        products[product] = {
            "documented_version": version,
            "mapping_source": _SOURCE[product],
            "rows": described_rows,
            "counts": {
                "rows": len(rows),
                "required": required,
                "excluded": len(rows) - required,
                "excluded_by_reason": dict(sorted(by_reason.items())),
            },
            "excluded_by_rule": (
                [
                    {
                        "method": "GET",
                        "path": path,
                        "reason": "administrative",
                        "reason_text": _REASON_TEXT["administrative"],
                        "note": "Named in the mapping's exclusion_rule; never a row.",
                    }
                    for path in _CONFLUENCE_AUDIT
                ]
                if product == "confluence"
                else []
            ),
        }

    required_keys = {
        (product, str(row["method"]), normalize_path(str(row["path"])))
        for product, block in products.items()
        if isinstance(block, dict)
        for row in _rows_of(block)
        if row["disposition"] == "required"
    }
    missing_additions = [key for key in _registered_additions() if key not in registry]
    if missing_additions:
        raise SystemExit(f"declared additions are not registered: {missing_additions}")
    promoted = [key for key in _registered_additions() if key in required_keys]
    if promoted:
        raise SystemExit(
            "declared additions are now documented required rows; remove them "
            f"from _REGISTERED_ADDITIONS_SOURCE: {promoted}"
        )
    additions = [
        {
            "runtime_operation_id": described[0]["id"],
            "product": described[0]["product"],
            "method": described[0]["method"],
            "path": described[0]["path"],
            "reason": _registered_additions()[key],
        }
        for key, described in registry.items()
        if key not in required_keys and key in _registered_additions()
    ]

    totals = {
        "documented_rows": len(_rows()) + len(_CONFLUENCE_AUDIT),
        "rows_with_disposition": len(_rows()),
        "required": sum(
            int(block["counts"]["required"])
            for block in products.values()
            if isinstance(block, dict)
        ),
        "excluded": sum(
            int(block["counts"]["excluded"])
            for block in products.values()
            if isinstance(block, dict)
        )
        + len(_CONFLUENCE_AUDIT),
        "unresolved": sum(
            1
            for block in products.values()
            if isinstance(block, dict)
            for row in _rows_of(block)
            if row["disposition"] not in {"required", "excluded"}
        ),
        "runtime_operations": sum(len(value) for value in registry.values()),
    }
    return {
        "schema": SCHEMA,
        "note": (
            "Frozen release denominator. `required` rows must have a runtime "
            "operation; every runtime operation must be required or listed in "
            "`registered_additions`. Regenerate with tools/build_rest_inventory.py."
        ),
        "totals": totals,
        "products": products,
        "registered_additions": additions,
    }


def _rows_of(block: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = block["rows"]
    if not isinstance(rows, list):
        raise SystemExit("expected row objects in the product block")
    return [row for row in rows if isinstance(row, dict)]


def verify(document: Mapping[str, object]) -> list[str]:
    """Return every inconsistency between the artifact, the freeze and the registry.

    Three questions, no more: do the frozen totals match, does every required row
    resolve to a registered operation (and every registered operation have a
    disposition), and is the excluded set still the reviewed one. A hand-edited
    artifact is already caught by the byte comparison in ``main``, so this
    function does not re-validate the document against itself.
    """
    problems: list[str] = []
    totals = document["totals"]
    if not isinstance(totals, dict):
        return ["totals is not an object"]
    for name, expected in _EXPECTED.items():
        if totals.get(name) != expected:
            problems.append(f"{name}: expected {expected}, built {totals.get(name)}")

    products = document["products"]
    additions = document["registered_additions"]
    if not isinstance(products, dict) or not isinstance(additions, list):
        return [*problems, "products or registered_additions has the wrong shape"]

    registry = _registry()
    seen: set[tuple[str, str, str]] = set()
    for product, block in products.items():
        if not isinstance(block, dict):
            problems.append(f"{product}: block is not an object")
            continue
        rows = _rows_of(block)
        expected_counts = _EXPECTED_PRODUCT.get(product)
        if expected_counts is None:
            problems.append(f"{product}: no frozen counts")
            continue
        required = [row for row in rows if row["disposition"] == "required"]
        excluded = [row for row in rows if row["disposition"] == "excluded"]
        if len(required) != expected_counts["required"]:
            problems.append(
                f"{product} required: expected {expected_counts['required']}, "
                f"rows say {len(required)}"
            )
        if len(excluded) != expected_counts["excluded"]:
            problems.append(
                f"{product} excluded: expected {expected_counts['excluded']}, "
                f"rows say {len(excluded)}"
            )
        if len(required) + len(excluded) != len(rows):
            problems.append(f"{product}: a row has no final disposition")
        for row in rows:
            key = (product, str(row["method"]), normalize_path(str(row["path"])))
            registered = key in registry
            if row["disposition"] == "required":
                if registered:
                    seen.add(key)
                else:
                    problems.append(
                        f"{product} {row['method']} {row['path']}: "
                        "required but unregistered"
                    )
            elif registered:
                problems.append(
                    f"{product} {row['method']} {row['path']}: excluded but registered"
                )
        digest = _excluded_digest(rows)
        if _EXPECTED_EXCLUDED_DIGEST.get(product) != digest:
            problems.append(
                f"{product} excluded set changed: {digest}; review the swap, then "
                "update _EXPECTED_EXCLUDED_DIGEST"
            )

    for addition in additions:
        if not isinstance(addition, dict):
            problems.append("registered_additions holds a non-object")
            continue
        key = (
            str(addition["product"]),
            str(addition["method"]),
            normalize_path(str(addition["path"])),
        )
        if key not in registry:
            problems.append(f"addition is not registered: {addition['path']}")
        if key in seen:
            problems.append(f"addition duplicates a required row: {addition['path']}")
        seen.add(key)

    problems.extend(
        f"runtime operation unaccounted for: {key[0]} {key[1]} {key[2]}"
        for key in registry
        if key not in seen
    )
    problems.extend(_rule_text_names_every_audit_path())
    return problems


def operations_census() -> list[dict[str, object]]:
    """Return the live registry rows used by the duplicate-key guard."""
    from atlawire import operations

    return operations.list_operations()


def render(document: Mapping[str, object]) -> str:
    """Return the exact committed on-disk text for one inventory document."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Inventory path to write or check.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed inventory differs or the two-way check fails.",
    )
    args = parser.parse_args(argv)

    document = build_document()
    rendered = render(document)
    problems = verify(document)
    status = 0
    if problems and not args.check:
        # A failing build must not overwrite a reviewed artifact.
        print("refusing to write: the two-way check failed")
    elif args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except OSError:
            print(f"inventory missing: {args.output}")
            status = 1
        else:
            if current != rendered:
                print(f"inventory outdated: {args.output}")
                status = 1
            else:
                print("inventory current")
    else:
        args.output.write_text(rendered, encoding="utf-8")

    totals = document["totals"]
    if not isinstance(totals, dict):
        print("inventory totals are not an object")
        return 1
    print(f"documented rows: {totals['documented_rows']}")
    print(f"required: {totals['required']}")
    print(f"excluded: {totals['excluded']}")
    print(f"runtime operations: {totals['runtime_operations']}")
    if problems:
        print(f"two-way check failed: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("two-way check passed")
    return status


if __name__ == "__main__":
    sys.exit(main())

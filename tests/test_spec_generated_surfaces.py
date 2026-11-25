"""Both generated surfaces must be fixed points.

A generator that reads the registry it feeds will treat its own output as a
pre-existing declaration and emit less on the next run. That happened twice: once
in the query surface and once in the admin surface. These tests make the second
run identical to the first, which is the property that was broken.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "src" / "atlawire" / "admin_operations.json"
QUERY = ROOT / "src" / "atlawire" / "query_params.json"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_admin_surface_is_the_regenerated_file():
    builder = _load("build_admin_surface", "build_admin_surface.py")

    assert builder.render(builder.build()) == ADMIN.read_text(encoding="utf-8")


def test_query_surface_is_the_regenerated_file():
    builder = _load("build_query_surface_idem", "build_query_surface.py")

    assert builder.render(builder.build()) == QUERY.read_text(encoding="utf-8")


def test_admin_surface_never_becomes_empty():
    """The precise failure: a second run must not see its own rows as existing."""
    document = json.loads(ADMIN.read_text(encoding="utf-8"))

    assert len(document["operations"]) > 100


def test_query_surface_does_not_duplicate_admin_parameters():
    """Admin parameters live in the admin artifact, not in both files."""
    admin = json.loads(ADMIN.read_text(encoding="utf-8"))
    query = json.loads(QUERY.read_text(encoding="utf-8"))
    admin_ids = {row["id"] for row in admin["operations"]}

    assert admin_ids.isdisjoint(query["operations"]), (
        "an operation appears in both generated files"
    )


def test_both_generators_agree_with_the_registry():
    from atlawire import operations

    registered = {item["id"]: item for item in operations.list_operations()}
    admin = json.loads(ADMIN.read_text(encoding="utf-8"))

    for row in admin["operations"]:
        declared = registered.get(row["id"])
        assert declared is not None, row["id"]
        assert declared["scope"] == "admin", row["id"]
        assert declared["path"] == row["path"], row["id"]

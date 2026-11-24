"""Contracts for the generated read manifest and its runtime projection."""

import importlib.util
import json
from pathlib import Path

import pytest

from atlawire import operations
from atlawire.http import AtlaWireError

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "src" / "atlawire" / "manifest.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "build_read_manifest", ROOT / "tools" / "build_read_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_manifest_is_the_regenerated_projection():
    """The committed manifest must equal a fresh build from the live mappings."""
    generator = _load_generator()
    document, _, _ = generator.build_document()

    assert generator.render(document) == MANIFEST.read_text(encoding="utf-8")


def test_every_manifest_route_is_installed_in_the_registry():
    """A manifest row that the registry silently drops is a broken projection."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_routes = {
        (entry["product"], entry["method"], entry["path"])
        for entry in manifest["operations"]
    }
    registry_routes = {
        (entry["product"], entry["method"], entry["path"])
        for entry in operations.list_operations()
    }

    assert manifest_routes - registry_routes == set()


def test_missing_or_invalid_manifest_fails_closed(monkeypatch, tmp_path):
    """A broken packaged manifest must not silently shrink the registry."""
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(operations, "_MANIFEST_PATH", missing)
    with pytest.raises(AtlaWireError, match="read manifest"):
        operations._manifest_entries()

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(operations, "_MANIFEST_PATH", invalid)
    with pytest.raises(AtlaWireError, match="read manifest"):
        operations._manifest_entries()

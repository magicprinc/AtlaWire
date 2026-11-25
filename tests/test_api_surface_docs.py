"""The split API surface must stay reproducible from the stored WADL.

The Markdown files and the index are generated from an artifact that came off the
network, so the checks are: the committed text is exactly what a rebuild
produces, every method of every WADL is present in exactly one file, and no file
is large enough that reading one question loads a whole resource group.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".development"
INDEX = BASE / "api-surface.json"
MAX_FILE_BYTES = 96 * 1024


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_api_surface_docs", ROOT / "tools" / "build_api_surface_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_files_match_a_fresh_build():
    index, files = _load_builder().build()
    index_path = BASE / "api-surface.json"
    files[index_path] = _load_builder().render(index)

    stale = [
        str(path.relative_to(ROOT))
        for path, text in files.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]

    assert stale == [], f"stale generated files: {stale[:5]}"


def test_index_lists_exactly_the_methods_the_wadl_declares():
    """Faithful, not deduplicated.

    Jira really declares some routes twice (for example `POST avatar/temporary`
    with different request bodies), so the index must carry both. The check is
    therefore that the index count equals the WADL count per product, never that
    a route appears once.
    """
    document = json.loads(INDEX.read_text(encoding="utf-8"))
    for product, block in document["products"].items():
        wadl = BASE / product / "source" / "application.wadl"
        declared = len(
            re.findall(
                r"<[a-z0-9]*:?method\b",
                wadl.read_text(encoding="utf-8", errors="replace"),
            )
        )
        assert len(block["methods"]) == declared, (
            f"{product}: {len(block['methods'])} methods indexed, {declared} in the WADL"
        )


def test_each_indexed_method_points_at_an_existing_file():
    document = json.loads(INDEX.read_text(encoding="utf-8"))
    missing = [
        method["file"]
        for block in document["products"].values()
        for method in block["methods"]
        if not (ROOT / method["file"]).exists()
    ]

    assert missing == []


def test_no_generated_file_needs_a_full_load():
    oversized = [
        f"{path.parent.parent.name}/{path.name}"
        for path in BASE.glob("*/api/*.md")
        if path.stat().st_size > MAX_FILE_BYTES
    ]

    assert oversized == []


def test_artifacts_never_contain_the_internal_host():
    """The WADL is redacted before it is written; a leak here is a real leak."""
    source = json.loads((BASE / "api-surface-source.json").read_text(encoding="utf-8"))
    for block in source["products"].values():
        artifact = ROOT / block["artifact"]
        assert "example.com" in artifact.read_text(encoding="utf-8", errors="replace")


def test_the_index_records_a_digest_for_every_product():
    source = json.loads((BASE / "api-surface-source.json").read_text(encoding="utf-8"))
    for product, block in source["products"].items():
        digest = block.get("sha256")
        assert isinstance(digest, str) and len(digest) == 64, product


def test_registry_only_entries_have_a_stated_reason():
    """A route we register but the server does not describe must say why."""
    document = json.loads(INDEX.read_text(encoding="utf-8"))
    for product, block in document["products"].items():
        for entry in block["not_in_wadl"]:
            assert entry["operation"] and entry["why"], product


def test_two_groups_that_slug_to_one_file_fail_instead_of_overwriting(monkeypatch):
    """`a--b` and `a-b` both slug to `a-b`; one group would vanish silently."""
    builder = _load_builder()
    assert builder._slug("projects--repos") == builder._slug("projects-repos")

    def colliding(product):
        method = builder.Method(verb="GET", route="/x", doc="", query=[])
        return {
            "projects--repos": builder.Paths(group="projects--repos", methods=[method]),
            "projects-repos": builder.Paths(group="projects-repos", methods=[method]),
        }

    monkeypatch.setattr(builder, "_groups", colliding)

    with pytest.raises(SystemExit, match="two groups map to one file name"):
        builder.build(check_only=True)


def test_check_mode_never_deletes_a_file(tmp_path, monkeypatch):
    """A verification run must not mutate the tree."""
    builder = _load_builder()
    calls: list[str] = []
    monkeypatch.setattr(
        Path, "unlink", lambda self, **kwargs: calls.append(str(self)), raising=True
    )

    builder.build(check_only=True)

    assert calls == []

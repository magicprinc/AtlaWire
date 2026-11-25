"""The API-surface checker must keep the registry honest against the servers.

Two guarantees: the report matches the reviewed baseline, and the baseline itself
cannot silently rot into meaninglessness (a `server_only` list that grows while a
count stays the same would hide a real gap).
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".development"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_api_surface", ROOT / "tools" / "check_api_surface.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_matches_the_reviewed_baseline():
    checker = _load_checker()

    assert checker.problems(checker.compare()) == []


def test_every_registered_route_the_server_serves_is_matched():
    """A route in both places but counted as a difference would be a bug here."""
    checker = _load_checker()
    report = checker.compare()

    for product, block in report.items():
        assert block["matched"] + len(block["server_only"]) == block["server_get"], (
            product
        )
        assert (
            block["matched"] + len(block["registry_only"]) == block["registered_get"]
        ), product


def test_baseline_counts_and_digests_are_consistent_with_the_lists():
    """Both the counts and the identity of the lists must match the baseline."""
    checker = _load_checker()
    report = checker.compare()

    for product, block in report.items():
        baseline = checker.BASELINE[product]
        assert len(block["server_only"]) == baseline["server_only"]
        assert len(block["registry_only"]) == baseline["registry_only"]
        assert len(block["undeclared_params"]) == baseline["undeclared_param_routes"]
        assert checker._digest(block["server_only"]) == baseline["server_only_sha"]
        assert checker._digest(block["registry_only"]) == baseline["registry_only_sha"]


def test_a_same_count_rename_is_still_reported_as_drift(monkeypatch):
    """Replacing one difference with another keeps counts and must not pass."""
    checker = _load_checker()
    original = checker.compare

    def renamed():
        report = original()
        block = report["confluence"]
        block["server_only"] = [
            *block["server_only"][:-1],
            "GET /renamed-instead-of-the-original",
        ]
        return report

    monkeypatch.setattr(checker, "compare", renamed)

    found = checker.problems(renamed())

    assert any("server_only_sha" in item for item in found)


def test_route_variants_expands_a_glued_suffix_but_keeps_trailing_placeholders():
    """`diff{path}` covers two routes; `/attachment/{id}` stays distinct."""
    checker = _load_checker()

    assert checker.route_variants("/diff{path}") == {"/diff", "/diff/{}"}
    assert checker.route_variants("/attachment/{}") == {"/attachment/{}"}
    assert checker.route_variants("/attachment") == {"/attachment"}


def test_a_new_registered_route_is_reported_as_drift(monkeypatch):
    """Adding a route the server does not serve must fail the check."""
    checker = _load_checker()
    original = checker.registry_index

    def with_extra():
        index = original()
        index["bitbucket"][("GET", "/not-a-real-route")] = set()
        return index

    monkeypatch.setattr(checker, "registry_index", with_extra)

    assert checker.problems(checker.compare()) != []


def test_every_indexed_route_has_a_reason_when_absent_from_the_wadl():
    checker = _load_checker()
    document = json.loads((BASE / "api-surface.json").read_text(encoding="utf-8"))
    covered = {
        checker.normalize(entry["operation"].split(" ", 1)[1])
        for block in document["products"].values()
        for entry in block["not_in_wadl"]
    }

    report = checker.compare()
    unexplained = [
        item
        for block in report.values()
        for item in block["registry_only"]
        if checker.normalize(item.split(" ", 1)[1]) not in covered
    ]

    assert unexplained == [], f"unexplained registry-only routes: {unexplained}"

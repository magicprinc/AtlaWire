"""Regression tests for the review findings: pinned exclusions, boundary rules.

Each case here corresponds to a way the frozen artifact could have passed the
two-way check while being materially wrong.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "build_rest_inventory_guards", ROOT / "tools" / "build_rest_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator():
    return _load_generator()


@pytest.fixture(scope="module")
def built(generator):
    return generator.build_document()


def _product_of(built, row):
    return next(
        product for product, block in built["products"].items() if row in block["rows"]
    )


def test_swapping_one_excluded_row_for_another_fails(generator, built):
    """Totals alone cannot catch a swap; the pinned digest must."""
    broken = generator.json.loads(generator.json.dumps(built))
    block = broken["products"]["bitbucket"]
    excluded = [row for row in block["rows"] if row["disposition"] == "excluded"]
    assert excluded
    dropped = excluded[0]
    replacement = dict(dropped)
    replacement["path"] = dropped["path"] + "-different"
    block["rows"] = [replacement if row is dropped else row for row in block["rows"]]

    problems = generator.verify(broken)

    assert any("excluded set changed" in problem for problem in problems)


def test_a_fifth_audit_path_is_not_excluded_by_prefix(generator):
    """`startswith('/rest/audit')` would silently swallow an unseen audit route."""
    assert generator._is_audit_path("/rest/audit")
    assert generator._is_audit_path("/rest/audit/export")
    assert not generator._is_audit_path("/rest/audit/records")
    assert not generator._is_audit_path("/rest/audit-trail")


def test_rule_prose_must_name_the_bare_audit_path(generator):
    """`/rest/audit` inside `/rest/audit/export` is not evidence."""
    assert generator._rule_text_names(
        "covers /rest/audit, /rest/audit/export", "/rest/audit"
    )
    assert not generator._rule_text_names(
        "covers /rest/audit/export only", "/rest/audit"
    )


def test_row_level_compensation_fails_even_when_counts_are_consistent(generator, built):
    """Dropping a required row and calling another one required keeps counts."""
    broken = generator.json.loads(generator.json.dumps(built))
    block = broken["products"]["jira"]
    required = [row for row in block["rows"] if row["disposition"] == "required"]
    excluded = [row for row in block["rows"] if row["disposition"] == "excluded"]
    required[0]["disposition"] = "excluded"
    excluded[0]["disposition"] = "required"
    block["counts"]["required"] = sum(
        1 for row in block["rows"] if row["disposition"] == "required"
    )
    block["counts"]["excluded"] = sum(
        1 for row in block["rows"] if row["disposition"] == "excluded"
    )

    problems = generator.verify(broken)

    assert any("required but unregistered" in problem for problem in problems)
    assert any("excluded but registered" in problem for problem in problems)


def test_counts_disagreeing_with_rows_fail(generator, built):
    broken = generator.json.loads(generator.json.dumps(built))
    broken["products"]["jira"]["counts"]["excluded"] = 6

    problems = generator.verify(broken)

    assert any("counts.excluded disagrees" in problem for problem in problems)


def test_unresolved_is_derived_not_hardcoded(generator, built):
    broken = generator.json.loads(generator.json.dumps(built))
    row = broken["products"]["jira"]["rows"][0]
    row["disposition"] = "unresolved"

    problems = generator.verify(broken)

    assert any("no final disposition" in problem for problem in problems)


def test_a_declared_addition_missing_from_the_registry_is_refused(
    generator, monkeypatch
):
    """A stale addition entry must break the build, not vanish from the output."""
    monkeypatch.setitem(
        generator._REGISTERED_ADDITIONS_SOURCE,
        ("jira", "GET", "/rest/api/2/never-registered"),
        "stale entry",
    )
    with pytest.raises(SystemExit, match="declared additions are not registered"):
        generator.build_document()


def test_generation_refuses_to_write_a_failing_inventory(
    generator, monkeypatch, tmp_path
):
    """A failing run must not overwrite a reviewed artifact."""
    monkeypatch.setattr(
        generator, "_EXPECTED", {**generator._EXPECTED, "required": 999}
    )
    target = tmp_path / "rest-inventory.json"

    code = generator.main(["--output", str(target)])

    assert code == 1
    assert not target.exists()


def test_check_fails_when_the_two_way_check_fails_but_bytes_match(
    generator, monkeypatch, tmp_path
):
    """Byte equality alone is not a pass; the directions are re-verified."""
    target = tmp_path / "rest-inventory.json"
    target.write_text(generator.render(generator.build_document()), encoding="utf-8")
    monkeypatch.setattr(
        generator, "_EXPECTED_PRODUCT", {"jira": {"required": 1, "excluded": 5}}
    )

    code = generator.main(["--check", "--output", str(target)])

    assert code == 1


def test_a_promoted_addition_fails_instead_of_vanishing(generator, monkeypatch):
    """An addition that becomes a documented row must be removed deliberately."""
    base = generator._rows()
    promoted = generator._Row(
        "jira", "GET", "/rest/api/2/attachment/{id}/content", "covered"
    )
    monkeypatch.setattr(generator, "_rows", lambda: [*base, promoted])

    with pytest.raises(SystemExit, match="now documented required rows"):
        generator.build_document()


def test_disposition_routes_an_unnamed_audit_child_to_required(generator):
    """The predicate is wired into the rule, not only testable in isolation."""
    row = generator._Row("confluence", "GET", "/rest/audit/records", "covered")

    assert generator._disposition(row) == ("required", "")
    named = generator._Row("confluence", "GET", "/rest/audit/export", "covered")
    assert generator._disposition(named) == ("excluded", "administrative")


def test_registered_flag_disagreeing_with_the_registry_fails(generator, built):
    broken = generator.json.loads(generator.json.dumps(built))
    row = next(
        row
        for block in broken["products"].values()
        for row in block["rows"]
        if row["disposition"] == "required"
    )
    row["registered"] = False

    problems = generator.verify(broken)

    assert any("registered flag disagrees" in problem for problem in problems)


def test_response_kind_disagreeing_with_the_registry_fails(generator, built):
    broken = generator.json.loads(generator.json.dumps(built))
    row = next(
        row
        for block in broken["products"].values()
        for row in block["rows"]
        if row["disposition"] == "required"
    )
    row["response_kind"] = "not-a-kind"

    problems = generator.verify(broken)

    assert any("response_kind disagrees" in problem for problem in problems)


def test_reason_reclassification_fails_the_digest(generator, built):
    """administrative -> system-route keeps counts but changes the evidence."""
    broken = generator.json.loads(generator.json.dumps(built))
    block = broken["products"]["bitbucket"]
    row = next(row for row in block["rows"] if row["disposition"] == "excluded")
    row["reason"] = "system-route"
    row["reason_text"] = generator._REASON_TEXT["system-route"]

    problems = generator.verify(broken)

    assert any("excluded set changed" in problem for problem in problems)
    assert any("excluded_by_reason disagrees" in problem for problem in problems)


def test_counts_rows_disagreeing_with_the_row_list_fails(generator, built):
    broken = generator.json.loads(generator.json.dumps(built))
    broken["products"]["jira"]["counts"]["rows"] = 999

    problems = generator.verify(broken)

    assert any("counts.rows disagrees" in problem for problem in problems)


def test_prose_naming_an_extra_audit_route_is_flagged(generator, monkeypatch):
    document = generator._read("confluence", "mapping-confluence.json")
    provenance = document["inventory_provenance"]
    original = provenance["exclusion_rule"]
    provenance["exclusion_rule"] = f"{original} Also /rest/audit/records."
    monkeypatch.setattr(generator, "_read", lambda product, name: document)

    extra = generator._rule_text_extra_paths()

    assert extra == ["/rest/audit/records"]


def test_generation_writes_when_the_check_passes(generator, tmp_path):
    """The success branch must stay exercised, not only the refusal path."""
    target = tmp_path / "rest-inventory.json"

    code = generator.main(["--output", str(target)])

    assert code == 0
    assert target.read_text(encoding="utf-8") == generator.render(
        generator.build_document()
    )

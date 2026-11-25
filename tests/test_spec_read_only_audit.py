"""The read-only audit must fail on the class it cannot read, not pass silently.

Most declared routes carry the server's own documentation, so the audit can read
their purpose. Fifty-six do not. For those, the first-word test has nothing to
read and used to pass unconditionally: an undocumented route whose path names a
change (the shape of Jira's `GET .../subtask/move`) would have been accepted. The
audit now falls back to the path segments for exactly that case, and it refuses a
parameter whose documented effect is a change.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_read_only_audit", ROOT / "tools" / "check_read_only.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(**overrides):
    base = {
        "id": "jira.probe",
        "product": "jira",
        "method": "GET",
        "path": "/rest/api/2/probe",
        "scope": "read",
        "query": [],
    }
    base.update(overrides)
    return base


def test_an_undocumented_route_with_a_change_in_its_path_is_reported():
    checker = _checker()

    problems = checker.audit(
        [_entry(id="jira.synthetic.move", path="/rest/api/2/synthetic/move")]
    )

    assert any("no documentation" in line and "move" in line for line in problems)


def test_an_undocumented_route_without_a_change_segment_is_accepted():
    checker = _checker()

    assert checker.audit([_entry(path="/rest/api/2/synthetic/read")]) == []


def test_a_documented_read_is_accepted():
    checker = _checker()

    assert checker.audit([_entry(path="/rest/api/2/issue/{issueIdOrKey}")]) == []


def test_an_undocumented_transition_route_is_reported():
    """`create`, `update` and `transition` are the shapes that mutate most often."""
    checker = _checker()

    problems = checker.audit(
        [_entry(product="confluence", path="/rest/api/content/transition")]
    )

    assert problems


def test_a_declared_side_effect_parameter_is_reported():
    """Even a documented GET must not offer a parameter that changes state."""
    checker = _checker()

    problems = checker.audit(
        [
            _entry(
                path="/rest/api/2/issue/{issueIdOrKey}",
                query=[{"name": "updateHistory"}],
            )
        ]
    )

    assert any("updateHistory" in line for line in problems)


def test_the_committed_registry_passes_the_weaker_audit_too():
    checker = _checker()

    assert checker.audit() == []

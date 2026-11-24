"""The BBK migration guide must name real AtlaWire callables and real gaps."""

import re
from pathlib import Path

import atlawire
import atlawire.bitbucket_search
from atlawire import (
    bitbucket,
    bitbucket_attachment,
    confluence,
    confluence_markdown,
    federated,
    identity,
    issue_markdown,
    jira,
    pr_review,
    repo_scan,
)

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "MIGRATION-FROM-BBK.md"

MODULES = {
    "jira": jira,
    "confluence": confluence,
    "bitbucket": bitbucket,
    "confluence_markdown": confluence_markdown,
    "issue_markdown": issue_markdown,
    "pr_review": pr_review,
    "bitbucket_search": atlawire.bitbucket_search,
    "identity": identity,
    "federated": federated,
    "repo_scan": repo_scan,
    "bitbucket_attachment": bitbucket_attachment,
}

MAPPING_ROWS = re.compile(r"^\| `([^`]+)` \| (.+?) \|", re.MULTILINE)


def _guide_text():
    return GUIDE.read_text(encoding="utf-8")


def _referenced_functions(text):
    """Return (module, function) pairs the mapping table promises."""
    found = []
    for _, target in MAPPING_ROWS.findall(text):
        for match in re.finditer(r"`([a-z_]+)\.([A-Za-z_][A-Za-z0-9_]*)`", target):
            found.append((match.group(1), match.group(2)))
    return found


def test_guide_exists_and_is_linked_from_the_index():
    assert GUIDE.is_file()
    index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    assert "MIGRATION-FROM-BBK.md" in index


def test_every_mapped_atlawire_function_exists():
    missing = [
        f"{module}.{name}"
        for module, name in _referenced_functions(_guide_text())
        if module not in MODULES or not callable(getattr(MODULES[module], name, None))
    ]

    assert missing == []


def test_guide_keeps_the_verified_gaps_explicit():
    text = _guide_text()

    for gap in ("pr_compact", "jira.url", "page_storage"):
        assert gap in text
    assert "Bearer only" in text
    assert "No typed-layer retry" in text


def test_the_typed_entry_points_the_guide_relies_on_are_public():
    assert callable(jira.search_issues)
    assert callable(confluence.get_page)
    assert callable(bitbucket.get_repository_file)
    assert callable(identity.whoami)
    assert callable(atlawire.bitbucket_search.search_code)
    assert callable(confluence_markdown.render_page_markdown)
    assert callable(issue_markdown.render_issue_markdown)

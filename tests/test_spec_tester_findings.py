"""Regression tests for the defects the live tester found.

Each test pins one finding so it cannot come back silently. They are offline: the
assertion is on the registry the tools read, not on a live answer.
"""

import inspect
import json
from pathlib import Path

import pytest

from atlawire import operations

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = {entry["id"]: entry for entry in operations.list_operations()}


def _field(operation_id: str, name: str) -> dict[str, object]:
    operation = REGISTRY[operation_id]
    for field in operation["query"] + operation["body"]:
        if field["name"] == name:
            return field
    raise AssertionError(f"{operation_id} does not declare {name}")


@pytest.mark.parametrize(
    ("operation_id", "name"),
    [
        ("bitbucket.admin.groups.more-members", "context"),
        ("bitbucket.admin.groups.more-non-members", "context"),
        ("bitbucket.admin.users.more-members", "context"),
        ("bitbucket.admin.users.more-non-members", "context"),
        ("bitbucket.projects.projectkey.repos.repositoryslug.changes", "until"),
        ("bitbucket.projects.projectkey.repos.repositoryslug.diff.path", "until"),
        (
            (
                "bitbucket.projects.projectkey.repos.repositoryslug"
                ".pull-requests.pullrequestid.comments"
            ),
            "path",
        ),
        ("bitbucket.repository.commit-comments", "path"),
        ("confluence.search", "cql"),
    ],
)
def test_a_parameter_the_server_requires_is_marked_required(operation_id, name):
    """D1: the deployment refuses these without the parameter; the registry said optional."""
    assert _field(operation_id, name)["required"] is True


def test_the_bare_raw_route_is_not_declared_as_a_query_read():
    """D2: `/raw?path=` answers 400; only `/raw/{path:.*}` serves a file."""
    raw = REGISTRY["bitbucket.repository.raw"]
    assert raw["path"].endswith("/raw/{path:.*}")
    assert raw["response"]["kind"] == "binary"
    assert "path" not in {field["name"] for field in raw["query"]}
    assert "path" in {argument["name"] for argument in raw["arguments"]}


def test_the_worklog_body_field_is_the_one_the_server_accepts():
    """D3: `issueIds` is rejected with 'Unrecognized field'; `ids` is accepted."""
    body = REGISTRY["jira.worklog.list"]["body"]
    assert [field["name"] for field in body] == ["ids"]
    assert body[0]["required"] is True


def test_memberof_declares_the_exactly_one_rule():
    """D4: sending both key and username answers 400 on the deployment."""
    rules = REGISTRY["confluence.user.memberof"]["query_rules"]
    assert rules["exactly_one"] == ["key", "username"]


def test_a_post_read_is_reachable_from_the_library_entry_point():
    """D8: a POST used to raise 'requires the library transport' for a library caller."""
    source = inspect.getsource(operations.read_operation)
    assert 'use_library or operation.method != "GET"' in source
    assert "requires the library transport" not in source


def test_the_binary_reader_states_what_it_accepts():
    """D5: an image route answers 406 to the JSON Accept the session sends."""
    from atlawire import sdk

    source = inspect.getsource(sdk._send_binary)
    assert 'accept="*/*"' in source


def test_a_wildcard_file_route_is_never_declared_as_json():
    """The generator must defer `/raw/{path:.*}`; kind json would parse a file as JSON."""
    manifest = json.loads(
        (ROOT / "src" / "atlawire" / "manifest.json").read_text(encoding="utf-8")
    )
    offenders = [
        entry["id"]
        for entry in manifest["operations"]
        if "/raw/" in entry["path"] and entry["path"].endswith("{path:.*}")
    ]
    assert offenders == []


def test_every_registered_route_is_declared_once():
    """A duplicate declaration is how a broken route hid behind a working one."""
    seen = {}
    for entry in REGISTRY.values():
        key = (entry["product"], entry["method"], entry["path"])
        seen.setdefault(key, []).append(entry["id"])
    duplicates = {key: ids for key, ids in seen.items() if len(ids) > 1}
    assert duplicates == {}

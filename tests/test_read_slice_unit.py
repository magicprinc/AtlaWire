"""Offline contracts for the canonical read surface.

Discovery, description and argument validation must work with no credential
file, no network and no environment configuration.
"""

import json

import pytest
from click.testing import CliRunner

import atlawire.cli as cli_module
from atlawire.cli import cli
from atlawire.http import AtlaWireError
from atlawire.operations import (
    CANONICAL_IDS,
    canonical_operations,
    describe_operation,
)

EXPECTED = [
    "bitbucket.repository.get",
    "confluence.space.get",
    "jira.project.get",
]


def forbidden(*args: object, **kwargs: object) -> object:
    raise AssertionError("discovery must not resolve credentials or call out")


@pytest.fixture(autouse=True)
def _no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_product_base_url_and_token", forbidden)
    monkeypatch.setattr(cli_module, "get_json", forbidden)
    monkeypatch.setattr(cli_module, "request_json", forbidden)


def test_canonical_surface_is_the_documented_three_reads() -> None:
    described = canonical_operations()

    assert [entry["id"] for entry in described] == EXPECTED
    assert set(EXPECTED) == CANONICAL_IDS
    for entry in described:
        assert entry["command"] == ["atlawire", "read", entry["id"]]
        argv = entry["example"]["argv"]
        assert argv[:3] == ["atlawire", "read", entry["id"]]
        assert argv[3] == "--params"
        json.loads(argv[4])


def test_describe_exposes_inputs_shape_and_command() -> None:
    described = describe_operation("jira.project.get")

    assert described["product"] == "jira"
    assert described["method"] == "GET"
    assert described["path"] == "/rest/api/2/project/{projectIdOrKey}"
    assert [item["name"] for item in described["arguments"]] == ["projectIdOrKey"]
    assert described["response"]["kind"] == "object"
    assert described["command"] == ["atlawire", "read", "jira.project.get"]
    assert described["example"]["argv"][:3] == [
        "atlawire",
        "read",
        "jira.project.get",
    ]


def test_describe_of_an_unknown_id_raises_a_safe_error() -> None:
    with pytest.raises(AtlaWireError, match="Unknown operation ID"):
        describe_operation("jira.no.such.operation")


def test_catalog_adds_operations_without_losing_legacy_metadata() -> None:
    result = CliRunner().invoke(cli, ["--catalog"])

    assert result.exit_code == 0
    catalog = json.loads(result.output)
    assert catalog["commands"]
    assert "name" in catalog and "help" in catalog
    assert [entry["id"] for entry in catalog["operations"]] == EXPECTED
    for name, entry in catalog["commands"].items():
        assert entry["name"] == name
    # The document must survive a strict round trip unchanged.
    assert json.loads(json.dumps(catalog, allow_nan=False)) == catalog


def test_describe_flag_prints_one_json_document() -> None:
    result = CliRunner().invoke(cli, ["--describe", "bitbucket.repository.get"])

    assert result.exit_code == 0
    described = json.loads(result.output)
    assert described["id"] == "bitbucket.repository.get"
    assert described["example"]["argv"][4] == (
        '{"projectKey":"DEMO","repositorySlug":"example-repository"}'
    )


def test_unknown_describe_is_a_json_usage_error() -> None:
    result = CliRunner().invoke(cli, ["--describe", "jira.missing"])

    assert result.exit_code == 2
    envelope = json.loads(result.output)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] is None
    assert envelope["error"]["code"] == "validation_error"
    assert "jira.missing" not in result.output

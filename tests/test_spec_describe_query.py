"""Contracts for the tri-state `query_documented` verdict in `--describe`.

`True` means at least one query field is declared; `None` means the route's
query surface has not been reconciled with the versioned reference yet; `False`
means verified parameter-free. No operation may claim `False` before that
reconciliation exists, because a false verdict would be an unproven promise.
"""

import json

from click.testing import CliRunner

from atlawire import operations
from atlawire.cli import cli


def _described(operation_id: str) -> dict[str, object]:
    result = CliRunner().invoke(cli, ["--describe", operation_id])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_describe_flags_a_route_with_declared_query_fields():
    described = _described("bitbucket.profile.recent-repositories")

    assert described["query_documented"] is True
    names = [field["name"] for field in described["query"]]
    assert names
    assert {"start", "limit"} <= set(names)


def test_describe_reports_an_unreconciled_route_as_null_not_false():
    # A route whose WADL declares no query parameter keeps `None`: the deployment
    # documents no parameter for it, which is not proof the route takes none.
    described = _described("bitbucket.project.get")

    assert described["query"] == []
    assert described["query_documented"] is None


def test_describe_output_round_trips_through_strict_json():
    """Both states must survive serialization, including the null state."""
    declared = CliRunner().invoke(
        cli, ["--describe", "bitbucket.profile.recent-repositories"]
    )
    unreconciled = CliRunner().invoke(cli, ["--describe", "bitbucket.project.get"])

    assert declared.exit_code == unreconciled.exit_code == 0
    assert json.loads(declared.stdout)["query_documented"] is True
    assert json.loads(unreconciled.stdout)["query_documented"] is None
    assert '"query_documented": null' in unreconciled.stdout


def test_every_description_derives_the_flag_from_its_query_list():
    for described in operations.list_operations():
        expected = True if described["query"] else None
        assert described["query_documented"] is expected, described["id"]


def test_no_operation_claims_a_verified_parameter_free_route():
    """`False` is reserved for a doc reconciliation that has not run yet."""
    verdicts = [entry["query_documented"] for entry in operations.list_operations()]

    assert [verdict for verdict in verdicts if verdict is False] == []


def test_query_documented_matches_the_registry_census():
    """113 declared, 89 unreconciled, 202 total; drift must be deliberate.

    The declared count rose from 22 when the parameters each deployment documents
    in its own WADL were merged in; the rest are routes with no documented query
    surface, which stay ``None`` rather than claiming to take no parameters.
    """
    described = operations.list_operations()

    assert len(described) == 202
    assert sum(1 for entry in described if entry["query_documented"] is True) == 113
    assert sum(1 for entry in described if entry["query_documented"] is None) == 89

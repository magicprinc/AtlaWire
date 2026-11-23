"""Public library surface: consumers import the documented entry points from the root.

Slice 1 of making AtlaWire usable as a Python library. A consumer must be able to
import the offline registry helpers and the read-only facade from ``atlawire``
instead of reaching into private modules. The registry helpers stay offline: an
unknown operation ID is a caller error raised before any transport is created.
"""

from collections.abc import Mapping
from typing import NoReturn

import pytest

import atlawire
from atlawire import (
    AtlaWire,
    AtlaWireError,
    describe_operation,
    list_operations,
    operations,
    read_operation,
)
from atlawire.http import AtlaWireError as HttpAtlaWireError

# Real registry IDs a consumer needs: one Jira issue read, one Jira search, one
# Confluence page read, and one Bitbucket repository read.
CONSUMER_IDS = (
    "jira.issue.issueidorkey",
    "jira.search",
    "confluence.content.id",
    "bitbucket.repository.get",
)
ROOT_NAMES = (
    "AtlaWire",
    "AtlaWireError",
    "describe_operation",
    "list_operations",
    "read_operation",
)
PREVIOUSLY_EXPORTED = (
    "SdkRequestError",
    "__version__",
    "client_for",
    "get_json",
    "request_json",
)
UNKNOWN_ID = "no-such-product.no-such-operation"
BASE = "https://atlassian.example.invalid"
TOKEN = "fixture/api-token"


def test_documented_entry_points_import_from_package_root() -> None:
    """The root names are the real objects, not lookalikes defined at the root."""
    assert isinstance(AtlaWire, type)
    assert AtlaWireError is HttpAtlaWireError
    assert issubclass(AtlaWireError, Exception)
    assert callable(read_operation)
    assert callable(list_operations)
    assert callable(describe_operation)


def test_public_names_are_declared_in_all() -> None:
    """``__all__`` advertises the new surface and keeps every previous export."""
    declared = set(atlawire.__all__)

    assert set(ROOT_NAMES) <= declared
    assert set(PREVIOUSLY_EXPORTED) <= declared
    for name in (*ROOT_NAMES, *PREVIOUSLY_EXPORTED):
        assert hasattr(atlawire, name), name


def test_facade_constructs_without_credentials() -> None:
    """Importing and instantiating the facade touches no credential or network."""
    facade = AtlaWire()

    assert facade.jira is not None
    assert facade.confluence is not None
    assert facade.bitbucket is not None


def test_list_operations_covers_the_consumer_reads() -> None:
    described = list_operations()

    assert isinstance(described, list)
    assert described
    ids = [entry["id"] for entry in described]
    assert all(isinstance(operation_id, str) for operation_id in ids)
    missing = set(CONSUMER_IDS) - set(ids)
    assert not missing, f"registry lost consumer reads: {sorted(missing)}"


def test_describe_operation_returns_mapping_with_operation_id() -> None:
    described = describe_operation("jira.issue.issueidorkey")

    assert isinstance(described, Mapping)
    assert described["id"] == "jira.issue.issueidorkey"


def test_read_operation_unknown_id_raises_typed_error_without_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown ID fails locally: no session, no request, no SDK fallback."""

    def _forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("transport touched for an unknown operation id")

    # Every way ``read_operation`` can reach the network; each must stay unused.
    for name in (
        "bearer_session",
        "get_json_any",
        "get_json_array",
        "get_json_object",
        "get_json_object_allow_no_content",
        "sdk_request_json_with_status",
        "sdk_download_to_file",
    ):
        monkeypatch.setattr(operations, name, _forbidden)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(UNKNOWN_ID, BASE, token=TOKEN, arguments={})

    assert str(raised.value) == "Unknown operation ID."
    assert UNKNOWN_ID not in str(raised.value)

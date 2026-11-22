"""Contract tests for the atlassian-python-api client facade."""

import contextlib

import pytest

from atlawire.http import AtlaWireError
from atlawire.sdk import client_for, get_json

BASE = "https://jira.example.invalid/jira"
TOKEN = "synthetic-sdk-token-4c2"


@pytest.mark.parametrize("product", ["jira", "confluence", "bitbucket"])
def test_client_factory_uses_bounded_settings(product: str) -> None:
    client = client_for(product, BASE, TOKEN)
    try:
        assert client.timeout == 30
        assert client.cloud is False
        # The adapter owns retries, so the SDK must not retry underneath it.
        assert client.backoff_and_retry is False
    finally:
        client.close()


@pytest.mark.parametrize(
    "path",
    [
        "/admin/rest/api/2/myself",
        "/rest/api/2/admin/users",
        "/rest/api/1.0/logs/logger/x",
        "/rest/api/2/../admin",
        "https://evil.invalid/rest/api/2/myself",
        "/rest/api/2/myself?x=1",
        "/rest/api/2/myself#x",
    ],
)
def test_get_json_rejects_unsafe_or_admin_paths_before_a_request(
    path: str,
) -> None:
    with pytest.raises(AtlaWireError):
        get_json("jira", BASE, path, token=TOKEN)


def test_read_only_proxy_exposes_reads_and_blocks_writes() -> None:
    client = client_for("jira", BASE, TOKEN)
    try:
        assert callable(client.get_all_projects)
        assert callable(client.get_project_roles)
        for name in (
            "delete_issue",
            "add_comment",
            "update_issue",
            "create_issue",
            "request",
            "get",
            "post",
        ):
            with pytest.raises(AttributeError):
                getattr(client, name)
    finally:
        client.close()


def test_client_factory_rejects_unknown_product() -> None:
    with pytest.raises(AtlaWireError):
        client_for("other", BASE, TOKEN)


def test_context_manager_closes_the_library_client() -> None:
    client = client_for("jira", BASE, TOKEN)
    with contextlib.closing(client):
        assert client.session is not None
    assert client.session is not None

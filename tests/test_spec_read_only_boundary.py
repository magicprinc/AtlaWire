"""The documented read-only client must not expose mutating library methods."""

import pytest

from atlawire import sdk

TOKEN = "synthetic-read-only-boundary-token"

WRITE_METHODS = (
    "open_pull_request",
    "reopen_pull_request",
    "project_grant_user_permissions",
    "repo_grant_group_permissions",
    "attach_file",
    "attach_content",
    "tempo_timesheets_write_worklog",
    "user_deactivate",
    "trigger_pipeline",
)


@pytest.mark.parametrize(
    ("product", "read_method"),
    [
        ("jira", "get_issue"),
        ("confluence", "get_space"),
        ("bitbucket", "get_pull_request"),
    ],
)
def test_client_for_blocks_known_writes_and_keeps_reads(product, read_method):
    client = sdk.client_for(product, "https://example.invalid", TOKEN)
    try:
        for name in WRITE_METHODS:
            with pytest.raises(AttributeError):
                getattr(client, name)
        for name in ("request", "get", "post", "put", "delete", "patch"):
            with pytest.raises(AttributeError):
                getattr(client, name)
        assert callable(getattr(client, read_method))
    finally:
        client.close()

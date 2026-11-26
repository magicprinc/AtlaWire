"""The read-only client exposes no product verb and keeps the transport policy."""

import pytest

from atlawire import sdk
from atlawire.http import AtlaWireError

TOKEN = "synthetic-read-only-boundary-token"

ABSENT_METHODS = (
    "open_pull_request",
    "reopen_pull_request",
    "project_grant_user_permissions",
    "repo_grant_group_permissions",
    "attach_file",
    "attach_content",
    "tempo_timesheets_write_worklog",
    "user_deactivate",
    "trigger_pipeline",
    "get_issue",
    "get_space",
    "get_pull_request",
    "request",
    "post",
    "put",
    "delete",
    "patch",
)


@pytest.mark.parametrize("product", ["jira", "confluence", "bitbucket"])
def test_client_for_exposes_no_product_method_at_all(product):
    """The client is a base URL plus one session.

    ``atlassian-python-api`` carried 249 product methods, dozens of them
    mutating, and needed a name-filtering proxy to hide them. The replacement
    carries no product methods, so every such attribute is absent by
    construction instead of by filtering.
    """
    client = sdk.client_for(product, "https://example.invalid", TOKEN)
    try:
        for name in ABSENT_METHODS:
            with pytest.raises(AttributeError):
                getattr(client, name)
        assert client.url == "https://example.invalid"
        assert client.product == product
    finally:
        client.close()


@pytest.mark.parametrize("product", ["jira", "confluence", "bitbucket"])
def test_the_transport_session_is_not_reachable_by_its_public_name(product):
    """A caller cannot take the raw session and issue a write.

    The removed ``ReadOnlyClient`` refused ``session``/``_session`` by name.
    Keeping the field private preserves that boundary at no cost, so the only
    method that reaches the network still restricts it to an allowed verb.
    """
    client = sdk.client_for(product, "https://example.invalid", TOKEN)
    try:
        with pytest.raises(AttributeError):
            client.session  # noqa: B018 - the absence of the name is the contract
        assert not hasattr(client, "session")
    finally:
        client.close()


@pytest.mark.parametrize("product", ["jira", "confluence", "bitbucket"])
def test_client_session_keeps_the_transport_policy(product):
    """Bearer auth, no ambient configuration, and no redirect is ever resolved."""
    client = sdk.client_for(product, "https://example.invalid", TOKEN)
    try:
        session = client._session
        assert session.trust_env is False
        assert session.headers["Authorization"] == f"Bearer {TOKEN}"
        assert session.headers["Accept"] == "application/json"
        assert list(session.resolve_redirects()) == []
    finally:
        client.close()


def test_unknown_product_is_refused_before_a_session_exists():
    """A caller-supplied product name never reaches the transport."""
    with pytest.raises(AtlaWireError):
        sdk.client_for("bamboo", "https://example.invalid", TOKEN)


def test_an_invalid_destination_is_refused_before_a_session_exists():
    """Only HTTPS is a destination, so a plain HTTP URL fails immediately."""
    with pytest.raises(AtlaWireError):
        sdk.client_for("jira", "http://example.invalid", TOKEN)


def test_a_malformed_token_is_refused_before_a_session_exists():
    """The bearer grammar is checked once, in the shared transport."""
    with pytest.raises(AtlaWireError):
        sdk.client_for("jira", "https://example.invalid", "not a token\n")


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_a_mutating_verb_never_reaches_the_transport(method):
    """The central promise: no public entry point can send a write.

    The base URL is unusable, so a request would fail with a transport error
    instead of this validation error. Reaching the network at all is therefore
    visible as the wrong exception type.
    """
    with pytest.raises(AtlaWireError) as raised:
        sdk.request_json(
            "jira",
            "https://example.invalid",
            "/rest/api/2/issue/DEMO-1",
            method=method,
            token=TOKEN,
        )
    assert raised.value.category == "validation"


def test_a_post_outside_the_audited_list_never_reaches_the_transport():
    """Only three documented semantic reads may use POST."""
    with pytest.raises(AtlaWireError) as raised:
        sdk.request_json(
            "jira",
            "https://example.invalid",
            "/rest/api/2/issue",
            method="POST",
            token=TOKEN,
            body={"fields": {}},
        )
    assert raised.value.category == "validation"


def test_an_admin_path_is_refused_unless_explicitly_opened():
    """The admin guard runs before the transport on the SDK path too."""
    with pytest.raises(AtlaWireError) as raised:
        sdk.request_json(
            "jira",
            "https://example.invalid",
            "/rest/api/2/audit",
            method="GET",
            token=TOKEN,
        )
    assert raised.value.category == "validation"

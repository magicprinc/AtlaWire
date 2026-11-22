"""Unit checks for the read-only cross-product identity probe."""

import json
from collections.abc import Mapping
from typing import cast

import pytest

from atlawire import identity
from atlawire.federated import ProductTarget
from atlawire.http import AtlaWireError
from atlawire.identity import whoami

CONFLUENCE = ProductTarget(
    "https://confluence.example.test/confluence", "fixture-confluence-token"
)
JIRA = ProductTarget("https://jira.example.test/jira", "fixture-jira-token")
BITBUCKET = ProductTarget(
    "https://bitbucket.example.test/bitbucket", "fixture-bitbucket-token"
)

CONFLUENCE_USER: dict[str, object] = {
    "type": "known",
    "username": "fixture-confluence-user",
    "displayName": "Fixture Confluence User",
    "_links": {"self": "https://elsewhere.example.test/confluence/user"},
}
JIRA_USER: dict[str, object] = {
    "name": "fixture-jira-user",
    "displayName": "Fixture Jira User",
    "emailAddress": "fixture@example.test",
    "self": "https://elsewhere.example.test/jira/user",
}
PRODUCTS = [
    ("confluence", "Confluence"),
    ("jira", "Jira"),
    ("bitbucket", "Bitbucket"),
]
PRODUCT_LABELS = dict(PRODUCTS)
_DEFAULT = object()


class _Session:
    """The closed session stand-in; no request is made by the fake transport."""

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


class Recorder:
    """Capture every adapter call so pairing and routing stay explicit."""

    def __init__(self) -> None:
        self.confluence_tokens: list[str] = []
        self.confluence_requests: list[tuple[str, dict[str, object]]] = []
        self.jira_calls: list[tuple[str, dict[str, object]]] = []
        self.bitbucket_calls: list[tuple[str, dict[str, object]]] = []


def install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    confluence_result: object = _DEFAULT,
    confluence_error: AtlaWireError | None = None,
    jira_result: object = _DEFAULT,
    jira_error: AtlaWireError | None = None,
    bitbucket_result: object = _DEFAULT,
    bitbucket_error: AtlaWireError | None = None,
) -> Recorder:
    """Replace the three probes with recorders and independent fixtures."""
    recorder = Recorder()
    confluence_value = (
        CONFLUENCE_USER if confluence_result is _DEFAULT else confluence_result
    )
    jira_value = JIRA_USER if jira_result is _DEFAULT else jira_result
    bitbucket_value = [] if bitbucket_result is _DEFAULT else bitbucket_result

    def bearer_session(token: str) -> _Session:
        recorder.confluence_tokens.append(token)
        return _Session()

    def get_json(
        session: _Session, url: str, *, params: Mapping[str, str | int]
    ) -> object:
        recorder.confluence_requests.append((url, dict(params)))
        if confluence_error is not None:
            raise confluence_error
        return confluence_value

    def current_user(base_url: str, **kwargs: object) -> object:
        recorder.jira_calls.append((base_url, dict(kwargs)))
        if jira_error is not None:
            raise jira_error
        return jira_value

    def my_pull_requests(base_url: str, **kwargs: object) -> object:
        recorder.bitbucket_calls.append((base_url, dict(kwargs)))
        if bitbucket_error is not None:
            raise bitbucket_error
        return bitbucket_value

    monkeypatch.setattr(identity, "bearer_session", bearer_session)
    monkeypatch.setattr(identity, "get_json_object", get_json)
    monkeypatch.setattr(identity, "get_current_user", current_user)
    monkeypatch.setattr(identity, "list_my_pull_requests", my_pull_requests)
    return recorder


def probe(**kwargs: object) -> dict[str, identity.IdentityCheck]:
    return whoami(
        confluence=cast(
            ProductTarget | None, kwargs.get("confluence", CONFLUENCE)
        ),
        jira=cast(ProductTarget | None, kwargs.get("jira", JIRA)),
        bitbucket=cast(
            ProductTarget | None, kwargs.get("bitbucket", BITBUCKET)
        ),
        allow_http_loopback=cast(bool, kwargs.get("allow_http_loopback", False)),
    )


def assert_product_not_called(recorder: Recorder, slot: str) -> None:
    """Assert the failed product sent no request while the others were probed."""
    if slot == "confluence":
        assert recorder.confluence_tokens == []
        assert recorder.confluence_requests == []
    elif slot == "jira":
        assert recorder.jira_calls == []
    else:
        assert recorder.bitbucket_calls == []


def test_each_pair_probes_only_its_own_fixed_read_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = install(monkeypatch)

    result = probe()

    assert recorder.confluence_tokens == [CONFLUENCE.token]
    assert recorder.confluence_requests == [
        (f"{CONFLUENCE.base_url}/rest/api/user/current", {})
    ]
    assert recorder.jira_calls == [
        (
            JIRA.base_url,
            {"token": JIRA.token, "allow_http_loopback": False},
        )
    ]
    assert recorder.bitbucket_calls == [
        (
            BITBUCKET.base_url,
            {"token": BITBUCKET.token, "limit": 1, "allow_http_loopback": False},
        )
    ]
    assert result == {
        "confluence": {
            "ok": True,
            "identity": {
                "username": "fixture-confluence-user",
                "displayName": "Fixture Confluence User",
            },
        },
        "jira": {
            "ok": True,
            "identity": {
                "name": "fixture-jira-user",
                "displayName": "Fixture Jira User",
            },
        },
        "bitbucket": {"ok": True, "authenticated": True},
    }
    assert list(result) == ["confluence", "jira", "bitbucket"]
    payload = json.dumps(result)
    for secret in (
        CONFLUENCE.token,
        JIRA.token,
        BITBUCKET.token,
        CONFLUENCE.base_url,
        JIRA.base_url,
        BITBUCKET.base_url,
        "fixture@example.test",
        "elsewhere.example.test",
    ):
        assert secret not in payload


@pytest.mark.parametrize(("slot", "label"), PRODUCTS)
@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "authentication rejected"), (403, "access denied")],
    ids=["401", "403"],
)
def test_a_product_failure_is_reported_without_hiding_the_others(
    monkeypatch: pytest.MonkeyPatch,
    slot: str,
    label: str,
    status: int,
    reason: str,
) -> None:
    # A rejected token in one product must neither fail the other probes nor
    # turn that product into a success.
    recorder = install(
        monkeypatch,
        **{f"{slot}_error": AtlaWireError(f"HTTP {status}: fixture detail.")},
    )

    result = probe()

    assert result[slot] == {
        "ok": False,
        "error": f"{label} check failed: {reason}.",
    }
    for other, other_label in PRODUCTS:
        if other != slot:
            assert result[other]["ok"] is True, other_label
    assert len(recorder.confluence_tokens) == 1
    assert len(recorder.jira_calls) == 1
    assert len(recorder.bitbucket_calls) == 1
    assert list(result) == ["confluence", "jira", "bitbucket"]


@pytest.mark.parametrize(
    "value",
    [
        {"type": "anonymous", "username": "anonymous"},
        {"type": "unknown"},
        {"username": "missing-type"},
        {"type": "known"},
        {"type": "known", "username": "   "},
        {"type": "known", "username": 7},
        {"type": "known", "username": "ann", "displayName": 7},
        {"type": "known", "username": "ann\ud800"},
    ],
    ids=[
        "anonymous-type",
        "unknown-type",
        "missing-type",
        "missing-username",
        "blank-username",
        "non-text-username",
        "non-text-display-name",
        "surrogate-username",
    ],
)
def test_confluence_anonymous_or_non_identity_results_are_failures(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    install(monkeypatch, confluence_result=value)

    result = probe()

    assert result["confluence"] == {
        "ok": False,
        "error": (
            "Confluence check failed: no authenticated identity was returned."
        ),
    }
    assert result["jira"]["ok"] is True
    assert result["bitbucket"]["ok"] is True


@pytest.mark.parametrize(
    "value",
    [
        {"displayName": "No name"},
        {"name": ""},
        {"name": "   "},
        {"name": 7},
        {"name": "ann\ud800"},
        {"name": "ann", "displayName": 7},
        None,
    ],
    ids=[
        "missing-name",
        "empty-name",
        "blank-name",
        "non-text-name",
        "surrogate-name",
        "non-text-display-name",
        "not-an-object",
    ],
)
def test_malformed_jira_identity_is_reported_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    install(monkeypatch, jira_result=value)

    result = probe()

    assert result["jira"] == {
        "ok": False,
        "error": "Jira check failed: no authenticated identity was returned.",
    }
    assert result["confluence"]["ok"] is True
    assert result["bitbucket"]["ok"] is True


def test_empty_authenticated_bitbucket_dashboard_is_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = install(monkeypatch, bitbucket_result=[])

    result = probe()

    assert result["bitbucket"] == {"ok": True, "authenticated": True}
    assert "identity" not in result["bitbucket"]
    assert recorder.bitbucket_calls[0][1]["limit"] == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ("HTTP 500: request failed.", "request failed"),
        ("HTTP 302: redirect refused; check the base URL.", "redirect refused"),
        (
            "HTTP 206: partial content is not supported.",
            "partial response refused",
        ),
        ("Request timed out.", "request timed out"),
        (
            "Request failed; check connectivity and TLS settings.",
            "connection failed",
        ),
        ("Expected a valid JSON response.", "unexpected response"),
    ],
    ids=[
        "server-error",
        "redirect",
        "partial",
        "timeout",
        "connection",
        "malformed-json",
    ],
)
def test_adapter_failures_map_to_one_closed_generic_reason(
    monkeypatch: pytest.MonkeyPatch, failure: str, reason: str
) -> None:
    install(monkeypatch, jira_error=AtlaWireError(failure))

    result = probe()

    assert result["jira"] == {"ok": False, "error": f"Jira check failed: {reason}."}


def test_failures_never_echo_secrets_destinations_or_response_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leak = (
        "HTTP 500: response-sentinel "
        "fixture-confluence-token https://confluence.example.test/private"
    )
    install(
        monkeypatch,
        confluence_error=AtlaWireError(leak),
        jira_error=AtlaWireError(leak),
        bitbucket_error=AtlaWireError(leak),
    )

    result = probe()
    payload = json.dumps(result)

    for slot, label in PRODUCTS:
        assert result[slot]["error"] == f"{label} check failed: request failed."
    for detail in (
        "response-sentinel",
        CONFLUENCE.token,
        JIRA.token,
        BITBUCKET.token,
        CONFLUENCE.base_url,
        JIRA.base_url,
        BITBUCKET.base_url,
        "private",
    ):
        assert detail not in payload


@pytest.mark.parametrize(("slot", "label"), PRODUCTS)
def test_missing_product_pair_reports_failure_and_probes_the_other_two(
    monkeypatch: pytest.MonkeyPatch, slot: str, label: str
) -> None:
    # A caller that could not resolve one saved pair passes None for exactly
    # that product; the other two must still be checked.
    recorder = install(monkeypatch)

    result = probe(**{slot: None})

    assert result[slot] == {
        "ok": False,
        "error": f"{label} check failed: configuration is missing or invalid.",
    }
    for other, _ in PRODUCTS:
        if other != slot:
            assert result[other]["ok"] is True, other
    assert_product_not_called(recorder, slot)
    assert (
        len(recorder.confluence_tokens)
        + len(recorder.jira_calls)
        + len(recorder.bitbucket_calls)
        == 2
    )


@pytest.mark.parametrize("slot", ["confluence", "jira", "bitbucket"])
@pytest.mark.parametrize(
    "target",
    [
        cast(ProductTarget, None),
        cast(ProductTarget, "https://confluence.example.test"),
        ProductTarget("", "fixture-token"),
        ProductTarget("http://confluence.example.test", "fixture-token"),
        ProductTarget("https://confluence.example.test", ""),
        ProductTarget("https://confluence.example.test", "bad token"),
        ProductTarget("https://confluence.example.test?cql=x", "fixture-token"),
        ProductTarget("https://user@confluence.example.test", "fixture-token"),
    ],
    ids=[
        "missing-pair",
        "wrong-type",
        "empty-url",
        "plain-http",
        "empty-token",
        "token-with-space",
        "url-with-query",
        "url-with-userinfo",
    ],
)
def test_invalid_target_fails_only_its_product_without_a_request(
    monkeypatch: pytest.MonkeyPatch, slot: str, target: ProductTarget
) -> None:
    recorder = install(monkeypatch)

    result = probe(**{slot: target})

    label = PRODUCT_LABELS[slot]
    assert result[slot] == {
        "ok": False,
        "error": f"{label} check failed: configuration is missing or invalid.",
    }
    for other, _ in PRODUCTS:
        if other != slot:
            assert result[other]["ok"] is True, other
    assert_product_not_called(recorder, slot)
    assert (
        len(recorder.confluence_tokens)
        + len(recorder.jira_calls)
        + len(recorder.bitbucket_calls)
        == 2
    )
    payload = json.dumps(result)
    for detail in (
        CONFLUENCE.token,
        JIRA.token,
        BITBUCKET.token,
        CONFLUENCE.base_url,
        JIRA.base_url,
        BITBUCKET.base_url,
    ):
        assert detail not in payload


def test_http_loopback_is_allowed_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = install(monkeypatch)
    loopback = ProductTarget("http://127.0.0.1:9/context", "fixture-token")

    result = probe(confluence=loopback, jira=loopback, bitbucket=loopback)

    for slot, label in PRODUCTS:
        assert result[slot] == {
            "ok": False,
            "error": (
                f"{label} check failed: configuration is missing or invalid."
            ),
        }
    assert recorder.confluence_tokens == []
    assert recorder.jira_calls == []
    assert recorder.bitbucket_calls == []

    result = probe(
        confluence=loopback,
        jira=loopback,
        bitbucket=loopback,
        allow_http_loopback=True,
    )

    assert all(entry["ok"] is True for entry in result.values())
    assert recorder.confluence_requests == [
        ("http://127.0.0.1:9/context/rest/api/user/current", {})
    ]
    assert recorder.jira_calls[0][1]["allow_http_loopback"] is True
    assert recorder.bitbucket_calls[0][1]["allow_http_loopback"] is True
    assert json.dumps(result).count("127.0.0.1") == 0

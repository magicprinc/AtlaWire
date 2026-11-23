"""Unit checks for the Jira caller identity projection.

Every request is replaced at the adapter boundary and the credential is a
synthetic fixture; no test reads process settings or contacts a real server.
The projection tests replace the JSON helper, while the transport tests keep the
shared helper and substitute only the session, so the exercised status and
decoding policy is the production one.
"""

import json
from collections.abc import Iterator, Mapping
from contextlib import nullcontext
from typing import Self

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError
from atlawire.http import bearer_session as real_bearer_session

BASE = "https://jira.example.invalid/jira"
MYSELF_PATH = f"{BASE}/rest/api/2/myself"
TOKEN = "fixture-jira-me-unit-token"
SENTINEL = "JIRA-ME-UNIT-SENTINEL"

IDENTITY: dict[str, object] = {
    "self": f"https://jira.example.invalid{MYSELF_PATH}?username={SENTINEL}",
    "key": SENTINEL,
    "name": "ada",
    "displayName": "Ada Lovelace",
    "emailAddress": "ada@example.invalid",
    "active": True,
    "avatarUrls": {"48x48": f"https://example.invalid/{SENTINEL}.png"},
    "groups": {"size": 1, "items": [{"name": SENTINEL}]},
    "properties": {"inert": {"opaque": True}},
}

EXPECTED: dict[str, str | None] = {
    "name": "ada",
    "displayName": "Ada Lovelace",
    "email": "ada@example.invalid",
}


def patch_identity_transport(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> tuple[list[tuple[str, dict[str, object]]], list[str], list[object]]:
    """Replace both adapter seams and record the token, URL, params, and session.

    ``bearer_session`` is wrapped around the real factory, so the Authorization
    header inspected by the caller is the one production code builds.
    """
    seen: list[tuple[str, dict[str, object]]] = []
    tokens: list[str] = []
    sessions: list[object] = []

    def spy_bearer_session(token: str) -> object:
        tokens.append(token)
        session = real_bearer_session(token)
        sessions.append(session)
        return session

    def fake_get_json_object(
        session: object, url: str, *, params: Mapping[str, object]
    ) -> object:
        seen.append((url, dict(params)))
        return value

    monkeypatch.setattr(jira, "bearer_session", spy_bearer_session)
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    return seen, tokens, sessions


def has_bearer_authorization(session: object, token: str) -> bool:
    """Report whether the header carries this token as a bearer credential.

    The comparison returns a bool so a failed assertion never prints the value.
    """
    headers = getattr(session, "headers", None)
    if not isinstance(headers, Mapping):
        return False
    value = headers.get("Authorization")
    if not isinstance(value, str):
        return False
    scheme, separator, credential = value.partition(" ")
    return separator == " " and scheme.lower() == "bearer" and credential == token


class _FakeResponse:
    """One streamed response substitute carrying a status and a body."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield self._body


class _RecordingSession:
    """A session substitute that records each GET instead of opening a socket."""

    def __init__(self, status: int, body: bytes = b"") -> None:
        self._status = status
        self._body = body
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def get(self, url: str, **options: object) -> _FakeResponse:
        params = options.get("params")
        recorded: dict[str, object] = dict(params) if isinstance(params, dict) else {}
        self.requests.append(("GET", url, recorded))
        return _FakeResponse(self._status, self._body)


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_identity_read_calls_the_fixed_myself_route_without_query_parameters(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    # Wrong impl: queries /user/search, adds expand= or username=, or loses the
    # configured base context path when joining the fixed route.
    seen, tokens, _ = patch_identity_transport(monkeypatch, IDENTITY)

    result = jira.get_current_user(base, token=TOKEN)

    assert result == EXPECTED
    assert seen == [(MYSELF_PATH, {})]
    assert tokens == [TOKEN]


def test_identity_read_sends_the_bearer_credential_in_the_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wrong impl: builds a bare requests.Session, sends Basic auth, or moves the
    # credential from the Authorization header into a query parameter.
    seen, tokens, sessions = patch_identity_transport(monkeypatch, IDENTITY)

    jira.get_current_user(BASE, token=TOKEN)

    assert seen == [(MYSELF_PATH, {})]
    assert tokens == [TOKEN]
    assert has_bearer_authorization(sessions[0], TOKEN), (
        "Expected a bearer-scheme Authorization header carrying the session token."
    )


def test_identity_read_issues_one_get_and_returns_the_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wrong impl: POSTs the read, follows a redirect, or returns the raw server
    # document instead of the three documented fields.
    session = _RecordingSession(200, json.dumps(IDENTITY).encode("utf-8"))
    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(session))

    result = jira.get_current_user(BASE, token=TOKEN)

    assert result == EXPECTED
    assert list(result) == ["name", "displayName", "email"]
    assert session.requests == [("GET", MYSELF_PATH, {})]


def test_the_email_key_is_mapped_from_email_address_and_nothing_else_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wrong impl: exposes the server's emailAddress key verbatim, copies an
    # unrelated email field, or keeps account ID, links, or permission claims.
    server = {**IDENTITY, "email": "decoy@example.invalid"}
    patch_identity_transport(monkeypatch, server)

    result = jira.get_current_user(BASE, token=TOKEN)

    assert result == EXPECTED
    assert list(result) == ["name", "displayName", "email"]
    assert result["email"] == server["emailAddress"]
    assert "emailAddress" not in result
    assert "key" not in result
    assert "self" not in result


@pytest.mark.parametrize(
    "value",
    [
        {"name": "ada"},
        {"name": "ada", "displayName": None, "emailAddress": None},
    ],
    ids=["absent", "null"],
)
def test_absent_or_null_optional_identity_fields_stay_null(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object]
) -> None:
    # Wrong impl: substitutes "" or the text "None" for a missing optional
    # field, or drops the field so the documented key disappears.
    patch_identity_transport(monkeypatch, value)

    result = jira.get_current_user(BASE, token=TOKEN)

    assert result == {"name": "ada", "displayName": None, "email": None}
    assert list(result) == ["name", "displayName", "email"]


@pytest.mark.parametrize(
    ("status", "diagnostic"),
    [
        (302, "redirect refused"),
        (401, "authentication rejected"),
        (403, "access denied"),
        (404, "request failed"),
        (500, "request failed"),
    ],
    ids=["302", "401", "403", "404", "500"],
)
def test_a_non_2xx_response_raises_the_plain_error_with_the_real_status(
    monkeypatch: pytest.MonkeyPatch, status: int, diagnostic: str
) -> None:
    # Wrong impl: returns a partial identity, retries a rejected credential,
    # follows a redirect, or masks the real status with a generic diagnostic.
    session = _RecordingSession(status)
    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(session))

    with pytest.raises(AtlaWireError) as caught:
        jira.get_current_user(BASE, token=TOKEN)

    error = caught.value
    # The shared transport attaches the structured classification and the real
    # arrived status; it is never inferred from the message.
    assert type(error) is AtlaWireError
    assert error.category == "http"
    assert error.http_status == status
    assert f"HTTP {status}" in str(error)
    assert diagnostic in str(error)
    assert session.requests == [("GET", MYSELF_PATH, {})]


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        (b'{"name": ', "valid JSON"),
        (b"", "valid JSON"),
        (b'["ada"]', "JSON object"),
    ],
    ids=["truncated", "empty", "array"],
)
def test_a_malformed_json_body_raises_instead_of_returning_a_partial_identity(
    monkeypatch: pytest.MonkeyPatch, body: bytes, diagnostic: str
) -> None:
    # Wrong impl: swallows a decode or shape failure and returns an empty or
    # partial identity instead of a typed error.
    session = _RecordingSession(200, body)
    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(session))

    with pytest.raises(AtlaWireError, match=diagnostic):
        jira.get_current_user(BASE, token=TOKEN)

    assert session.requests == [("GET", MYSELF_PATH, {})]


@pytest.mark.parametrize(
    ("value", "diagnostic"),
    [
        ({}, "Invalid Jira user name"),
        ({"name": 7}, "Invalid Jira user name"),
        ({"name": True}, "Invalid Jira user name"),
        ({"name": ["ada"]}, "Invalid Jira user name"),
        ({"name": "ada", "displayName": 5}, "Invalid Jira user display name"),
        (
            {"name": "ada", "displayName": None, "emailAddress": 5},
            "Invalid Jira user email",
        ),
        (
            {"name": "ada", "emailAddress": ["ada@example.invalid"]},
            "Invalid Jira user email",
        ),
        ({"name": "ada\ud800"}, "valid UTF-8"),
        ({"name": "ada", "displayName": "Ada\ud800"}, "valid UTF-8"),
        ({"name": "ada", "emailAddress": "ada\ud800@example.invalid"}, "valid UTF-8"),
    ],
    ids=[
        "missing-name",
        "integer-name",
        "boolean-name",
        "array-name",
        "integer-display-name",
        "integer-email",
        "array-email",
        "unencodable-name",
        "unencodable-display-name",
        "unencodable-email",
    ],
)
def test_a_malformed_identity_is_rejected_without_a_partial_result(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object], diagnostic: str
) -> None:
    # Wrong impl: coerces wrong-typed fields with str() or defaults missing
    # fields to "" and publishes a partial identity.
    seen, _, _ = patch_identity_transport(monkeypatch, value)

    with pytest.raises(AtlaWireError, match=diagnostic):
        jira.get_current_user(BASE, token=TOKEN)

    assert seen == [(MYSELF_PATH, {})]


def test_a_blank_name_is_reported_as_validation_not_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Wrong impl: classifies a caller-shaped output problem as a transport
    # failure, or returns the blank name as a valid identity.
    seen, _, _ = patch_identity_transport(
        monkeypatch, {"name": "   ", "displayName": "Ada Lovelace"}
    )

    with pytest.raises(AtlaWireError) as caught:
        jira.get_current_user(BASE, token=TOKEN)

    error = caught.value
    assert type(error) is AtlaWireError
    assert "non-empty name" in str(error)
    # Validation of the projected identity is not a transport failure: the
    # transport classification and the arrived status stay unset.
    assert error.category is None or error.category == "validation"
    assert error.http_status is None
    assert "HTTP" not in str(error)
    assert "Request failed" not in str(error)
    assert seen == [(MYSELF_PATH, {})]

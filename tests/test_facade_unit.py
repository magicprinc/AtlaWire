"""Unit contracts for the public AtlaWire facade."""

import json

import pytest

import atlawire.facade as facade
from atlawire.credentials import SavedCredentials
from atlawire.facade import AtlaWire
from atlawire.http import AtlaWireError
from atlawire.sdk import SdkRequestError

TOKEN = "synthetic-facade-unit-token-5e9"
SENTINEL = "FACADE-UNIT-SENTINEL"
BASE = {
    "bitbucket": "https://bitbucket.example.invalid/bitbucket",
    "confluence": "https://wiki.example.invalid/confluence",
    "jira": "https://jira.example.invalid/jira",
}
DATA = {
    "bitbucket": {"values": [{"slug": "my-repo"}], "isLastPage": True},
    "confluence": {"id": "4242", "title": "Page"},
    "jira": {"key": "ABC-123", "fields": {"summary": "Summary"}},
}


class Resolver:
    """Synthetic saved-credential source that records every product lookup."""

    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing
        self.calls: list[tuple[str, str | None, bool]] = []

    def __call__(
        self,
        product: str,
        *,
        supplied_base_url: str | None,
        allow_http_loopback: bool,
    ) -> SavedCredentials:
        self.calls.append((product, supplied_base_url, allow_http_loopback))
        if product in self.failing:
            raise AtlaWireError(f"Saved BBK credentials are unavailable for {product}.")
        return SavedCredentials(base_url=BASE[product], token=TOKEN)


class Transport:
    """Stand-in for ``get_json`` that records the exact request or fails."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        product: str,
        base_url: str,
        path: str,
        *,
        token: str,
        params: dict[str, str | int] | None = None,
        allow_http_loopback: bool = False,
    ) -> object:
        self.calls.append(
            {
                "product": product,
                "base_url": base_url,
                "path": path,
                "token": token,
                "params": params,
                "allow_http_loopback": allow_http_loopback,
            }
        )
        if self.error is not None:
            raise self.error
        return DATA[product]


def install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> tuple[Resolver, Transport]:
    resolver = resolver or Resolver()
    transport = transport or Transport()
    monkeypatch.setattr(facade, "resolve_saved_credentials", resolver)
    monkeypatch.setattr(facade, "get_json", transport)
    return resolver, transport


def forbidden(*args: object, **kwargs: object) -> object:
    raise AssertionError("no upstream work is expected")


CASES = [
    (
        "jira",
        "get_issue",
        ("ABC-123",),
        {},
        "/rest/api/2/issue/ABC-123",
        None,
    ),
    (
        "jira",
        "search",
        ('project = ABC AND text ~ "x y"',),
        {"limit": 7},
        "/rest/api/2/search",
        {"jql": 'project = ABC AND text ~ "x y"', "maxResults": 7},
    ),
    ("jira", "list_projects", (), {}, "/rest/api/2/project", None),
    (
        "confluence",
        "get_page",
        (4242,),
        {},
        "/rest/api/content/4242",
        None,
    ),
    (
        "confluence",
        "search",
        ("type=page",),
        {"limit": 5},
        "/rest/api/content/search",
        {"cql": "type=page", "limit": 5},
    ),
    (
        "confluence",
        "list_spaces",
        (),
        {},
        "/rest/api/space",
        {"limit": 25},
    ),
    (
        "bitbucket",
        "get_repository",
        ("PROJ", "my-repo"),
        {},
        "/rest/api/1.0/projects/PROJ/repos/my-repo",
        None,
    ),
    (
        "bitbucket",
        "list_projects",
        (),
        {},
        "/rest/api/1.0/projects",
        {"limit": 25},
    ),
    (
        "bitbucket",
        "get_pull_request",
        ("PROJ", "my-repo", 7),
        {},
        "/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/7",
        None,
    ),
]


@pytest.mark.parametrize(
    ("product", "method", "args", "kwargs", "path", "params"),
    CASES,
)
def test_namespace_calls_send_one_fixed_request_and_the_raw_data(
    monkeypatch: pytest.MonkeyPatch,
    product: str,
    method: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    path: str,
    params: dict[str, str | int] | None,
) -> None:
    resolver, transport = install(monkeypatch)
    wire = AtlaWire()

    envelope = getattr(getattr(wire, product), method)(*args, **kwargs)

    assert envelope == {"ok": True, "product": product, "data": DATA[product]}
    assert envelope["data"] is DATA[product]
    assert resolver.calls == [(product, None, False)]
    assert transport.calls == [
        {
            "product": product,
            "base_url": BASE[product],
            "path": path,
            "token": TOKEN,
            "params": params,
            "allow_http_loopback": False,
        }
    ]


DISPATCH_CASES = [
    ("jira.get_issue", {"key": "ABC-123"}, "jira", "/rest/api/2/issue/ABC-123", None),
    (
        "jira.search",
        {"jql": 'project = ABC AND text ~ "x y"', "limit": 7},
        "jira",
        "/rest/api/2/search",
        {"jql": 'project = ABC AND text ~ "x y"', "maxResults": 7},
    ),
    ("jira.list_projects", {}, "jira", "/rest/api/2/project", None),
    (
        "confluence.get_page",
        {"content_id": 4242},
        "confluence",
        "/rest/api/content/4242",
        None,
    ),
    (
        "confluence.search",
        {"cql": "type=page"},
        "confluence",
        "/rest/api/content/search",
        {"cql": "type=page", "limit": 25},
    ),
    (
        "confluence.list_spaces",
        {},
        "confluence",
        "/rest/api/space",
        {"limit": 25},
    ),
    (
        "bitbucket.get_repository",
        {"project": "PROJ", "slug": "my-repo"},
        "bitbucket",
        "/rest/api/1.0/projects/PROJ/repos/my-repo",
        None,
    ),
    (
        "bitbucket.list_projects",
        {},
        "bitbucket",
        "/rest/api/1.0/projects",
        {"limit": 25},
    ),
    (
        "bitbucket.get_pull_request",
        {"project": "PROJ", "slug": "my-repo", "pr_id": 7},
        "bitbucket",
        "/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/7",
        None,
    ),
]


@pytest.mark.parametrize(
    ("operation", "params_in", "product", "path", "params"),
    DISPATCH_CASES,
)
def test_named_call_dispatches_the_same_operations_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    params_in: dict[str, object],
    product: str,
    path: str,
    params: dict[str, str | int] | None,
) -> None:
    resolver, transport = install(monkeypatch)
    wire = AtlaWire()

    envelope = wire.call(operation, **params_in)

    assert envelope == {"ok": True, "product": product, "data": DATA[product]}
    assert resolver.calls == [(product, None, False)]
    assert transport.calls[0]["path"] == path
    assert transport.calls[0]["params"] == params


@pytest.mark.parametrize(
    ("operation", "params_in", "product"),
    [
        ("get_issue", {"key": "ABC-123"}, "jira"),
        ("get_page", {"content_id": 4242}, "confluence"),
        ("list_spaces", {}, "confluence"),
        ("get_repository", {"project": "PROJ", "slug": "my-repo"}, "bitbucket"),
        (
            "get_pull_request",
            {"project": "PROJ", "slug": "my-repo", "pr_id": 7},
            "bitbucket",
        ),
    ],
)
def test_a_unique_bare_method_name_is_dispatched(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    params_in: dict[str, object],
    product: str,
) -> None:
    _, transport = install(monkeypatch)

    envelope = AtlaWire().call(operation, **params_in)

    assert envelope == {"ok": True, "product": product, "data": DATA[product]}
    assert len(transport.calls) == 1


def test_ambiguous_bare_method_names_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, transport = install(monkeypatch)

    envelopes = [
        AtlaWire().call("search", jql="project = ABC"),
        AtlaWire().call("search", cql="type=page"),
        AtlaWire().call("list_projects"),
    ]

    for envelope in envelopes:
        assert envelope["ok"] is False
        assert envelope["product"] is None
        assert envelope["error"]["code"] == "validation_error"
    assert resolver.calls == []
    assert transport.calls == []


def test_success_envelope_has_no_other_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch)

    envelope = AtlaWire().jira.get_issue("ABC-123")

    assert set(envelope) == {"ok", "product", "data"}


def test_namespaces_are_lazy_and_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver, transport = install(monkeypatch)

    wire = AtlaWire()
    assert resolver.calls == []
    assert wire.jira is wire.jira
    assert wire.confluence is not wire.jira
    assert resolver.calls == []
    assert transport.calls == []


def test_one_product_call_resolves_only_that_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, _ = install(monkeypatch)

    AtlaWire().bitbucket.list_projects()

    assert resolver.calls == [("bitbucket", None, False)]


def test_a_missing_product_entry_fails_only_that_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, transport = install(
        monkeypatch, resolver=Resolver(failing=frozenset({"jira"}))
    )
    wire = AtlaWire()

    failed = wire.jira.list_projects()
    succeeded = wire.confluence.list_spaces()

    assert failed["ok"] is False
    assert failed["product"] == "jira"
    assert failed["error"] == {
        "status": None,
        "code": "credentials_error",
        "message": "Saved BBK credentials are unavailable for jira.",
        "path": None,
        "body": None,
        "body_json": None,
        "body_truncated": False,
    }
    assert succeeded == {
        "ok": True,
        "product": "confluence",
        "data": DATA["confluence"],
    }
    assert resolver.calls == [
        ("jira", None, False),
        ("confluence", None, False),
    ]
    assert [call["product"] for call in transport.calls] == ["confluence"]


def test_unresolvable_saved_credentials_fail_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, transport = install(monkeypatch, resolver=Resolver(failing=frozenset({"jira"})))

    envelope = AtlaWire().jira.get_issue("ABC-123")

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "credentials_error"
    assert envelope["error"]["status"] is None
    assert TOKEN not in json.dumps(envelope)
    assert transport.calls == []


@pytest.mark.parametrize(
    ("operation", "product"),
    [
        ("jira.delete_issue", "jira"),
        ("bitbucket.create_repository", "bitbucket"),
        ("confluence.update_page", "confluence"),
        ("delete_issue", None),
        ("jira", None),
        ("", None),
        (42, None),
        (None, None),
    ],
)
def test_unknown_or_unqualified_operations_are_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    operation: object,
    product: str | None,
) -> None:
    resolver, transport = install(monkeypatch)

    envelope = AtlaWire().call(operation)  # type: ignore[arg-type]

    assert envelope == {
        "ok": False,
        "product": product,
        "error": {
            "status": None,
            "code": "validation_error",
            "message": "Unknown operation.",
            "path": None,
            "body": None,
            "body_json": None,
            "body_truncated": False,
        },
    }
    assert resolver.calls == []
    assert transport.calls == []


def test_extra_request_shaping_parameters_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, transport = install(monkeypatch)

    envelopes = [
        AtlaWire().call("jira.get_issue", key="ABC-123", path="/rest/api/2/admin"),
        AtlaWire().call("jira.get_issue", key="ABC-123", method="POST"),
        AtlaWire().call("jira.list_projects", limit=1),
        AtlaWire().call(
            "jira.get_issue", key="ABC-123", base_url="https://evil.invalid"
        ),
    ]

    for envelope in envelopes:
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "validation_error"
        assert envelope["error"]["status"] is None
    assert resolver.calls == []
    assert transport.calls == []


def test_missing_required_parameters_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, transport = install(monkeypatch)

    envelopes = [
        AtlaWire().call("jira.get_issue"),
        AtlaWire().call("confluence.get_page"),
        AtlaWire().call("bitbucket.get_repository", project="PROJ"),
        AtlaWire().call(
            "bitbucket.get_pull_request", project="PROJ", slug="my-repo"
        ),
    ]

    for envelope in envelopes:
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "validation_error"
    assert resolver.calls == []
    assert transport.calls == []


@pytest.mark.parametrize(
    ("operation", "params"),
    [
        ("jira.get_issue", {"key": "abc-123"}),
        ("jira.get_issue", {"key": "ABC"}),
        ("jira.get_issue", {"key": "ABC-1/../../admin"}),
        ("jira.get_issue", {"key": "ABC-1?x=1"}),
        ("jira.get_issue", {"key": "ABC-1#fragment"}),
        ("jira.get_issue", {"key": "ABC-1\nX"}),
        ("jira.get_issue", {"key": "ABC-1 "}),
        ("confluence.get_page", {"content_id": "12/34"}),
        ("confluence.get_page", {"content_id": ".."}),
        ("confluence.get_page", {"content_id": "12?x=1"}),
        ("confluence.get_page", {"content_id": "１２"}),
        ("confluence.get_page", {"content_id": 0}),
        ("bitbucket.get_repository", {"project": "P/../X", "slug": "my-repo"}),
        ("bitbucket.get_repository", {"project": "../X", "slug": "my-repo"}),
        ("bitbucket.get_repository", {"project": "PROJ", "slug": "../../etc"}),
        ("bitbucket.get_repository", {"project": "PROJ", "slug": ".."}),
        ("bitbucket.get_repository", {"project": "PROJ", "slug": "my%2Frepo"}),
        (
            "bitbucket.get_pull_request",
            {"project": "PROJ", "slug": "my-repo", "pr_id": "-1"},
        ),
        (
            "bitbucket.get_pull_request",
            {"project": "PROJ", "slug": "my-repo", "pr_id": "1/2"},
        ),
        (
            "bitbucket.get_pull_request",
            {"project": "PROJ", "slug": "my-repo", "pr_id": "1?x=1"},
        ),
    ],
)
def test_unsafe_identifiers_are_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    params: dict[str, object],
) -> None:
    resolver, transport = install(monkeypatch)

    envelope = AtlaWire().call(operation, **params)

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert envelope["error"]["status"] is None
    assert resolver.calls == []
    assert transport.calls == []
    assert ".." not in json.dumps(envelope["error"]["message"])


@pytest.mark.parametrize(
    ("operation", "params"),
    [
        ("jira.search", {"jql": ""}),
        ("jira.search", {"jql": "   "}),
        ("jira.search", {"jql": "project = ABC\nX"}),
        ("jira.search", {"jql": "project = ABC", "limit": 0}),
        ("jira.search", {"jql": "project = ABC", "limit": 1001}),
        ("jira.search", {"jql": "project = ABC", "limit": True}),
        ("jira.search", {"jql": "project = ABC", "limit": "50"}),
        ("jira.search", {"jql": "project = ABC", "limit": 1.5}),
        ("confluence.search", {"cql": ""}),
        ("confluence.search", {"cql": "type=page", "limit": 0}),
        ("confluence.list_spaces", {"limit": -1}),
        ("bitbucket.list_projects", {"limit": 1001}),
        ("jira.search", {"jql": "x" * 8193}),
    ],
)
def test_invalid_queries_and_limits_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    params: dict[str, object],
) -> None:
    resolver, transport = install(monkeypatch)

    envelope = AtlaWire().call(operation, **params)

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert resolver.calls == []
    assert transport.calls == []


def test_upstream_http_failure_preserves_status_body_and_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = SdkRequestError(
        status=401,
        code="http_401",
        classification="authentication",
        message=f"401 Client Error: echo {TOKEN}",
        body=json.dumps({"message": SENTINEL, "echo": TOKEN}),
        content_type="application/json",
        path="/rest/api/2/issue/ABC-123",
    )
    install(monkeypatch, transport=Transport(error=error))

    envelope = AtlaWire().jira.get_issue("ABC-123")

    assert envelope == {
        "ok": False,
        "product": "jira",
        "error": {
            "status": 401,
            "code": "http_401",
            "message": "401 Client Error: echo [REDACTED]",
            "path": "/rest/api/2/issue/ABC-123",
            "body": '{"message": "FACADE-UNIT-SENTINEL", "echo": "[REDACTED]"}',
            "body_json": {"message": SENTINEL, "echo": "[REDACTED]"},
            "body_truncated": False,
        },
    }
    rendered = json.dumps(envelope)
    assert TOKEN not in rendered
    assert "Authorization" not in rendered


def test_upstream_json_escape_of_the_token_is_still_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    escaped = "\\u0073" + TOKEN[1:]
    assert json.loads(f'"{escaped}"') == TOKEN
    error = SdkRequestError(
        status=400,
        code="http_400",
        classification="client_error",
        message="400 Client Error",
        body=f'{{"echo": "{escaped}", "nested": [{{"echo": "{escaped}"}}]}}',
        content_type="application/json",
        path="/rest/api/2/project",
    )
    install(monkeypatch, transport=Transport(error=error))

    envelope = AtlaWire().jira.list_projects()

    assert TOKEN not in json.dumps(envelope, ensure_ascii=False)
    assert envelope["error"]["body_json"] == {
        "echo": "[REDACTED]",
        "nested": [{"echo": "[REDACTED]"}],
    }


def test_upstream_body_is_truncated_after_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = f'{{"message": "{TOKEN}"}}' + "A" * 9000
    error = SdkRequestError(
        status=500,
        code="http_500",
        classification="server_error",
        message="500 Server Error",
        body=body,
        content_type="application/json",
        path="/rest/api/2/project",
    )
    install(monkeypatch, transport=Transport(error=error))

    envelope = AtlaWire().jira.list_projects()

    reported = envelope["error"]
    assert reported["body_truncated"] is True
    assert len(reported["body"]) == 8192
    assert reported["body"] == body.replace(TOKEN, "[REDACTED]")[:8192]
    assert TOKEN not in json.dumps(envelope)


def test_transport_failure_has_no_status_and_no_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = SdkRequestError(
        status=None,
        code="timeout",
        classification="timeout",
        message="Request timed out.",
        body=None,
        content_type=None,
        path="/rest/api/1.0/projects",
    )
    install(monkeypatch, transport=Transport(error=error))

    envelope = AtlaWire().bitbucket.list_projects()

    assert envelope["ok"] is False
    assert envelope["error"] == {
        "status": None,
        "code": "timeout",
        "message": "Request timed out.",
        "path": "/rest/api/1.0/projects",
        "body": None,
        "body_json": None,
        "body_truncated": False,
    }


def test_loopback_flag_is_propagated_to_credentials_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver, transport = install(monkeypatch)

    AtlaWire(allow_http_loopback=True).jira.get_issue("ABC-123")

    assert resolver.calls == [("jira", None, True)]
    assert transport.calls[0]["allow_http_loopback"] is True


def test_facade_does_not_expose_clients_or_transport_primitives() -> None:
    wire = AtlaWire()

    for name in ("client", "session", "get", "request", "api_request"):
        assert not hasattr(wire, name)
    for name in ("client", "session", "get", "post", "request"):
        assert not hasattr(wire.jira, name)
        assert not hasattr(wire.confluence, name)
        assert not hasattr(wire.bitbucket, name)

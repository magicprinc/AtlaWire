"""Unit checks for the Jira issue metadata readers.

Every request is replaced at the adapter boundary and every credential is a
synthetic fixture; no test reads process settings or contacts a real server.
The expected documents are independent fixtures, not values produced by the
module under test.
"""

from collections.abc import Callable
from contextlib import nullcontext
from copy import deepcopy
from typing import cast

import pytest

from atlawire import jira_metadata
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
LOOPBACK = "http://127.0.0.1:8080/jira"
TOKEN = "fixture-jira-metadata-token"
KEY = "DEMO-42"
SENTINEL = "JIRA-METADATA-SENTINEL"

EDIT_META_PATH = f"{BASE}/rest/api/2/issue/{KEY}/editmeta"
CREATE_META_PATH = f"{BASE}/rest/api/2/issue/createmeta"
TRANSITIONS_PATH = f"{BASE}/rest/api/2/issue/{KEY}/transitions"

SUMMARY_FIELD: dict[str, object] = {
    "required": True,
    "schema": {"type": "string", "system": "summary"},
    "name": "Summary ✓",
    "fieldId": "summary",
    "autoCompleteUrl": "https://pasted.example.invalid/rest/api/2/issue/picker",
    "hasDefaultValue": False,
    "operations": ["set"],
    "allowedValues": [],
    "defaultValue": None,
    "pluginField": {"nested": [None, {"deep": "false"}]},
}

EDIT_META: dict[str, object] = {
    "fields": {
        "summary": SUMMARY_FIELD,
        "customfield_10000": {
            "required": False,
            "schema": {
                "type": "array",
                "items": "option",
                "custom": "com.example:multiselect",
                "customId": 10000,
            },
            "name": "My Multi Select",
            "fieldId": "customfield_10000",
            "operations": ["set", "add"],
            "allowedValues": ["red", "blue", {"nested": []}],
            "defaultValue": "false",
        },
    },
    "pluginDocument": SENTINEL,
}

CREATE_META: dict[str, object] = {
    "expand": "projects",
    "projects": [
        {
            "self": "https://pasted.example.invalid/rest/api/2/project/EX",
            "id": "10000",
            "key": "EX",
            "name": "Example Project ✓",
            "avatarUrls": {"48x48": None},
            "issuetypes": [
                {
                    "self": None,
                    "id": "1",
                    "description": None,
                    "iconUrl": "https://pasted.example.invalid/icons/bug.png",
                    "name": "Bug",
                    "subtask": False,
                    "avatarId": 10000,
                    "fields": {
                        "issuetype": {
                            "required": True,
                            "name": "Issue Type",
                            "fieldId": "issuetype",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                            "pluginField": {"nested": [1, None]},
                        }
                    },
                    "pluginIssueType": SENTINEL,
                }
            ],
            "pluginProject": {"capped": True},
        },
        {
            "self": None,
            "id": "10001",
            "key": "ABC",
            "name": "Alphabetical",
            "issuetypes": [],
        },
    ],
    "pluginDocument": [None, False],
}

TRANSITIONS: dict[str, object] = {
    "expand": "transitions",
    "transitions": [
        {
            "id": "31",
            "name": "Start Progress",
            "to": {
                "self": "https://pasted.example.invalid/rest/api/2/status/3",
                "name": "In Progress",
                "statusCategory": {"id": 4, "key": "indeterminate"},
            },
            "fields": {
                "resolution": {
                    "required": False,
                    "name": "Resolution",
                    "fieldId": "resolution",
                    "operations": ["set"],
                    "allowedValues": [{"id": "1", "name": "Fixed"}],
                    "pluginField": {"nested": None},
                }
            },
            "pluginTransition": SENTINEL,
        },
        {"id": "41", "name": "Done", "to": None, "fields": {}},
    ],
    "pluginDocument": {"nested": [None]},
}


def read_with_transport(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    invoke: Callable[[], dict[str, object]],
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Run one reader with a fake transport and record the surfaced request."""
    seen: list[tuple[str, dict[str, str | int]]] = []
    tokens: list[str] = []

    def fake_bearer_session(token: str) -> object:
        tokens.append(token)
        return nullcontext(None)

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append((url, dict(params)))
        return document

    monkeypatch.setattr(jira_metadata, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira_metadata, "get_json_object", fake_get_json_object)
    snapshot = deepcopy(document)
    result = invoke()
    assert result == snapshot
    return result, seen, tokens


def read_edit_meta(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    *,
    base: str = BASE,
    argument: str = KEY,
    allow_http_loopback: bool = False,
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the edit metadata reader with a fake transport."""
    return read_with_transport(
        monkeypatch,
        document,
        lambda: jira_metadata.get_edit_meta(
            base,
            argument,
            token=TOKEN,
            allow_http_loopback=allow_http_loopback,
        ),
    )


def read_create_meta(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    *,
    base: str = BASE,
    project: object = None,
    allow_http_loopback: bool = False,
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the create metadata reader with a fake transport."""
    return read_with_transport(
        monkeypatch,
        document,
        lambda: jira_metadata.get_create_meta(
            base,
            token=TOKEN,
            project=cast("str | None", project),
            allow_http_loopback=allow_http_loopback,
        ),
    )


def read_transition_fields(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    *,
    base: str = BASE,
    argument: str = KEY,
    transition_id: object = None,
    allow_http_loopback: bool = False,
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the transition metadata reader with a fake transport."""
    return read_with_transport(
        monkeypatch,
        document,
        lambda: jira_metadata.get_transition_fields(
            base,
            argument,
            token=TOKEN,
            transition_id=cast("str | None", transition_id),
            allow_http_loopback=allow_http_loopback,
        ),
    )


def refuse_every_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any session or request an immediate test failure."""

    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_object(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira_metadata, "bearer_session", unexpected_session)
    monkeypatch.setattr(jira_metadata, "get_json_object", unexpected_object)


def test_edit_meta_uses_the_fixed_route_and_preserves_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, tokens = read_edit_meta(monkeypatch, EDIT_META)

    assert document == EDIT_META
    assert document["pluginDocument"] == SENTINEL
    assert seen == [(EDIT_META_PATH, {})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_edit_meta_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_edit_meta(monkeypatch, EDIT_META, base=base)

    assert seen == [(EDIT_META_PATH, {})]


def test_a_pasted_browse_url_supplies_only_the_edit_meta_issue_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argument = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=edit#top"

    document, seen, _ = read_edit_meta(monkeypatch, EDIT_META, argument=argument)

    assert document == EDIT_META
    assert seen == [(EDIT_META_PATH, {})]


@pytest.mark.parametrize(
    "argument",
    [
        "",
        " ",
        "demo-42",
        "DEMO",
        "DEMO-42 ",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
        f"https://pasted.example.invalid/browse/{KEY}\ud800",
    ],
)
def test_edit_meta_rejects_an_unusable_key_before_any_session(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="issue key"):
        jira_metadata.get_edit_meta(BASE, argument, token=TOKEN)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"fields": None},
        {"fields": []},
        {"fields": "text"},
        {"fields": 7},
    ],
    ids=["missing", "null", "array", "text", "integer"],
)
def test_edit_meta_rejects_a_missing_or_non_object_fields_member(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="edit metadata fields object"):
        read_edit_meta(monkeypatch, document)


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_edit_meta_field_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    document: dict[str, object] = {"fields": {"summary": SUMMARY_FIELD, "late": entry}}

    with pytest.raises(AtlaWireError, match="edit metadata field objects"):
        read_edit_meta(monkeypatch, document)


def test_edit_meta_accepts_an_empty_fields_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {"fields": {}, "pluginDocument": SENTINEL}

    result, seen, _ = read_edit_meta(monkeypatch, document)

    assert result == document
    assert seen == [(EDIT_META_PATH, {})]


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?expand=renderedFields",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_edit_meta_rejects_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira_metadata.get_edit_meta(base, KEY, token=TOKEN)


def test_edit_meta_accepts_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_edit_meta(
        monkeypatch, EDIT_META, base=LOOPBACK, allow_http_loopback=True
    )

    assert document == EDIT_META
    assert seen == [(f"{LOOPBACK}/rest/api/2/issue/{KEY}/editmeta", {})]


def test_create_meta_requests_documented_field_expansion_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, tokens = read_create_meta(monkeypatch, CREATE_META)

    assert document == CREATE_META
    assert document["pluginDocument"] == [None, False]
    assert seen == [(CREATE_META_PATH, {"expand": "projects.issuetypes.fields"})]
    assert tokens == [TOKEN]


def test_create_meta_sends_an_exact_project_key_as_the_documented_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_create_meta(
        monkeypatch, CREATE_META, project="DEMO"
    )

    assert document == CREATE_META
    assert seen == [
        (
            CREATE_META_PATH,
            {"expand": "projects.issuetypes.fields", "projectKeys": "DEMO"},
        )
    ]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_create_meta_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_create_meta(monkeypatch, CREATE_META, base=base, project="DEMO")

    assert seen[0][0] == CREATE_META_PATH


@pytest.mark.parametrize(
    "project",
    [
        "",
        " ",
        "demo",
        "Demo",
        "DEMO-1",
        "DEMO 1",
        'DEMO"',
        "1DEMO",
        "DEMO\u0000",
        7,
        True,
        ["DEMO"],
    ],
    ids=[
        "empty",
        "blank",
        "lowercase",
        "mixed-case",
        "hyphen",
        "space",
        "quote",
        "leading-digit",
        "control",
        "integer",
        "boolean",
        "array",
    ],
)
def test_create_meta_rejects_an_unusable_project_before_any_session(
    monkeypatch: pytest.MonkeyPatch, project: object
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="project key"):
        jira_metadata.get_create_meta(
            BASE,
            token=TOKEN,
            project=cast("str | None", project),
        )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"projects": None},
        {"projects": {}},
        {"projects": "text"},
        {"projects": 7},
    ],
    ids=["missing", "null", "object", "text", "integer"],
)
def test_create_meta_rejects_a_missing_or_non_array_projects_member(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="projects array"):
        read_create_meta(monkeypatch, document)


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ({"projects": [None]}, "project objects"),
        ({"projects": [{"issuetypes": None}]}, "issuetypes array"),
        ({"projects": [{"issuetypes": {}}]}, "issuetypes array"),
        ({"projects": [{"issuetypes": [None]}]}, "issue type objects"),
        ({"projects": [{"issuetypes": [{"fields": []}]}]}, "issue type fields object"),
        (
            {"projects": [{"issuetypes": [{"fields": {"summary": None}}]}]},
            "issue type field objects",
        ),
    ],
    ids=[
        "malformed-project",
        "null-issuetypes",
        "object-issuetypes",
        "malformed-issue-type",
        "array-fields",
        "malformed-field",
    ],
)
def test_create_meta_rejects_a_malformed_documented_shape(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    diagnostic: str,
) -> None:
    with pytest.raises(AtlaWireError, match=diagnostic):
        read_create_meta(monkeypatch, document)


def test_create_meta_accepts_an_empty_projects_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {"expand": "projects", "projects": []}

    result, seen, _ = read_create_meta(monkeypatch, document)

    assert result == document
    assert seen == [(CREATE_META_PATH, {"expand": "projects.issuetypes.fields"})]


def test_a_malformed_late_create_project_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {"projects": [{"id": "10000", "key": "EX"}, 7]}

    with pytest.raises(AtlaWireError, match="project objects"):
        read_create_meta(monkeypatch, document)


def test_a_malformed_late_create_issue_type_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {
        "projects": [
            {
                "id": "10000",
                "issuetypes": [{"id": "1", "subtask": False}, {"id": 2}],
            }
        ]
    }

    with pytest.raises(AtlaWireError, match="issue type objects"):
        read_create_meta(monkeypatch, document)


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?projectKeys=DEMO",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_create_meta_rejects_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira_metadata.get_create_meta(base, token=TOKEN, project="DEMO")


def test_create_meta_accepts_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_create_meta(
        monkeypatch, CREATE_META, base=LOOPBACK, allow_http_loopback=True
    )

    assert document == CREATE_META
    assert seen == [
        (
            f"{LOOPBACK}/rest/api/2/issue/createmeta",
            {"expand": "projects.issuetypes.fields"},
        )
    ]


def test_transition_fields_use_the_fixed_expanded_route_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, tokens = read_transition_fields(monkeypatch, TRANSITIONS)

    assert document == TRANSITIONS
    assert document["pluginDocument"] == {"nested": [None]}
    assert seen == [(TRANSITIONS_PATH, {"expand": "transitions.fields"})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize(
    "transition_id",
    [
        "31",
        "031",
        "12345678901234567890",
        "start-progress",
        "a&b=c?d#e+f/g%h",
        "переход ✓",
        " ",
    ],
    ids=[
        "numeric",
        "leading-zero",
        "long-numeric",
        "nonnumeric",
        "reserved-query-characters",
        "unicode",
        "space-only",
    ],
)
def test_transition_fields_send_any_opaque_nonempty_id_unchanged(
    monkeypatch: pytest.MonkeyPatch, transition_id: str
) -> None:
    document, seen, _ = read_transition_fields(
        monkeypatch, TRANSITIONS, transition_id=transition_id
    )

    assert document == TRANSITIONS
    assert seen == [
        (
            TRANSITIONS_PATH,
            {"expand": "transitions.fields", "transitionId": transition_id},
        )
    ]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_transition_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_transition_fields(monkeypatch, TRANSITIONS, base=base)

    assert seen == [(TRANSITIONS_PATH, {"expand": "transitions.fields"})]


def test_a_pasted_browse_url_supplies_only_the_transition_issue_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argument = f"https://pasted.example.invalid/jira/browse/{KEY}/?tab=workflow"

    document, seen, _ = read_transition_fields(
        monkeypatch, TRANSITIONS, argument=argument
    )

    assert document == TRANSITIONS
    assert seen == [(TRANSITIONS_PATH, {"expand": "transitions.fields"})]


@pytest.mark.parametrize(
    "argument",
    [
        "",
        "demo-42",
        "DEMO-42x",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
    ],
)
def test_transition_fields_reject_an_unusable_key_before_any_session(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="issue key"):
        jira_metadata.get_transition_fields(BASE, argument, token=TOKEN)


@pytest.mark.parametrize(
    ("transition_id", "diagnostic"),
    [
        ("", "non-empty"),
        ("\x00", "control-free"),
        ("bad\nid", "control-free"),
        ("bad\tid", "control-free"),
        ("bad\x7fid", "control-free"),
        ("bad\x85id", "control-free"),
        ("\ud800", "valid UTF-8"),
        (7, "non-empty"),
        (True, "non-empty"),
        (["1"], "non-empty"),
    ],
    ids=[
        "empty",
        "nul",
        "newline",
        "tab",
        "del",
        "c1-control",
        "lone-surrogate",
        "integer",
        "boolean",
        "array",
    ],
)
def test_transition_fields_reject_an_unusable_id_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    transition_id: object,
    diagnostic: str,
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match=diagnostic) as raised:
        jira_metadata.get_transition_fields(
            BASE,
            KEY,
            token=TOKEN,
            transition_id=cast("str | None", transition_id),
        )
    if isinstance(transition_id, str):
        assert transition_id not in str(raised.value)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"transitions": None},
        {"transitions": {}},
        {"transitions": "text"},
        {"transitions": 7},
    ],
    ids=["missing", "null", "object", "text", "integer"],
)
def test_transition_fields_reject_a_missing_or_non_array_transitions_member(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="transitions array"):
        read_transition_fields(monkeypatch, document)


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ({"transitions": [None]}, "transition objects"),
        ({"transitions": [{"fields": None}]}, "transition fields object"),
        ({"transitions": [{"fields": []}]}, "transition fields object"),
        (
            {"transitions": [{"fields": {"resolution": None}}]},
            "transition field objects",
        ),
    ],
    ids=[
        "malformed-transition",
        "null-fields",
        "array-fields",
        "malformed-field",
    ],
)
def test_transition_fields_reject_a_malformed_documented_shape(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    diagnostic: str,
) -> None:
    with pytest.raises(AtlaWireError, match=diagnostic):
        read_transition_fields(monkeypatch, document)


def test_transition_fields_accept_an_empty_transitions_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {"expand": "transitions", "transitions": []}

    result, seen, _ = read_transition_fields(monkeypatch, document)

    assert result == document
    assert seen == [(TRANSITIONS_PATH, {"expand": "transitions.fields"})]


def test_a_malformed_late_transition_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {
        "transitions": [{"id": "31", "name": "Start Progress"}, {"id": 41}]
    }

    with pytest.raises(AtlaWireError, match="transition objects"):
        read_transition_fields(monkeypatch, document)


def test_a_malformed_late_transition_field_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: dict[str, object] = {
        "transitions": [
            {
                "id": "31",
                "fields": {"resolution": {"required": False}, "late": 7},
            }
        ]
    }

    with pytest.raises(AtlaWireError, match="transition field objects"):
        read_transition_fields(monkeypatch, document)


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?expand=transitions.fields",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_transition_fields_reject_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    refuse_every_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira_metadata.get_transition_fields(base, KEY, token=TOKEN)


def test_transition_fields_accept_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_transition_fields(
        monkeypatch, TRANSITIONS, base=LOOPBACK, allow_http_loopback=True
    )

    assert document == TRANSITIONS
    assert seen == [
        (
            f"{LOOPBACK}/rest/api/2/issue/{KEY}/transitions",
            {"expand": "transitions.fields"},
        )
    ]


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ({"fields": {SENTINEL: None}}, "edit metadata field objects"),
        ({"projects": [SENTINEL]}, "project objects"),
        ({"transitions": [SENTINEL]}, "transition objects"),
    ],
    ids=["edit-meta", "create-meta", "transitions"],
)
def test_shape_errors_never_echo_server_content(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    diagnostic: str,
) -> None:
    with pytest.raises(AtlaWireError, match=diagnostic) as raised:
        if "fields" in document:
            read_edit_meta(monkeypatch, document)
        elif "projects" in document:
            read_create_meta(monkeypatch, document)
        else:
            read_transition_fields(monkeypatch, document)
    assert SENTINEL not in str(raised.value)

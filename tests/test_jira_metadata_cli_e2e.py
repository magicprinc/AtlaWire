"""Installed-CLI loopback checks for the Jira issue metadata commands.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance or reads a real credential store. The tests define the
expected command contract before the shared CLI is wired:

* ``jira-edit-meta ISSUE``
* ``jira-create-meta [--project KEY]``
* ``jira-transition-fields ISSUE [--transition-id ID]``
"""

import json
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "fixture-jira-metadata-cli-token"
CONTEXT = "/jira"
KEY = "DEMO-42"
SENTINEL = "JIRA-METADATA-CLI-SENTINEL"
EDIT_META_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}/editmeta"
CREATE_META_PATH = f"{CONTEXT}/rest/api/2/issue/createmeta"
TRANSITIONS_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}/transitions"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-jira-metadata.json")
)

EDIT_META: dict[str, object] = {
    "fields": {
        "summary": {
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
        },
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
        },
    },
    "pluginDocument": {"kept": True, "nested": [None, 1.5]},
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
                    "pluginIssueType": {"kept": True},
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
            "pluginTransition": {"kept": True},
        },
        {"id": "41", "name": "Done", "to": None, "fields": {}},
    ],
    "pluginDocument": {"nested": [None]},
}

Case = tuple[tuple[str, ...], str, dict[str, list[str]], object]

CASES: list[Case] = [
    (("jira-edit-meta", KEY), EDIT_META_PATH, {}, EDIT_META),
    (
        ("jira-create-meta",),
        CREATE_META_PATH,
        {"expand": ["projects.issuetypes.fields"]},
        CREATE_META,
    ),
    (
        ("jira-create-meta", "--project", "DEMO"),
        CREATE_META_PATH,
        {"expand": ["projects.issuetypes.fields"], "projectKeys": ["DEMO"]},
        CREATE_META,
    ),
    (
        ("jira-transition-fields", KEY),
        TRANSITIONS_PATH,
        {"expand": ["transitions.fields"]},
        TRANSITIONS,
    ),
    (
        ("jira-transition-fields", KEY, "--transition-id", "31"),
        TRANSITIONS_PATH,
        {"expand": ["transitions.fields"], "transitionId": ["31"]},
        TRANSITIONS,
    ),
]

CASE_IDS = [
    "edit-meta",
    "create-meta",
    "create-meta-project",
    "transition-fields",
    "transition-id",
]


def environment(origin: str) -> dict[str, str]:
    """Point Jira at the loopback context and keep every other source inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
        "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
    }


def run_case(
    args: tuple[str, ...],
    path: str,
    body: object,
    *,
    status: int = 200,
    location: str | None = None,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
    list[Request],
]:
    """Run one installed command against one synthetic loopback response.

    GET requests are recorded with their query and Authorization header.
    Any write method is recorded separately and answered with 405, so a test
    can prove that the command never attempted a mutation.
    """
    seen: list[Request] = []
    accepts: list[str | None] = []
    mutations: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            _, request_path, _, authorization = record
            if request_path != path or authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            if location is not None:
                send_bytes(
                    self,
                    302,
                    b"",
                    content_type=None,
                    extra_headers={"Location": location},
                )
                return
            if status != 200:
                send_json(self, status, {"message": SENTINEL})
                return
            send_json(self, 200, body)

        def _refuse_mutation(self) -> None:
            mutations.append(request_record(self))
            send_json(self, 405, {"message": SENTINEL})

        do_POST = _refuse_mutation
        do_PUT = _refuse_mutation
        do_DELETE = _refuse_mutation
        do_PATCH = _refuse_mutation

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [*args, "--token-from-env", "--allow-http-loopback"],
            environment(origin),
        )
    return result, seen, accepts, mutations


def expected_get(path: str, query: dict[str, list[str]]) -> list[Request]:
    return [("GET", path, query, f"Bearer {TOKEN}")]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-jira-metadata" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


@pytest.mark.parametrize(
    ("args", "path", "query", "body"),
    CASES,
    ids=CASE_IDS,
)
def test_installed_metadata_command_prints_the_raw_document(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: object,
) -> None:
    result, seen, accepts, mutations = run_case(args, path, body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == body
    assert TOKEN not in result.stdout
    assert seen == expected_get(path, query)
    assert len(seen) == 1
    assert {record[0] for record in seen} == {"GET"}
    assert accepts == ["application/json"]
    assert mutations == []


def test_installed_edit_meta_preserves_unknown_nested_members() -> None:
    result, seen, _, _ = run_case(
        ("jira-edit-meta", KEY), EDIT_META_PATH, EDIT_META
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["pluginDocument"] == {"kept": True, "nested": [None, 1.5]}
    assert document["fields"]["summary"]["defaultValue"] is None
    assert document["fields"]["summary"]["pluginField"]["nested"][1] == {
        "deep": "false"
    }
    assert seen == expected_get(EDIT_META_PATH, {})


def test_installed_create_meta_preserves_the_legacy_projects_array() -> None:
    result, seen, _, _ = run_case(
        ("jira-create-meta",), CREATE_META_PATH, CREATE_META
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["expand"] == "projects"
    assert len(document["projects"]) == 2
    assert document["projects"][0]["issuetypes"][0]["fields"]["issuetype"][
        "required"
    ] is True
    assert document["pluginDocument"] == [None, False]
    assert seen == expected_get(
        CREATE_META_PATH, {"expand": ["projects.issuetypes.fields"]}
    )


def test_installed_transition_fields_preserves_unknown_members() -> None:
    result, seen, _, _ = run_case(
        ("jira-transition-fields", KEY), TRANSITIONS_PATH, TRANSITIONS
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["expand"] == "transitions"
    assert len(document["transitions"]) == 2
    assert document["transitions"][0]["pluginTransition"] == {"kept": True}
    assert document["pluginDocument"] == {"nested": [None]}
    assert seen == expected_get(
        TRANSITIONS_PATH, {"expand": ["transitions.fields"]}
    )


@pytest.mark.parametrize(
    ("args", "path", "query", "body"),
    CASES[:1] + CASES[3:4],
    ids=["edit-meta", "transition-fields"],
)
def test_installed_metadata_command_pins_a_foreign_pasted_url_to_the_server(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: object,
) -> None:
    pasted = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=edit#top"
    replaced = (args[0], pasted, *args[2:])

    result, seen, accepts, mutations = run_case(replaced, path, body)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == body
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert mutations == []


@pytest.mark.parametrize(
    ("args", "diagnostic", "literal"),
    [
        (("jira-edit-meta", "demo-42"), "issue key", "demo-42"),
        (("jira-edit-meta", "DEMO"), "issue key", "DEMO-"),
        (
            (
                "jira-edit-meta",
                f"https://pasted.example.invalid/browse/{KEY}/extra",
            ),
            "issue key",
            "/extra",
        ),
        (("jira-create-meta", "--project", "demo"), "project key", "demo"),
        (("jira-create-meta", "--project", "DEMO-1"), "project key", "DEMO-1"),
        (("jira-create-meta", "--project", "DE MO"), "project key", "DE MO"),
        (
            ("jira-transition-fields", "demo-42"),
            "issue key",
            "demo-42",
        ),
        (
            ("jira-transition-fields", KEY, "--transition-id", ""),
            "transition ID",
            None,
        ),
        (
            ("jira-transition-fields", KEY, "--transition-id", "bad\x01id"),
            "control-free",
            "bad\x01id",
        ),
        (
            ("jira-transition-fields", KEY, "--transition-id", "bad\x7fid"),
            "control-free",
            "bad\x7fid",
        ),
    ],
    ids=[
        "lowercase-key",
        "project-only-key",
        "browse-with-extra-path",
        "lowercase-project",
        "hyphenated-project",
        "spaced-project",
        "lowercase-transition-key",
        "empty-transition-id",
        "control-transition-id",
        "del-transition-id",
    ],
)
def test_installed_metadata_command_rejects_bad_input_without_a_request(
    args: tuple[str, ...], diagnostic: str, literal: str | None
) -> None:
    path = EDIT_META_PATH if args[0] == "jira-edit-meta" else TRANSITIONS_PATH

    result, seen, accepts, mutations = run_case(args, path, {})

    assert result.returncode != 0
    assert result.stdout == ""
    assert diagnostic in result.stderr
    if literal is not None:
        assert literal not in result.stderr
    assert TOKEN not in result.stderr
    assert SENTINEL not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert accepts == []
    assert mutations == []


@pytest.mark.parametrize(
    "transition_id",
    [
        "start-progress",
        "a&b=c?d#e+f/g%h",
        "переход ✓",
        " ",
    ],
    ids=["nonnumeric", "reserved-query-characters", "unicode", "space-only"],
)
def test_installed_transition_fields_send_an_opaque_id_as_one_query_value(
    transition_id: str,
) -> None:
    args = ("jira-transition-fields", KEY, "--transition-id", transition_id)

    result, seen, accepts, mutations = run_case(
        args, TRANSITIONS_PATH, TRANSITIONS
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == TRANSITIONS
    assert seen == expected_get(
        TRANSITIONS_PATH,
        {"expand": ["transitions.fields"], "transitionId": [transition_id]},
    )
    assert len(seen) == 1
    assert {record[0] for record in seen} == {"GET"}
    assert accepts == ["application/json"]
    assert mutations == []
    assert TOKEN not in result.stdout


@pytest.mark.parametrize(
    ("args", "path", "query", "body"),
    CASES,
    ids=CASE_IDS,
)
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401: authentication rejected."),
        (403, "HTTP 403: access denied."),
        (404, "HTTP 404: request failed."),
        (500, "HTTP 500: request failed."),
        (206, "HTTP 206: partial content is not supported."),
    ],
)
def test_installed_metadata_command_maps_http_errors(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: object,
    status: int,
    message: str,
) -> None:
    result, seen, accepts, mutations = run_case(args, path, body, status=status)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {message}\n"
    assert SENTINEL not in result.stdout + result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert mutations == []


@pytest.mark.parametrize(
    ("args", "path", "query", "body"),
    CASES,
    ids=CASE_IDS,
)
def test_installed_metadata_command_refuses_a_redirect_without_following_it(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: object,
) -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

        def _refuse_mutation(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 405, {"message": SENTINEL})

        do_POST = _refuse_mutation
        do_PUT = _refuse_mutation
        do_DELETE = _refuse_mutation
        do_PATCH = _refuse_mutation

    with serving(Honeypot) as target:
        location = f"http://127.0.0.1:{target.server_port}/stolen"
        result, seen, accepts, mutations = run_case(
            args, path, body, location=location
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert honeypot == []
    assert mutations == []


@pytest.mark.parametrize(
    ("args", "path", "query", "body", "diagnostic"),
    [
        (
            ("jira-edit-meta", KEY),
            EDIT_META_PATH,
            {},
            {},
            "edit metadata fields object",
        ),
        (
            ("jira-edit-meta", KEY),
            EDIT_META_PATH,
            {},
            {"fields": []},
            "edit metadata fields object",
        ),
        (
            ("jira-edit-meta", KEY),
            EDIT_META_PATH,
            {},
            {"fields": {"summary": 7}},
            "edit metadata field objects",
        ),
        (
            ("jira-edit-meta", KEY),
            EDIT_META_PATH,
            {},
            {"fields": {"summary": {"required": True}, "late": 7}},
            "edit metadata field objects",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {},
            "projects array",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": {}},
            "projects array",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": [None]},
            "project objects",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": [{"issuetypes": {"fields": {}}}]},
            "issuetypes array",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": [{"issuetypes": [{"fields": []}]}]},
            "issue type fields object",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": [{"issuetypes": [{"fields": {"summary": 7}}]}]},
            "issue type field objects",
        ),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"projects": [{"id": "10000"}, 7]},
            "project objects",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {},
            "transitions array",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"transitions": {}},
            "transitions array",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"transitions": [None]},
            "transition objects",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"transitions": [{"fields": []}]},
            "transition fields object",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"transitions": [{"fields": {"resolution": 7}}]},
            "transition field objects",
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"transitions": [{"id": "31", "name": "Start Progress"}, 7]},
            "transition objects",
        ),
    ],
    ids=[
        "edit-missing-fields",
        "edit-array-fields",
        "edit-malformed-field",
        "edit-late-field",
        "create-missing-projects",
        "create-object-projects",
        "create-malformed-project",
        "create-object-issuetypes",
        "create-array-fields",
        "create-malformed-field",
        "create-late-project",
        "transition-missing-array",
        "transition-object-array",
        "transition-malformed-entry",
        "transition-array-fields",
        "transition-malformed-field",
        "transition-late-entry",
    ],
)
def test_installed_metadata_command_rejects_a_malformed_document(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: object,
    diagnostic: str,
) -> None:
    result, seen, accepts, mutations = run_case(args, path, body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert mutations == []


@pytest.mark.parametrize(
    ("args", "path", "query"),
    [
        (("jira-edit-meta", KEY), EDIT_META_PATH, {}),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
        ),
    ],
    ids=["edit-meta", "create-meta", "transition-fields"],
)
def test_installed_metadata_command_rejects_a_non_object_body(
    args: tuple[str, ...], path: str, query: dict[str, list[str]]
) -> None:
    result, seen, accepts, mutations = run_case(args, path, [])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Expected a JSON object" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert mutations == []


@pytest.mark.parametrize(
    ("args", "path", "query", "body"),
    [
        (("jira-edit-meta", KEY), EDIT_META_PATH, {}, {"fields": {}}),
        (
            ("jira-create-meta",),
            CREATE_META_PATH,
            {"expand": ["projects.issuetypes.fields"]},
            {"expand": "projects", "projects": []},
        ),
        (
            ("jira-transition-fields", KEY),
            TRANSITIONS_PATH,
            {"expand": ["transitions.fields"]},
            {"expand": "transitions", "transitions": []},
        ),
    ],
    ids=["edit-meta", "create-meta", "transition-fields"],
)
def test_installed_metadata_command_accepts_empty_metadata(
    args: tuple[str, ...],
    path: str,
    query: dict[str, list[str]],
    body: dict[str, object],
) -> None:
    result, seen, accepts, mutations = run_case(args, path, body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == body
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]
    assert mutations == []


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ({"fields": {SENTINEL: 7}}, "field objects"),
        ({"projects": [SENTINEL]}, "project objects"),
        ({"transitions": [SENTINEL]}, "transition objects"),
    ],
    ids=["edit-meta", "create-meta", "transition-fields"],
)
def test_installed_metadata_command_never_echoes_server_content(
    document: dict[str, object], diagnostic: str
) -> None:
    if "fields" in document:
        args, path = ("jira-edit-meta", KEY), EDIT_META_PATH
        query: dict[str, list[str]] = {}
    elif "projects" in document:
        args, path = ("jira-create-meta",), CREATE_META_PATH
        query = {"expand": ["projects.issuetypes.fields"]}
    else:
        args, path = ("jira-transition-fields", KEY), TRANSITIONS_PATH
        query = {"expand": ["transitions.fields"]}

    result, seen, _, _ = run_case(args, path, document)

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(path, query)


def test_installed_metadata_command_never_fetches_a_returned_link() -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

        def _refuse_mutation(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 405, {"message": SENTINEL})

        do_POST = _refuse_mutation
        do_PUT = _refuse_mutation
        do_DELETE = _refuse_mutation
        do_PATCH = _refuse_mutation

    with serving(Honeypot) as target:
        link = f"http://127.0.0.1:{target.server_port}/must-not-be-read"
        body = {**EDIT_META, "self": link, "next": link}
        result, seen, accepts, mutations = run_case(
            ("jira-edit-meta", KEY), EDIT_META_PATH, body
        )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["self"] == link
    assert json.loads(result.stdout)["next"] == link
    assert seen == expected_get(EDIT_META_PATH, {})
    assert accepts == ["application/json"]
    assert honeypot == []
    assert mutations == []

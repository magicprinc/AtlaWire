"""Opt-in real-server checks for the api-request command.

Run explicitly::

    C:/Python315/python.exe -B -m pytest -q checks/test_sdk_live.py

The CLI loads the owner's saved BBK credentials. This module never reads or
prints tokens, URLs, response bodies, or fixture values.
"""

import json
import subprocess
import sys

import pytest

CLI = (sys.executable, "-P", "-B", "-m", "atlawire")
TIMEOUT = 60


def _run(*args: str) -> dict[str, object] | list[object]:
    completed = subprocess.run(
        [*CLI, "api-request", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        # Do not print stderr: it can contain server or credential material.
        pytest.fail("live request failed", pytrace=False)
    try:
        value = json.loads(completed.stdout)
    except ValueError:
        pytest.fail("live response was not JSON", pytrace=False)
    return value


def test_jira_myself_is_a_json_object() -> None:
    value = _run("jira", "GET", "/rest/api/2/myself")
    assert isinstance(value, dict)
    assert isinstance(value.get("name"), str)


def test_jira_priorities_is_a_json_array() -> None:
    value = _run("jira", "GET", "/rest/api/2/priority")
    assert isinstance(value, list)
    assert value and isinstance(value[0], dict)


def test_jira_search_read_only_post_returns_an_issue_object() -> None:
    value = _run(
        "jira",
        "POST",
        "/rest/api/2/search",
        "--body",
        '{"jql":"order by created DESC","maxResults":1}',
    )
    assert isinstance(value, dict)
    assert isinstance(value.get("issues"), list)
    assert value["issues"]


def test_confluence_current_user_is_a_json_object() -> None:
    value = _run("confluence", "GET", "/rest/api/user/current")
    assert isinstance(value, dict)
    assert value.get("type") == "known"


def test_confluence_space_page_is_a_json_object() -> None:
    value = _run(
        "confluence",
        "GET",
        "/rest/api/space",
        "--params",
        '{"limit":1}',
    )
    assert isinstance(value, dict)
    assert isinstance(value.get("results"), list)


def test_confluence_cql_page_is_a_json_object() -> None:
    value = _run(
        "confluence",
        "GET",
        "/rest/api/content/search",
        "--params",
        '{"cql":"type=page","limit":1}',
    )
    assert isinstance(value, dict)
    assert isinstance(value.get("results"), list)


def test_jira_projects_is_a_json_array() -> None:
    value = _run("jira", "GET", "/rest/api/2/project")
    assert isinstance(value, list)
    assert value and isinstance(value[0], dict)


def test_jira_fields_is_a_json_array() -> None:
    value = _run("jira", "GET", "/rest/api/2/field")
    assert isinstance(value, list)
    assert value and isinstance(value[0], dict)


def test_bitbucket_projects_is_a_json_page() -> None:
    value = _run(
        "bitbucket",
        "GET",
        "/rest/api/1.0/projects",
        "--params",
        '{"limit":1}',
    )
    assert isinstance(value, dict)
    assert isinstance(value.get("values"), list)


def test_bitbucket_users_is_a_json_page() -> None:
    value = _run(
        "bitbucket",
        "GET",
        "/rest/api/1.0/users",
        "--params",
        '{"limit":1}',
    )
    assert isinstance(value, dict)
    assert isinstance(value.get("values"), list)


def test_real_not_found_returns_a_parseable_json_error() -> None:
    completed = subprocess.run(
        [
            *CLI,
            "api-request",
            "jira",
            "GET",
            "/rest/api/2/project/ATLASWIRE_NO_SUCH_PROJECT_9X",
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 1
    value = json.loads(completed.stdout)
    assert value["ok"] is False
    assert value["error"]["status"] in {400, 404}
    assert value["error"]["code"].startswith("http_")

"""Offline contract tests for the opt-in live read-batch checks.

The live module in ``checks`` is imported by path. Every test here supplies a
synthetic environment and a fake subprocess runner; no test reads the real
process environment, a credential file, or a product endpoint.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "checks" / "test_live_read_batch.py"

SENTINEL = "SYNTHETIC-LIVE-BATCH-SENTINEL"
ISSUE = "DEMO-42"
NAME = "ada"
REPO = "DEMO/widgets"
PR_ID = "7"
PATH = "src/main/java/demo/WidgetService.java"
REF = "0123456789abcdef0123456789abcdef01234567"
COMMIT = "fedcba9876543210fedcba9876543210fedcba98"
PAGE = "555"
TAG = "v1.0.0"


def _load_live() -> ModuleType:
    spec = importlib.util.spec_from_file_location("atlawire_live_read_batch", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = cast(Any, _load_live())


def synthetic_environment() -> dict[str, str]:
    """Return credential-like sentinels and ordinary settings for isolation."""
    return {
        "PATH": "synthetic-path",
        "HOME": "synthetic-home",
        "USERPROFILE": "synthetic-profile",
        "APPDATA": "synthetic-appdata",
        "BBK_CREDENTIALS": "synthetic-bbk-credentials.json",
        "HTTP_PROXY": "http://synthetic-proxy.invalid:3128",
        "HTTPS_PROXY": "http://synthetic-proxy.invalid:3128",
        "ATLAWIRE_JIRA_URL": "https://jira.synthetic.invalid",
        "ATLAWIRE_JIRA_TOKEN": SENTINEL,
        "ATLAWIRE_CONFLUENCE_TOKEN": SENTINEL,
        "ATLAWIRE_BITBUCKET_TOKEN": SENTINEL,
        "ATLAWIRE_LIVE_JIRA_ISSUE": ISSUE,
        "AWS_SECRET_ACCESS_KEY": SENTINEL,
        "PYTHONPATH": "synthetic-shadow-path",
    }


class Recorder:
    """Capture subprocess arguments and return synthetic output."""

    def __init__(
        self,
        *,
        stdout: bytes = b"[]",
        returncode: int = 0,
        stderr: bytes = b"",
        error: BaseException | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.error = error

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(argv), dict(kwargs)))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )


def run(
    args: tuple[str, ...],
    *,
    recorder: Recorder | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[bytes, Recorder]:
    recording = recorder or Recorder()
    output = live.run_cli(
        args,
        runner=recording,
        environ=synthetic_environment() if environ is None else environ,
    )
    return output, recording


def json_bytes(value: object) -> bytes:
    return json.dumps(value).encode()


def assert_failure(category: str, raw: bytes) -> None:
    with pytest.raises(live.LiveCheckError) as info:
        live._json(raw)
    assert info.value.category == category


def test_batch_and_discovery_commands_are_exact() -> None:
    batch = frozenset(
        {
            "issue-remote-links",
            "jira-priorities",
            "jira-resolutions",
            "jira-issue-types",
            "jira-status-categories",
            "jira-users",
            "pr-merge-status",
            "tags",
            "tag",
            "last-modified",
            "page-attachments",
            "page-comments",
            "page-labels",
            "page-history",
            "page-version",
            "page-url",
            "jira-edit-meta",
            "jira-create-meta",
            "jira-transition-fields",
            "whoami",
            "read-operation",
        }
    )

    assert live.BATCH_COMMANDS == batch
    assert live.DISCOVERY_COMMANDS == frozenset({"jira-me", "page"})
    assert live._DISCOVERY_ARITY == {"jira-me": 1, "page": 2}
    assert live.ALLOWED_COMMANDS == batch | {"jira-me", "page"}
    assert live._READ_OPERATION_IDS == frozenset(
        {
            "bitbucket.project.get",
            "bitbucket.repository.get",
            "confluence.space.get",
            "jira.issue.votes",
            "jira.issue.watchers",
            "jira.project.get",
        }
    )
    assert "jira.server.info" not in live._READ_OPERATION_IDS
    for forbidden in (
        "merge",
        "pr-merge",
        "pr_merge",
        "write",
        "comment",
        "issue-comment",
        "page-create",
        "tag-create",
        "delete",
    ):
        assert forbidden not in live.ALLOWED_COMMANDS


def test_plan_uses_installed_module_and_saved_file_mode() -> None:
    output, recorder = run(("jira-priorities",))

    assert output == b"[]"
    assert len(recorder.calls) == 1
    argv, kwargs = recorder.calls[0]
    assert tuple(argv[: len(live.CLI_PREFIX)]) == live.CLI_PREFIX
    assert tuple(argv[len(live.CLI_PREFIX) :]) == ("jira-priorities",)
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == live.TIMEOUT_SECONDS
    assert kwargs["check"] is False
    assert kwargs["shell"] is False
    assert kwargs["stdin"] == subprocess.DEVNULL

    environment = cast(dict[str, str], kwargs["env"])
    assert environment["PATH"] == "synthetic-path"
    assert environment["HOME"] == "synthetic-home"
    assert environment["BBK_CREDENTIALS"] == "synthetic-bbk-credentials.json"
    assert environment["HTTP_PROXY"] == "http://synthetic-proxy.invalid:3128"
    for excluded in (
        "ATLAWIRE_JIRA_URL",
        "ATLAWIRE_JIRA_TOKEN",
        "ATLAWIRE_CONFLUENCE_TOKEN",
        "ATLAWIRE_BITBUCKET_TOKEN",
        "ATLAWIRE_LIVE_JIRA_ISSUE",
        "AWS_SECRET_ACCESS_KEY",
        "PYTHONPATH",
    ):
        assert excluded not in environment
    assert SENTINEL not in json.dumps(environment)


def test_jira_me_discovery_uses_no_arguments() -> None:
    identity = json_bytes({"name": NAME, "displayName": "Ada", "email": None})
    output, recorder = run(("jira-me",), recorder=Recorder(stdout=identity))

    assert output == identity
    argv, _ = recorder.calls[0]
    assert tuple(argv[len(live.CLI_PREFIX) :]) == ("jira-me",)


@pytest.mark.parametrize(
    "args",
    [
        ("merge", REPO, PR_ID),
        ("pr-merge", REPO, PR_ID),
        ("pr_merge", REPO, PR_ID),
        ("jira-me", "extra"),
        ("jira-me", "--token-from-env"),
        ("jira-priorities", "--token-from-env"),
        ("jira-priorities", "--base-url", "https://synthetic.invalid"),
        ("tags", "--base-url=https://synthetic.invalid"),
        ("jira-users", "--help"),
        ("last-modified", REPO, PATH, "--at"),
        ("last-modified", REPO, PATH, "--at", REF, "--json"),
        ("page", PAGE, "--json"),
        ("page-history", PAGE, "--json"),
        ("page-version", PAGE, "0"),
        ("page-version", PAGE, "-1"),
        ("page-url", PAGE, "--token-from-env"),
        ("jira-edit-meta", "demo-42"),
        ("jira-create-meta", "--project", "demo"),
        ("jira-create-meta", "--project", "DEMO", "--json"),
        ("jira-transition-fields", ISSUE, "--transition-id", "31"),
        ("whoami", "--json"),
        ("whoami", "extra"),
        (
            "read-operation",
            "jira.unknown.operation",
            "--params",
            '{"issueIdOrKey":"DEMO-42"}',
        ),
        (
            "read-operation",
            "jira.issue.votes",
            "--query",
            '{"start":0}',
        ),
        (
            "read-operation",
            "jira.issue.votes",
            "--params",
            '{"issueIdOrKey":"DEMO-42","extra":"x"}',
        ),
        (
            "read-operation",
            "jira.issue.votes",
            "--params",
            '{"issueIdOrKey":"--help"}',
        ),
        (
            "read-operation",
            "jira.issue.votes",
            "--params",
            '{"issueIdOrKey":"DEMO-42","issueIdOrKey":"DEMO-43"}',
        ),
        (
            "read-operation",
            "jira.project.get",
            "--params",
            '{"projectIdOrKey":"https://evil.invalid"}',
        ),
        (
            "read-operation",
            "bitbucket.repository.get",
            "--params",
            '{"projectKey":"DEMO","repositorySlug":"widgets","method":"POST"}',
        ),
    ],
)
def test_unknown_write_or_override_arguments_never_start_subprocess(
    args: tuple[str, ...],
) -> None:
    recorder = Recorder(error=AssertionError("no subprocess authorized"))

    with pytest.raises(live.LiveCheckError) as info:
        live.run_cli(args, runner=recorder, environ=synthetic_environment())

    assert info.value.category == "invalid_plan"
    assert recorder.calls == []


def test_new_command_plans_are_fixed() -> None:
    plans = (
        ("page", PAGE),
        ("page-history", PAGE),
        ("page-version", PAGE, "7"),
        ("page-url", PAGE),
        ("jira-edit-meta", ISSUE),
        ("jira-create-meta", "--project", "DEMO"),
        ("jira-transition-fields", ISSUE),
        ("whoami",),
        (
            "read-operation",
            "jira.project.get",
            "--params",
            '{"projectIdOrKey":"DEMO"}',
        ),
    )
    for plan in plans:
        output, recorder = run(plan)

        assert output == b"[]"
        argv, _ = recorder.calls[0]
        assert tuple(argv[len(live.CLI_PREFIX) :]) == plan


def test_read_operation_helper_uses_only_hardcoded_parameters() -> None:
    raw = json_bytes({"key": "DEMO"})
    recorder = Recorder(stdout=raw)

    output = live.run_read_operation(
        "jira.project.get",
        {"projectIdOrKey": "DEMO"},
        runner=recorder,
        environ=synthetic_environment(),
    )

    assert output == raw
    argv, _ = recorder.calls[0]
    assert tuple(argv[len(live.CLI_PREFIX) :]) == (
        "read-operation",
        "jira.project.get",
        "--params",
        '{"projectIdOrKey":"DEMO"}',
    )

    with pytest.raises(live.LiveCheckError) as info:
        live.run_read_operation("jira.server.info", {})
    assert info.value.category == "invalid_plan"

    forbidden = Recorder(error=AssertionError("no subprocess authorized"))
    with pytest.raises(live.LiveCheckError) as extra:
        live.run_read_operation(
            "jira.issue.votes",
            {"issueIdOrKey": ISSUE, "method": "POST"},
            runner=forbidden,
            environ=synthetic_environment(),
        )
    assert extra.value.category == "invalid_plan"
    assert forbidden.calls == []


def test_last_modified_plan_allows_only_the_at_option() -> None:
    raw = json_bytes({"files": {PATH: {"id": COMMIT}}})
    recorder = Recorder(stdout=raw)

    output, _ = run(("last-modified", REPO, PATH, "--at", REF), recorder=recorder)

    assert output == raw
    argv, _ = recorder.calls[0]
    assert tuple(argv[len(live.CLI_PREFIX) :]) == (
        "last-modified",
        REPO,
        PATH,
        "--at",
        REF,
    )


def test_nonzero_exit_reports_only_a_fixed_category(
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder(
        stdout=SENTINEL.encode(),
        stderr=SENTINEL.encode(),
        returncode=1,
    )

    with pytest.raises(live.LiveCheckError) as info:
        run(("jira-priorities",), recorder=recorder)

    assert info.value.category == "cli_failed"
    assert SENTINEL not in str(info.value)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_timeout_and_launch_failure_report_fixed_categories() -> None:
    with pytest.raises(live.LiveCheckError) as timeout:
        run(
            ("jira-priorities",),
            recorder=Recorder(error=subprocess.TimeoutExpired([SENTINEL], 30)),
        )
    assert timeout.value.category == "timeout"
    assert SENTINEL not in str(timeout.value)

    with pytest.raises(live.LiveCheckError) as unavailable:
        run(
            ("jira-priorities",),
            recorder=Recorder(error=OSError(f"{SENTINEL} unavailable")),
        )
    assert unavailable.value.category == "cli_unavailable"
    assert SENTINEL not in str(unavailable.value)


def test_empty_and_oversized_stdout_are_invalid() -> None:
    with pytest.raises(live.LiveCheckError) as empty:
        run(("jira-priorities",), recorder=Recorder(stdout=b""))
    assert empty.value.category == "invalid_output"

    oversized = b"x" * (live.MAX_OUTPUT_BYTES + 1)
    with pytest.raises(live.LiveCheckError) as huge:
        run(("jira-priorities",), recorder=Recorder(stdout=oversized))
    assert huge.value.category == "invalid_output"


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        (b"not-json", "invalid_output"),
        (b"\xff", "invalid_output"),
        (b"\xef\xbb\xbf[]", "invalid_output"),
        (b"{}", "invalid_output"),
        (b"null", "invalid_output"),
        (b'"text"', "invalid_output"),
        (b"[] trailing", "invalid_output"),
        (b"[]", "inconclusive"),
    ],
)
def test_bad_array_shapes_are_rejected(raw: bytes, category: str) -> None:
    with pytest.raises(live.LiveCheckError) as info:
        live._nonempty_array(raw)
    assert info.value.category == category


def test_oversized_json_document_is_rejected_before_decode() -> None:
    raw = b"[" + b" " * live.MAX_OUTPUT_BYTES + b"]"

    assert_failure("invalid_output", raw)


@pytest.mark.parametrize(
    ("name", "validator", "good", "bad"),
    [
        ("ATLAWIRE_LIVE_JIRA_ISSUE", "valid_issue", ISSUE, "--help"),
        ("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", "valid_page_id", PAGE, "-1"),
        (
            "ATLAWIRE_LIVE_BITBUCKET_REPO",
            "valid_repo",
            REPO,
            "-DEMO/widgets",
        ),
        (
            "ATLAWIRE_LIVE_BITBUCKET_PR_ID",
            "valid_positive_id",
            PR_ID,
            "-1",
        ),
        (
            "ATLAWIRE_LIVE_BITBUCKET_FILE_PATH",
            "valid_path",
            PATH,
            "src/../secret.java",
        ),
        (
            "ATLAWIRE_LIVE_BITBUCKET_FILE_REF",
            "valid_commit",
            REF,
            "0123456",
        ),
    ],
)
def test_fixture_validation_fails_closed_without_echoing_values(
    name: str, validator: str, good: str, bad: str
) -> None:
    check = getattr(live, validator)

    assert live.require_fixture({name: good}, name, check) == good
    with pytest.raises(live.FixtureError) as missing:
        live.require_fixture({}, name, check)
    assert missing.value.name == name

    with pytest.raises(live.FixtureError) as invalid:
        live.require_fixture({name: bad}, name, check)
    assert invalid.value.name == name
    assert bad not in str(invalid.value)


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        ("valid_repo", "DEMO"),
        ("valid_repo", "DEMO/.."),
        ("valid_repo", "DEMO/a/b"),
        ("valid_path", "/absolute.java"),
        ("valid_path", "src\\windows.java"),
        ("valid_tag", "a..b"),
        ("valid_tag", "release/"),
        ("valid_tag", "release//x"),
        ("valid_commit", "abc"),
        ("valid_issue", "demo-42"),
        ("valid_page_id", "0"),
        ("valid_positive_id", "0"),
    ],
)
def test_invalid_fixture_forms_are_rejected(validator: str, value: str) -> None:
    assert getattr(live, validator)(value) is False


def test_slash_delimited_tag_names_are_accepted() -> None:
    assert live.valid_tag("release/1.0") is True
    assert live.valid_tag("release/ü") is True


def test_reference_list_requires_shaped_rows_and_a_readable_name() -> None:
    live.check_reference_list(
        json_bytes(
            [
                {"id": "1", "name": "Low"},
                {"id": 2, "name": "High"},
                {"id": 3, "name": None},
            ]
        )
    )

    for raw, category in (
        (b"[]", "inconclusive"),
        (b'{"id": "1"}', "invalid_output"),
        (b'[{"name": "High"}]', "invalid_output"),
        (b'[{"id": "1"}]', "inconclusive"),
        (b'[{"id": "1", "name": ""}]', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_reference_list(raw)
        assert info.value.category == category


def test_remote_links_require_a_nonempty_object_array() -> None:
    live.check_remote_links(
        json_bytes(
            [
                {
                    "id": 10000,
                    "globalId": "system=https://tracker.invalid/&id=1",
                    "relationship": "causes",
                    "application": {"name": "Tracker"},
                    "object": {"url": "https://tracker.invalid/T-1"},
                }
            ]
        )
    )

    for raw, category in (
        (b"[]", "inconclusive"),
        (b"[1]", "invalid_output"),
        (b'[{"globalId": "x"}]', "invalid_output"),
        (b'[{"id": 1, "object": "bad"}]', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_remote_links(raw)
        assert info.value.category == category


def test_current_user_supplies_a_safe_search_name() -> None:
    assert (
        live.check_current_user(
            json_bytes({"name": NAME, "displayName": "Ada", "email": None})
        )
        == NAME
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"displayName": "Ada"}', "invalid_output"),
        (b'{"name": ""}', "invalid_output"),
        (b'{"name": "--help"}', "invalid_output"),
        (b'{"name": "ada", "displayName": 1}', "invalid_output"),
        (b'{"name": "ada", "email": 1}', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_current_user(raw)
        assert info.value.category == category


def test_users_require_the_discovered_user() -> None:
    live.check_users(
        json_bytes(
            [
                {
                    "name": NAME,
                    "displayName": "Ada Lovelace",
                    "emailAddress": "ada@example.invalid",
                    "active": True,
                }
            ]
        ),
        NAME,
    )

    for raw, category in (
        (b"[]", "inconclusive"),
        (b'[{"displayName": "Ada"}]', "invalid_output"),
        (b'[{"name": "ada"}]', "invalid_output"),
        (
            (b'[{"name": "ada", "displayName": "Ada", "emailAddress": 1}]'),
            "invalid_output",
        ),
        (
            b'[{"name": "ada", "displayName": "Ada", "active": "yes"}]',
            "invalid_output",
        ),
        (
            b'[{"name": "grace", "displayName": "Grace"}]',
            "oracle_mismatch",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_users(raw, NAME)
        assert info.value.category == category


def test_merge_status_validates_booleans_outcome_and_conflict_invariant() -> None:
    live.check_merge_status(
        json_bytes(
            {
                "canMerge": True,
                "conflicted": False,
                "outcome": "CLEAN",
                "vetoes": [],
            }
        )
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"canMerge": true, "outcome": "CLEAN"}', "invalid_output"),
        (
            b'{"canMerge": 1, "conflicted": false, "outcome": "CLEAN"}',
            "invalid_output",
        ),
        (
            b'{"canMerge": true, "conflicted": true, "outcome": "CLEAN"}',
            "oracle_mismatch",
        ),
        (
            (
                b'{"canMerge": true, "conflicted": false, "outcome": "CLEAN", '
                b'"vetoes": "none"}'
            ),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_merge_status(raw)
        assert info.value.category == category


def test_tags_return_discoverable_names() -> None:
    assert live.check_tags(json_bytes(["other", TAG])) == ["other", TAG]
    assert live.check_tags(
        json_bytes([{"id": TAG, "displayId": f"refs/tags/{TAG}", "type": "TAG"}])
    ) == [TAG]

    for raw, category in (
        (b"[]", "inconclusive"),
        (b"[1]", "invalid_output"),
        (b'[{"latestCommit": "abc"}]', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_tags(raw)
        assert info.value.category == category


def test_tag_requires_identity_and_validates_present_commit_fields() -> None:
    live.check_tag(
        json_bytes(
            {
                "id": TAG,
                "displayId": f"refs/tags/{TAG}",
                "type": "TAG",
                "latestCommit": COMMIT,
                "latestChangeset": None,
                "hash": "",
            }
        ),
        TAG,
    )
    live.check_tag(
        json_bytes(
            {
                "displayId": f"refs/tags/{TAG}",
                "latestCommit": None,
                "hash": "",
            }
        ),
        TAG,
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"latestCommit": "abc"}', "invalid_output"),
        (
            json_bytes({"displayId": "refs/tags/other", "latestCommit": COMMIT}),
            "oracle_mismatch",
        ),
        (
            json_bytes({"displayId": f"refs/tags/{TAG}", "type": "BRANCH"}),
            "invalid_output",
        ),
        (
            json_bytes({"displayId": f"refs/tags/{TAG}", "latestCommit": "abc"}),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_tag(raw, TAG)
        assert info.value.category == category


def test_last_modified_requires_the_known_path() -> None:
    live.check_last_modified(
        json_bytes(
            {
                "files": {
                    PATH: {
                        "id": COMMIT,
                        "displayId": COMMIT[:11],
                        "author": {"name": "ada"},
                    }
                },
                "latestCommit": {"id": COMMIT, "displayId": COMMIT[:11]},
            }
        ),
        PATH,
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"files": "bad"}', "invalid_output"),
        (b'{"files": {}}', "inconclusive"),
        (json_bytes({"files": {PATH: {"id": "x"}}}), "invalid_output"),
        (
            json_bytes({"files": {"src/Other.java": {"id": COMMIT}}}),
            "inconclusive",
        ),
        (json_bytes({"files": {PATH: {}}}), "invalid_output"),
        (
            json_bytes(
                {
                    "files": {PATH: {"id": COMMIT}},
                    "latestCommit": {"id": "x"},
                }
            ),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_last_modified(raw, PATH)
        assert info.value.category == category


def test_page_attachment_rows_require_metadata() -> None:
    live.check_page_attachments(
        json_bytes(
            {
                "results": [{"id": "200", "title": "design.md"}],
                "start": 0,
                "limit": 2,
                "size": 1,
            }
        )
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"results": []}', "inconclusive"),
        (b'{"results": "bad"}', "invalid_output"),
        (b'{"results": [{"id": "200"}]}', "invalid_output"),
        (b'{"results": [{"title": "design.md"}]}', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_attachments(raw)
        assert info.value.category == category


def test_page_comments_require_storage_bodies_for_roots_and_replies() -> None:
    live.check_page_comments(
        json_bytes(
            {
                "page": {
                    "results": [
                        {
                            "id": "c1",
                            "type": "comment",
                            "body": {"storage": {"value": "<p>Root</p>"}},
                            "children": {
                                "comment": {
                                    "results": [
                                        {
                                            "id": "c2",
                                            "type": "comment",
                                            "body": {
                                                "storage": {"value": "<p>Reply</p>"}
                                            },
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                    "size": 1,
                },
                "unknownTopLevel": {"kept": True},
            }
        )
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"results": []}', "inconclusive"),
        (b'{"results": [{"id": "c1", "type": "comment"}]}', "invalid_output"),
        (
            json_bytes(
                {"results": [{"id": "c1", "body": {"storage": {"value": " "}}}]}
            ),
            "invalid_output",
        ),
        (
            json_bytes({"results": [{"id": "c1", "body": {"value": "<p>Root</p>"}}]}),
            "invalid_output",
        ),
        (
            json_bytes(
                {
                    "results": [
                        {
                            "id": "c1",
                            "body": {"storage": {"value": "<p>Root</p>"}},
                            "children": {
                                "comment": {
                                    "results": [{"id": "c2", "type": "comment"}]
                                }
                            },
                        }
                    ]
                }
            ),
            "invalid_output",
        ),
        (
            json_bytes(
                {
                    "results": [
                        {
                            "id": "c1",
                            "type": "page",
                            "body": {"storage": {"value": "<p>Root</p>"}},
                        }
                    ]
                }
            ),
            "invalid_output",
        ),
        (
            json_bytes(
                {
                    "results": [
                        {
                            "id": "c1",
                            "body": {"storage": {"value": "<p>Root</p>"}},
                            "children": "bad",
                        }
                    ]
                }
            ),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_comments(raw)
        assert info.value.category == category


def test_page_label_rows_require_names() -> None:
    live.check_page_labels(json_bytes({"results": ["design", "other"]}))
    live.check_page_labels(
        json_bytes({"results": [{"prefix": "global", "name": "design", "id": "1"}]})
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"results": []}', "inconclusive"),
        (b'{"results": "bad"}', "invalid_output"),
        (b'{"results": [1]}', "invalid_output"),
        (json_bytes({"results": [{"id": "1"}]}), "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_labels(raw)
        assert info.value.category == category


def test_live_failures_hide_sentinels_under_showlocals(tmp_path: Path) -> None:
    input_sentinel = "PRIVATE-999999"
    output_sentinel = "PRIVATE-API-OUTPUT-7f3a"
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    regression = tmp_path / "test_live_showlocals_regression.py"
    regression.write_text(
        f'''import importlib.util

INPUT_SENTINEL = "{input_sentinel}"
OUTPUT_SENTINEL = "{output_sentinel}"
SCRIPT = {str(SCRIPT)!r}
spec = importlib.util.spec_from_file_location(
    "live_showlocals_regression", SCRIPT
)
assert spec is not None and spec.loader is not None
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def test_missing_prerequisite(monkeypatch):
    monkeypatch.delenv("ATLAWIRE_LIVE_JIRA_ISSUE", raising=False)
    live.test_jira_issue_remote_links_return_objects()


def test_expected_failure(monkeypatch):
    def no_rows(*args, **kwargs):
        raise live.LiveCheckError("inconclusive")

    monkeypatch.setattr(live, "run_cli", no_rows)
    live.test_jira_priorities_are_readable()


def test_unexpected_failure(monkeypatch):
    monkeypatch.setenv("ATLAWIRE_LIVE_JIRA_ISSUE", INPUT_SENTINEL)

    def boom(*args, **kwargs):
        raise RuntimeError(OUTPUT_SENTINEL)

    monkeypatch.setattr(live, "run_cli", boom)
    live.test_jira_issue_remote_links_return_objects()


def test_new_entrypoint_failure(monkeypatch):
    monkeypatch.setenv("ATLAWIRE_LIVE_JIRA_ISSUE", INPUT_SENTINEL)

    def boom(*args, **kwargs):
        raise RuntimeError(OUTPUT_SENTINEL)

    monkeypatch.setattr(live, "run_cli", boom)
    live.test_read_operation_jira_votes_use_known_issue()
''',
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "PYTEST_ADDOPTS": "",
        "PYTHONUTF8": "1",
    }
    for name in ("SYSTEMDRIVE", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(name)
        if value:
            environment[name] = value

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "--showlocals",
            "-q",
            "-p",
            "no:cacheprovider",
            str(regression),
        ],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert input_sentinel.encode() not in combined
    assert output_sentinel.encode() not in combined
    assert b"Traceback" not in combined
    assert b"RuntimeError" not in combined
    for category in (b"missing_fixture", b"inconclusive", b"unexpected_error"):
        assert category in combined


def test_page_history_requires_known_content() -> None:
    live.check_page_history(
        json_bytes(
            {
                "latest": True,
                "createdDate": "2020-01-01T00:00:00.000Z",
                "createdBy": {"username": "ada"},
            }
        )
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b"{}", "inconclusive"),
        (b'{"unknown": 1}', "inconclusive"),
        (b'{"latest": "yes"}', "invalid_output"),
        (b'{"createdDate": ""}', "invalid_output"),
        (b'{"lastUpdated": []}', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_history(raw)
        assert info.value.category == category


def test_page_version_and_space_sources_use_known_page() -> None:
    page = json_bytes(
        {
            "id": PAGE,
            "version": {"number": 7},
            "space": {"key": "DEMO"},
        }
    )

    assert live.check_page_version_source(page, PAGE) == 7
    assert live.check_page_space_source(page, PAGE) == "DEMO"

    assert (
        live.check_page_version_source(
            json_bytes({"id": PAGE, "version": {"number": 1}}), PAGE
        )
        == 1
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (json_bytes({"id": "999", "version": {"number": 7}}), "oracle_mismatch"),
        (json_bytes({"id": PAGE}), "inconclusive"),
        (json_bytes({"id": PAGE, "version": {"number": 0}}), "inconclusive"),
        (json_bytes({"id": PAGE, "version": {"number": True}}), "inconclusive"),
        (json_bytes({"id": PAGE, "version": {"number": "7"}}), "inconclusive"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_version_source(raw, PAGE)
        assert info.value.category == category

    for raw, category in (
        (b"[]", "invalid_output"),
        (json_bytes({"id": "999", "space": {"key": "DEMO"}}), "oracle_mismatch"),
        (json_bytes({"id": PAGE}), "inconclusive"),
        (json_bytes({"id": PAGE, "space": {}}), "inconclusive"),
        (json_bytes({"id": PAGE, "space": {"key": "../bad"}}), "inconclusive"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_space_source(raw, PAGE)
        assert info.value.category == category


def test_page_version_validates_identity_version_status_and_body() -> None:
    version = {
        "id": PAGE,
        "type": "page",
        "status": "historical",
        "version": {"number": 7},
        "body": {"storage": {"value": "<p>Old</p>"}},
    }
    live.check_page_version(json_bytes(version), PAGE, 7)

    for patch, category in (
        ({"id": "999"}, "oracle_mismatch"),
        ({"type": "attachment"}, "invalid_output"),
        ({"version": None}, "invalid_output"),
        ({"version": {"number": True}}, "invalid_output"),
        ({"version": {"number": 8}}, "oracle_mismatch"),
        ({"status": "current"}, "invalid_output"),
        ({"body": {"storage": {"value": " "}}}, "invalid_output"),
        ({"body": None}, "invalid_output"),
    ):
        raw = json_bytes({**version, **patch})
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_version(raw, PAGE, 7)
        assert info.value.category == category


def test_page_url_requires_https_without_credentials() -> None:
    live.check_page_url(b"https://wiki.example.invalid/display/DEMO/Page\n")
    live.check_page_url(b"https://wiki.example.invalid/x?pageId=555#section\r\n")

    for raw in (
        b"",
        b"http://wiki.example.invalid/display/DEMO/Page\n",
        b"https://user:pass@wiki.example.invalid/display/DEMO\n",
        b"/display/DEMO/Page\n",
        b"https://wiki.example.invalid/display/DEMO Page\n",
        b"https://wiki.example.invalid/display/DEMO\n\n",
        b"\xff",
        b"https://wiki.example.invalid:0/display/DEMO\n",
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_page_url(raw)
        assert info.value.category == "invalid_output"


def test_edit_meta_requires_a_nonempty_field_map() -> None:
    live.check_edit_meta(json_bytes({"fields": {"summary": {"name": "Summary"}}}))

    for raw, category in (
        (b"[]", "invalid_output"),
        (b"{}", "invalid_output"),
        (b'{"fields": {}}', "inconclusive"),
        (b'{"fields": []}', "invalid_output"),
        (b'{"fields": {"summary": "bad"}}', "invalid_output"),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_edit_meta(raw)
        assert info.value.category == category


def test_create_meta_requires_known_project_and_shapes() -> None:
    live.check_create_meta(
        json_bytes(
            {
                "projects": [
                    {
                        "key": "DEMO",
                        "issuetypes": [{"fields": {"summary": {"name": "Summary"}}}],
                    }
                ]
            }
        ),
        "DEMO",
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"projects": []}', "inconclusive"),
        (b'{"projects": "bad"}', "invalid_output"),
        (json_bytes({"projects": [{"key": "OTHER"}]}), "oracle_mismatch"),
        (
            json_bytes({"projects": [{"key": "DEMO", "issuetypes": "bad"}]}),
            "invalid_output",
        ),
        (
            json_bytes({"projects": [{"key": "DEMO", "issuetypes": [{"fields": []}]}]}),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_create_meta(raw, "DEMO")
        assert info.value.category == category


def test_transition_fields_require_shaped_transitions() -> None:
    live.check_transition_fields(
        json_bytes(
            {
                "transitions": [
                    {
                        "id": "31",
                        "name": "Start",
                        "to": {"name": "In Progress"},
                        "fields": {"resolution": {"name": "Resolution"}},
                    }
                ]
            }
        )
    )

    for raw, category in (
        (b"[]", "invalid_output"),
        (b'{"transitions": []}', "inconclusive"),
        (b'{"transitions": "bad"}', "invalid_output"),
        (json_bytes({"transitions": [{"name": "Start"}]}), "invalid_output"),
        (json_bytes({"transitions": [{"id": "31"}]}), "invalid_output"),
        (
            json_bytes({"transitions": [{"id": "31", "name": "Start", "to": 1}]}),
            "invalid_output",
        ),
        (
            json_bytes({"transitions": [{"id": "31", "name": "Start", "fields": []}]}),
            "invalid_output",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            live.check_transition_fields(raw)
        assert info.value.category == category


def test_whoami_requires_three_successful_entries() -> None:
    good = {
        "confluence": {
            "ok": True,
            "identity": {"username": "ada", "displayName": "Ada"},
        },
        "jira": {"ok": True, "identity": {"name": "ada", "displayName": "Ada"}},
        "bitbucket": {"ok": True, "authenticated": True},
    }
    live.check_whoami(json_bytes(good))

    cases = (
        (
            {key: value for key, value in good.items() if key != "jira"},
            "invalid_output",
        ),
        ({**good, "jira": {"ok": False}}, "oracle_mismatch"),
        ({**good, "confluence": {"ok": True}}, "invalid_output"),
        ({**good, "bitbucket": {"ok": True}}, "oracle_mismatch"),
    )
    for payload, category in cases:
        with pytest.raises(live.LiveCheckError) as info:
            live.check_whoami(json_bytes(payload))
        assert info.value.category == category


def test_read_operation_response_validators_use_known_identity() -> None:
    live.check_jira_project(json_bytes({"key": "DEMO"}), "DEMO")
    live.check_jira_votes(
        json_bytes({"votes": 2, "hasVoted": True, "voters": [{"name": "ada"}]})
    )
    live.check_jira_watchers(
        json_bytes({"watchCount": 1, "watchers": [{"name": "ada"}]})
    )
    live.check_bitbucket_project(json_bytes({"key": "DEMO"}), "DEMO")
    live.check_bitbucket_repository(
        json_bytes({"slug": "widgets", "project": {"key": "DEMO"}}),
        "DEMO",
        "widgets",
    )
    live.check_confluence_space(json_bytes({"key": "DEMO"}), "DEMO")

    for call, category in (
        (
            lambda: live.check_jira_project(b'{"key": "OTHER"}', "DEMO"),
            "oracle_mismatch",
        ),
        (
            lambda: live.check_jira_votes(
                b'{"votes": -1, "hasVoted": false, "voters": []}'
            ),
            "invalid_output",
        ),
        (
            lambda: live.check_jira_votes(
                b'{"votes": 1, "hasVoted": false, "voters": "bad"}'
            ),
            "invalid_output",
        ),
        (
            lambda: live.check_jira_watchers(b'{"watchCount": true, "watchers": []}'),
            "invalid_output",
        ),
        (
            lambda: live.check_bitbucket_project(b'{"key": "OTHER"}', "DEMO"),
            "oracle_mismatch",
        ),
        (
            lambda: live.check_bitbucket_repository(
                b'{"slug": "other", "project": {"key": "DEMO"}}', "DEMO", "widgets"
            ),
            "oracle_mismatch",
        ),
        (
            lambda: live.check_confluence_space(b'{"key": "OTHER"}', "DEMO"),
            "oracle_mismatch",
        ),
    ):
        with pytest.raises(live.LiveCheckError) as info:
            call()
        assert info.value.category == category


def test_read_operation_arguments_are_limited_to_fixed_values() -> None:
    assert live._valid_read_operation_arguments(
        "jira.project.get", '{"projectIdOrKey":"DEMO"}'
    )
    assert live._valid_read_operation_arguments(
        "jira.issue.votes", '{"issueIdOrKey":"DEMO-42"}'
    )
    assert live._valid_read_operation_arguments(
        "jira.issue.watchers", '{"issueIdOrKey":"DEMO-42"}'
    )
    assert live._valid_read_operation_arguments(
        "bitbucket.project.get", '{"projectKey":"DEMO"}'
    )
    assert live._valid_read_operation_arguments(
        "bitbucket.repository.get",
        '{"projectKey":"DEMO","repositorySlug":"widgets"}',
    )
    assert live._valid_read_operation_arguments(
        "confluence.space.get", '{"spaceKey":"DEMO"}'
    )

    for operation_id, raw in (
        ("jira.unknown", '{"issueIdOrKey":"DEMO-42"}'),
        ("jira.issue.votes", "[]"),
        ("jira.issue.votes", '{"issueIdOrKey":"DEMO-42","extra":"x"}'),
        ("jira.issue.votes", '{"issueIdOrKey":"--help"}'),
        (
            "jira.issue.votes",
            '{"issueIdOrKey":"DEMO-42","issueIdOrKey":"DEMO-43"}',
        ),
        ("jira.project.get", '{"projectIdOrKey":"https://evil.invalid"}'),
        (
            "bitbucket.repository.get",
            '{"projectKey":"DEMO","repositorySlug":"widgets","method":"POST"}',
        ),
        ("confluence.space.get", '{"spaceKey":"../bad"}'),
    ):
        assert not live._valid_read_operation_arguments(operation_id, raw)


def test_required_fixtures_reuse_existing_live_names() -> None:
    existing = (PROJECT_ROOT / "checks" / "live_read_only.py").read_text("utf-8")

    for name in (
        "ATLAWIRE_LIVE_JIRA_ISSUE",
        "ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID",
        "ATLAWIRE_LIVE_BITBUCKET_REPO",
        "ATLAWIRE_LIVE_BITBUCKET_PR_ID",
        "ATLAWIRE_LIVE_BITBUCKET_FILE_PATH",
        "ATLAWIRE_LIVE_BITBUCKET_FILE_REF",
    ):
        assert f'"{name}"' in existing


def test_live_checks_stay_outside_default_testpaths() -> None:
    import tomllib

    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert Path(live.__file__).resolve().parent == PROJECT_ROOT / "checks"

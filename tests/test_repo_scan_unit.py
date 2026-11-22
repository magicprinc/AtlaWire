"""Unit and failure-contract tests for the extension inventory walk."""

import threading
from concurrent.futures import ALL_COMPLETED, Future, ThreadPoolExecutor
from contextlib import nullcontext
from queue import Empty, Queue
from typing import ClassVar, Protocol, cast

import pytest

from atlawire import bitbucket, repo_scan
from atlawire.http import AtlaWireError
from atlawire.repo_scan import ExtensionMatch, scan_repository_extensions

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"

type Call = tuple[str, str, str, str, int, bool]


class ListingApi(Protocol):
    """The three listing methods the extension walk consumes."""

    def list_projects(
        self,
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]: ...

    def list_repositories(
        self,
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]: ...

    def list_repository_files(
        self,
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]: ...


def project_row(key: str, *, url: str | None = None) -> bitbucket.Project:
    return bitbucket.Project(key=key, name=None, public=None, description=None, url=url)


def repository_row(slug: str) -> bitbucket.Repository:
    return bitbucket.Repository(slug=slug, name=None, state=None, public=None)


def install_tree(
    monkeypatch: pytest.MonkeyPatch,
    *,
    projects: list[str],
    repositories: dict[str, list[str]],
    files: dict[str, list[str]],
) -> list[Call]:
    """Install a synthetic project tree and record every API invocation."""
    calls: list[Call] = []

    def fake_projects(
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        calls.append(("projects", base_url, "", token, max_pages, allow_http_loopback))
        return [project_row(key) for key in projects]

    def fake_repositories(
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        calls.append(
            ("repositories", base_url, project, token, max_pages, allow_http_loopback)
        )
        return [repository_row(slug) for slug in repositories[project]]

    def fake_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        calls.append(("files", base_url, repo, token, max_pages, allow_http_loopback))
        return files[repo]

    monkeypatch.setattr(repo_scan, "list_projects", fake_projects)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", fake_files)
    return calls


def install_api(monkeypatch: pytest.MonkeyPatch, api: ListingApi) -> None:
    """Install an object exposing the three listing methods used by the walk."""
    monkeypatch.setattr(repo_scan, "list_projects", api.list_projects)
    monkeypatch.setattr(repo_scan, "list_repositories", api.list_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", api.list_repository_files)


class ObservedExecutor(ThreadPoolExecutor):
    """Thread pool that records future outcomes and shutdown entry arguments."""

    instances: ClassVar[list[object]] = []

    def __init__(self, max_workers: int) -> None:
        super().__init__(max_workers=max_workers)
        self.failure_seen = threading.Event()
        self.shutdown_entered = threading.Event()
        self.errors: list[BaseException] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []
        self.lock = threading.Lock()
        ObservedExecutor.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    def submit(self, fn, /, *args, **kwargs):
        future = super().submit(fn, *args, **kwargs)

        def observe(done: Future[object]) -> None:
            if done.cancelled():
                return
            error = done.exception()
            if error is not None:
                with self.lock:
                    self.errors.append(error)
                self.failure_seen.set()

        future.add_done_callback(observe)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self.lock:
            self.shutdown_calls.append((wait, cancel_futures))
        self.shutdown_entered.set()
        super().shutdown(wait=wait, cancel_futures=cancel_futures)


def forbid_io(*args: object, **kwargs: object) -> None:
    raise AssertionError("input validation must precede I/O")


def test_inventory_returns_sorted_complete_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_tree(
        monkeypatch,
        projects=["ZETA", "ALPHA"],
        repositories={
            "ZETA": ["z-tools", "z-docs"],
            "ALPHA": ["a-scripts", "a-extra"],
        },
        files={
            "ZETA/z-tools": ["a.py", "b.PY", "notes.txt"],
            "ZETA/z-docs": ["guide.md"],
            "ALPHA/a-scripts": ["main.py"],
            "ALPHA/a-extra": ["x.py", "y.py"],
        },
    )
    expected: list[ExtensionMatch] = [
        {
            "project": "ALPHA",
            "repository": "a-extra",
            "files": 2,
            "matched": 2,
            "sample": ["x.py", "y.py"],
        },
        {
            "project": "ZETA",
            "repository": "z-tools",
            "files": 3,
            "matched": 2,
            "sample": ["a.py", "b.PY"],
        },
        {
            "project": "ALPHA",
            "repository": "a-scripts",
            "files": 1,
            "matched": 1,
            "sample": ["main.py"],
        },
    ]

    assert (
        scan_repository_extensions(BASE, ".py", token=TOKEN, workers=2, max_pages=10)
        == expected
    )
    # A second run must not depend on worker completion order.
    assert (
        scan_repository_extensions(BASE, "PY", token=TOKEN, workers=2, max_pages=10)
        == expected
    )
    assert {call[2] for call in calls if call[0] == "files"} == {
        "ZETA/z-tools",
        "ZETA/z-docs",
        "ALPHA/a-scripts",
        "ALPHA/a-extra",
    }
    assert all(call[1] == BASE and call[3] == TOKEN for call in calls)
    assert all(call[4] == 10 and call[5] is False for call in calls)


@pytest.mark.parametrize("extension", [".py", "py", ".PY", "Py"])
def test_extension_forms_match_case_insensitively(
    monkeypatch: pytest.MonkeyPatch, extension: str
) -> None:
    install_tree(
        monkeypatch,
        projects=["P"],
        repositories={"P": ["r"]},
        files={"P/r": ["A.PY", "b.py", "c.txt"]},
    )

    assert scan_repository_extensions(BASE, extension, token=TOKEN, workers=1) == [
        {
            "project": "P",
            "repository": "r",
            "files": 3,
            "matched": 2,
            "sample": ["A.PY", "b.py"],
        }
    ]


def test_sample_keeps_first_five_matching_paths_in_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [f"f{number}.py" for number in range(7)] + ["README.md"]
    install_tree(
        monkeypatch,
        projects=["P"],
        repositories={"P": ["r"]},
        files={"P/r": paths},
    )

    rows = scan_repository_extensions(BASE, ".py", token=TOKEN, workers=1)

    assert rows[0]["files"] == 8
    assert rows[0]["matched"] == 7
    assert rows[0]["sample"] == paths[:5]


def test_no_visible_projects_returns_empty_without_file_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_tree(monkeypatch, projects=[], repositories={}, files={})

    assert scan_repository_extensions(BASE, ".py", token=TOKEN, max_pages=5) == []
    assert calls == [("projects", BASE, "", TOKEN, 5, False)]


def test_repository_listing_failure_returns_nothing_and_starts_no_file_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("sanitized repository listing failure")
    calls: list[object] = []

    def fake_projects(
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        calls.append("projects")
        return [project_row("P1"), project_row("P2")]

    def fake_repositories(
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        calls.append(("repositories", project))
        if project == "P2":
            raise failure
        return [repository_row("one")]

    def fake_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        calls.append(("files", repo))
        return ["a.py"]

    monkeypatch.setattr(repo_scan, "list_projects", fake_projects)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", fake_files)

    with pytest.raises(AtlaWireError) as raised:
        scan_repository_extensions(BASE, ".py", token=TOKEN, workers=2)

    assert raised.value is failure
    assert calls == ["projects", ("repositories", "P1"), ("repositories", "P2")]


def test_project_scope_uses_only_the_requested_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_repositories(
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        calls.append(("repositories", project))
        assert project == "~scoped"
        return [repository_row("r1"), repository_row("r2")]

    def fake_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        calls.append(("files", repo))
        return {
            "~scoped/r1": ["a.py", "notes.txt"],
            "~scoped/r2": ["b.PY"],
        }[repo]

    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", fake_files)

    rows = scan_repository_extensions(
        BASE, ".py", token=TOKEN, workers=1, max_pages=5, project="~scoped"
    )

    assert rows == [
        {
            "project": "~scoped",
            "repository": "r1",
            "files": 2,
            "matched": 1,
            "sample": ["a.py"],
        },
        {
            "project": "~scoped",
            "repository": "r2",
            "files": 1,
            "matched": 1,
            "sample": ["b.PY"],
        },
    ]
    assert calls == [
        ("repositories", "~scoped"),
        ("files", "~scoped/r1"),
        ("files", "~scoped/r2"),
    ]


def test_project_scope_failure_returns_nothing_and_lists_no_unrelated_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("sanitized scoped failure")
    calls: list[tuple[str, str]] = []

    def fake_repositories(
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        calls.append(("repositories", project))
        return [repository_row("first"), repository_row("second")]

    def fake_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        calls.append(("files", repo))
        if repo == "SCOPED/first":
            return ["one.py", "two.py"]
        if repo == "SCOPED/second":
            raise failure
        raise AssertionError(f"unexpected repository: {repo}")

    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", fake_files)

    with pytest.raises(AtlaWireError) as raised:
        scan_repository_extensions(
            BASE, ".py", token=TOKEN, workers=1, max_pages=5, project="SCOPED"
        )

    assert raised.value is failure
    assert calls == [
        ("repositories", "SCOPED"),
        ("files", "SCOPED/first"),
        ("files", "SCOPED/second"),
    ]


@pytest.mark.parametrize("project", ["PROJ", "PROJ.name-1_2", "~scoped", "A_1"])
def test_project_scope_accepts_valid_bitbucket_key_forms(
    monkeypatch: pytest.MonkeyPatch, project: str
) -> None:
    seen: list[str] = []

    def fake_repositories(
        base_url: str,
        key: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        seen.append(key)
        return []

    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", forbid_io)

    assert scan_repository_extensions(
        BASE, ".py", token=TOKEN, project=project
    ) == []
    assert seen == [project]


@pytest.mark.parametrize(
    "project", ["", "BAD/KEY", " bad", "bad ", "~", "..", "A\tB", True, 7]
)
def test_invalid_project_key_is_rejected_before_io(
    monkeypatch: pytest.MonkeyPatch, project: object
) -> None:
    monkeypatch.setattr(repo_scan, "bearer_session", forbid_io)
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repositories", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repository_files", forbid_io)

    with pytest.raises(AtlaWireError, match="project key"):
        scan_repository_extensions(
            BASE, ".py", token=TOKEN, project=cast(str, project)
        )


@pytest.mark.parametrize(
    "extension",
    ["", ".", "..py", " py", "py ", "py/py", "py\\py", "p\ty", "p\ny", True, None, 7],
)
def test_invalid_extension_is_rejected_before_io(
    monkeypatch: pytest.MonkeyPatch, extension: object
) -> None:
    monkeypatch.setattr(repo_scan, "bearer_session", forbid_io)
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repositories", forbid_io)
    monkeypatch.setattr(repo_scan, "list_repository_files", forbid_io)

    with pytest.raises(AtlaWireError, match="extension"):
        scan_repository_extensions(BASE, cast(str, extension), token=TOKEN)


@pytest.mark.parametrize("workers", [0, -1, 9, 1000, True, False, 1.5, "2", None])
def test_invalid_worker_count_is_rejected_before_io(
    monkeypatch: pytest.MonkeyPatch, workers: object
) -> None:
    monkeypatch.setattr(repo_scan, "bearer_session", forbid_io)
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)

    with pytest.raises(AtlaWireError, match="worker count"):
        scan_repository_extensions(BASE, ".py", token=TOKEN, workers=cast(int, workers))


@pytest.mark.parametrize("max_pages", [0, -1, 1001, True, False, 2.5, "10", None])
def test_invalid_page_budget_is_rejected_before_io(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    monkeypatch.setattr(repo_scan, "bearer_session", forbid_io)
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)

    with pytest.raises(AtlaWireError, match="page limit"):
        scan_repository_extensions(
            BASE, ".py", token=TOKEN, max_pages=cast(int, max_pages)
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "http://bitbucket.example.invalid/scm",
        "ftp://bitbucket.example.invalid/scm",
        "https://user:password@bitbucket.example.invalid/scm",
        "https://bitbucket.example.invalid/scm?query=1",
    ],
)
def test_invalid_base_url_is_rejected_before_io(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    monkeypatch.setattr(repo_scan, "bearer_session", forbid_io)
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)

    with pytest.raises(AtlaWireError):
        scan_repository_extensions(base_url, ".py", token=TOKEN)


@pytest.mark.parametrize("token", ["", "bad token", "ü", None, 7])
def test_invalid_token_is_rejected_before_enumeration(
    monkeypatch: pytest.MonkeyPatch, token: object
) -> None:
    monkeypatch.setattr(repo_scan, "list_projects", forbid_io)

    with pytest.raises(AtlaWireError, match="bearer token"):
        scan_repository_extensions(BASE, ".py", token=cast(str, token))


def test_every_request_uses_the_supplied_destination_and_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Call] = []

    def fake_projects(
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        calls.append(("projects", base_url, "", token, max_pages, allow_http_loopback))
        return [project_row("P", url="https://evil.invalid/never-followed")]

    def fake_repositories(
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        calls.append(
            ("repositories", base_url, project, token, max_pages, allow_http_loopback)
        )
        return [repository_row("slug")]

    def fake_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        calls.append(("files", base_url, repo, token, max_pages, allow_http_loopback))
        return ["x.py"]

    monkeypatch.setattr(repo_scan, "list_projects", fake_projects)
    monkeypatch.setattr(repo_scan, "list_repositories", fake_repositories)
    monkeypatch.setattr(repo_scan, "list_repository_files", fake_files)

    rows = scan_repository_extensions(
        "http://127.0.0.1:9/scm/",
        ".py",
        token=TOKEN,
        workers=1,
        max_pages=7,
        allow_http_loopback=True,
    )

    assert rows == [
        {
            "project": "P",
            "repository": "slug",
            "files": 1,
            "matched": 1,
            "sample": ["x.py"],
        }
    ]
    assert calls == [
        ("projects", "http://127.0.0.1:9/scm", "", TOKEN, 7, True),
        ("repositories", "http://127.0.0.1:9/scm", "P", TOKEN, 7, True),
        ("files", "http://127.0.0.1:9/scm", "P/slug", TOKEN, 7, True),
    ]


def test_default_worker_count_is_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[int] = []

    class CapturingExecutor(ThreadPoolExecutor):
        def __init__(self, max_workers: int) -> None:
            super().__init__(max_workers=max_workers)
            captured.append(max_workers)

    install_tree(
        monkeypatch,
        projects=["P"],
        repositories={"P": ["r"]},
        files={"P/r": ["notes.txt"]},
    )
    monkeypatch.setattr(repo_scan, "ThreadPoolExecutor", CapturingExecutor)

    assert scan_repository_extensions(BASE, ".py", token=TOKEN) == []
    assert captured == [8]


class SuccessThenFailureApi:
    """Succeed in one worker only after another worker has already failed."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.success_done = threading.Event()
        self.started: list[str] = []
        self.threads: list[threading.Thread] = []
        self.lock = threading.Lock()

    def list_projects(
        self,
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        return [project_row("P")]

    def list_repositories(
        self,
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        return [repository_row("other"), repository_row("success")]

    def list_repository_files(
        self,
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        slug = repo.split("/", 1)[1]
        with self.lock:
            self.started.append(slug)
            self.threads.append(threading.current_thread())
        if slug == "success":
            self.success_done.set()
            return ["a.py", "b.py", "notes.txt"]
        if slug == "other":
            if not self.success_done.wait(timeout=5):
                raise AssertionError("successful worker did not finish")
            raise self.failure
        raise AssertionError(f"unexpected repository: {repo}")


def test_worker_failure_after_another_success_propagates_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("sanitized repository failure")
    api = SuccessThenFailureApi(failure)
    install_api(monkeypatch, api)

    with pytest.raises(AtlaWireError) as raised:
        scan_repository_extensions(BASE, "py", token=TOKEN, workers=2, max_pages=5)

    assert raised.value is failure
    assert sorted(api.started) == ["other", "success"]
    assert len(api.threads) == 2
    assert all(thread is not threading.current_thread() for thread in api.threads)
    assert all(not thread.is_alive() for thread in api.threads)


class SequentialMatchThenFailureApi:
    """Match in the first repository, then fail while scanning the second."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.started: list[str] = []
        self.completed: list[str] = []
        self.threads: list[threading.Thread] = []
        self.lock = threading.Lock()

    def list_projects(
        self,
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        return [project_row("P")]

    def list_repositories(
        self,
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        return [repository_row("first"), repository_row("second")]

    def list_repository_files(
        self,
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        slug = repo.split("/", 1)[1]
        with self.lock:
            self.started.append(slug)
            self.threads.append(threading.current_thread())
        if slug == "first":
            with self.lock:
                self.completed.append(slug)
            return ["one.py", "two.py", "notes.txt"]
        if slug == "second":
            raise self.failure
        raise AssertionError(f"unexpected repository: {repo}")


def test_single_worker_discards_a_completed_match_on_later_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = AtlaWireError("sanitized second repository failure")
    api = SequentialMatchThenFailureApi(failure)
    install_api(monkeypatch, api)

    with pytest.raises(AtlaWireError) as raised:
        scan_repository_extensions(BASE, ".py", token=TOKEN, workers=1, max_pages=5)

    assert raised.value is failure
    assert api.started == ["first", "second"]
    assert api.completed == ["first"]
    assert len(api.threads) == 2
    assert api.threads[0] is api.threads[1]
    assert all(not thread.is_alive() for thread in api.threads)
    captured = capsys.readouterr()
    assert captured.out == ""


class OverlappingApi:
    """Block one worker, fail another, and expose the never-submitted slot."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.blocked_started = threading.Event()
        self.release = threading.Event()
        self.never_started = threading.Event()
        self.started: list[str] = []
        self.threads: list[threading.Thread] = []
        self.worker_threads: dict[str, threading.Thread] = {}
        self.lock = threading.Lock()

    def list_projects(
        self,
        base_url: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Project]:
        return [project_row("P")]

    def list_repositories(
        self,
        base_url: str,
        project: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[bitbucket.Repository]:
        return [
            repository_row("blocked"),
            repository_row("failure"),
            repository_row("never"),
        ]

    def list_repository_files(
        self,
        base_url: str,
        repo: str,
        *,
        token: str,
        max_pages: int,
        allow_http_loopback: bool,
    ) -> list[str]:
        slug = repo.split("/", 1)[1]
        with self.lock:
            self.started.append(slug)
            self.threads.append(threading.current_thread())
            self.worker_threads[slug] = threading.current_thread()
        if slug == "blocked":
            self.blocked_started.set()
            if not self.release.wait(timeout=10):
                raise AssertionError("blocked worker was not released")
            return ["blocked.py"]
        if slug == "failure":
            if not self.blocked_started.wait(timeout=5):
                raise AssertionError("blocked worker did not start")
            raise self.failure
        if slug == "never":
            self.never_started.set()
            return ["never.py"]
        raise AssertionError(f"unexpected repository: {repo}")


def test_failure_awaits_blocked_worker_and_drops_queued_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("sanitized repository failure")
    api = OverlappingApi(failure)
    install_api(monkeypatch, api)
    ObservedExecutor.reset()
    outcome: Queue[tuple[str, object]] = Queue()
    coordinator_waiting = threading.Event()
    wait_calls = 0
    failure_returned = False
    real_wait = repo_scan.wait

    def tracked_wait(fs, *, timeout=None, return_when=ALL_COMPLETED):
        """Signal the coordinator's first wait after the failure is observed."""
        nonlocal wait_calls, failure_returned
        wait_calls += 1
        if failure_returned:
            assert any(not future.done() for future in fs)
            coordinator_waiting.set()
        done, not_done = real_wait(fs, timeout=timeout, return_when=return_when)
        for future in done:
            if not future.cancelled() and future.exception() is failure:
                failure_returned = True
        return done, not_done

    def invoke() -> None:
        try:
            outcome.put(
                (
                    "return",
                    scan_repository_extensions(
                        BASE, "py", token=TOKEN, workers=2, max_pages=5
                    ),
                )
            )
        except AtlaWireError as exc:
            outcome.put(("exception", exc))

    monkeypatch.setattr(repo_scan, "wait", tracked_wait)
    monkeypatch.setattr(repo_scan, "ThreadPoolExecutor", ObservedExecutor)
    caller = threading.Thread(target=invoke, daemon=True)
    caller.start()
    try:
        assert api.blocked_started.wait(timeout=5)
        executor = cast(ObservedExecutor, ObservedExecutor.instances[0])
        assert executor.failure_seen.wait(timeout=5)
        assert coordinator_waiting.wait(timeout=5)
        assert wait_calls == 2
        assert executor.shutdown_calls == []
        assert caller.is_alive()
        assert api.worker_threads["blocked"].is_alive()
        with pytest.raises(Empty):
            outcome.get_nowait()
    finally:
        api.release.set()
        caller.join(timeout=10)

    assert not caller.is_alive()
    assert outcome.get_nowait() == ("exception", failure)
    assert wait_calls == 2
    assert executor.shutdown_entered.is_set()
    assert executor.shutdown_calls == [(True, True)]
    assert executor.errors == [failure]
    assert sorted(api.started) == ["blocked", "failure"]
    assert not api.never_started.is_set()
    assert len(api.threads) == 2
    assert all(not thread.is_alive() for thread in api.threads)


def test_successful_later_pages_for_projects_repositories_and_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_url = f"{BASE}/rest/api/1.0/projects"
    p1_repositories_url = f"{projects_url}/P1/repos"
    p2_repositories_url = f"{projects_url}/P2/repos"
    first_files_url = f"{p1_repositories_url}/r1/files"
    second_files_url = f"{p1_repositories_url}/r2/files"
    third_files_url = f"{p2_repositories_url}/r3/files"
    pages: dict[tuple[str, int], object] = {
        (projects_url, 0): {
            "values": [{"key": "P1"}],
            "isLastPage": False,
            "nextPageStart": 1,
        },
        (projects_url, 1): {
            "values": [{"key": "P2"}],
            "isLastPage": True,
        },
        (p1_repositories_url, 0): {
            "values": [{"slug": "r1"}],
            "isLastPage": False,
            "nextPageStart": 2,
        },
        (p1_repositories_url, 2): {
            "values": [{"slug": "r2"}],
            "isLastPage": True,
        },
        (p2_repositories_url, 0): {
            "values": [{"slug": "r3"}],
            "isLastPage": True,
        },
        (first_files_url, 0): {
            "values": ["a.py"],
            "isLastPage": False,
            "nextPageStart": 5,
        },
        (first_files_url, 5): {
            "values": ["b.py"],
            "isLastPage": True,
        },
        (second_files_url, 0): {
            "values": ["notes.txt"],
            "isLastPage": True,
        },
        (third_files_url, 0): {
            "values": ["c.PY"],
            "isLastPage": True,
        },
    }
    seen: list[tuple[str, int, int]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        start = cast(int, params["start"])
        seen.append((url, start, cast(int, params["limit"])))
        value = pages[(url, start)]
        if isinstance(value, BaseException):
            raise value
        return cast(dict[str, object], value)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    rows = scan_repository_extensions(BASE, ".py", token=TOKEN, workers=1, max_pages=10)
    assert rows == [
        {
            "project": "P1",
            "repository": "r1",
            "files": 2,
            "matched": 2,
            "sample": ["a.py", "b.py"],
        },
        {
            "project": "P2",
            "repository": "r3",
            "files": 1,
            "matched": 1,
            "sample": ["c.PY"],
        },
    ]
    assert seen == [
        (projects_url, 0, 100),
        (projects_url, 1, 100),
        (p1_repositories_url, 0, 100),
        (p1_repositories_url, 2, 100),
        (p2_repositories_url, 0, 100),
        (first_files_url, 0, 100),
        (first_files_url, 5, 100),
        (second_files_url, 0, 100),
        (third_files_url, 0, 100),
    ]


def test_later_file_page_failure_returns_no_partial_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("sanitized later page failure")
    projects_url = f"{BASE}/rest/api/1.0/projects"
    repositories_url = f"{projects_url}/P/repos"
    files_url = f"{repositories_url}/success/files"
    pages: dict[tuple[str, int], object] = {
        (projects_url, 0): {"values": [{"key": "P"}], "isLastPage": True},
        (repositories_url, 0): {
            "values": [{"slug": "success"}],
            "isLastPage": True,
        },
        (files_url, 0): {
            "values": ["a.py"],
            "isLastPage": False,
            "nextPageStart": 7,
        },
        (files_url, 7): failure,
    }
    seen: list[tuple[str, int, int]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        start = cast(int, params["start"])
        seen.append((url, start, cast(int, params["limit"])))
        value = pages[(url, start)]
        if isinstance(value, BaseException):
            raise value
        return cast(dict[str, object], value)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    with pytest.raises(AtlaWireError) as raised:
        scan_repository_extensions(BASE, "py", token=TOKEN, workers=2, max_pages=5)

    assert raised.value is failure
    assert seen == [
        (projects_url, 0, 100),
        (repositories_url, 0, 100),
        (files_url, 0, 100),
        (files_url, 7, 100),
    ]


def test_files_page_budget_exhaustion_returns_no_partial_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_url = f"{BASE}/rest/api/1.0/projects"
    repositories_url = f"{projects_url}/P/repos"
    files_url = f"{repositories_url}/success/files"
    pages: dict[tuple[str, int], object] = {
        (projects_url, 0): {"values": [{"key": "P"}], "isLastPage": True},
        (repositories_url, 0): {
            "values": [{"slug": "success"}],
            "isLastPage": True,
        },
        (files_url, 0): {
            "values": ["a.py"],
            "isLastPage": False,
            "nextPageStart": 100,
        },
    }
    seen: list[tuple[str, int, int]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        start = cast(int, params["start"])
        seen.append((url, start, cast(int, params["limit"])))
        value = pages[(url, start)]
        if isinstance(value, BaseException):
            raise value
        return cast(dict[str, object], value)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    with pytest.raises(AtlaWireError, match="page limit"):
        scan_repository_extensions(BASE, "py", token=TOKEN, workers=1, max_pages=1)

    assert seen == [
        (projects_url, 0, 100),
        (repositories_url, 0, 100),
        (files_url, 0, 100),
    ]

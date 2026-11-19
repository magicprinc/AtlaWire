import asyncio
import socket
import subprocess
import sys
import threading
from concurrent.futures import Future
from contextlib import contextmanager

import pytest
from aiohttp import web

from cosmic_ray.distribution.http import handle_mutate_and_test
from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import TestOutcome as Outcome
from cosmic_ray.work_item import WorkerOutcome


@contextmanager
def loopback_server(startup_hook=None, cleanup_hook=None, startup_timeout=10):
    loop = asyncio.new_event_loop()
    ready = Future()
    errors = []

    async def serve():
        app = web.Application()
        app.add_routes([web.post("/", handle_mutate_and_test)])
        if cleanup_hook is not None:
            app.on_cleanup.append(cleanup_hook)
        runner = web.AppRunner(app)
        try:
            await runner.setup()
            if startup_hook is not None:
                await startup_hook(app)
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            ready.set_result(f"http://127.0.0.1:{runner.addresses[0][1]}")
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    task = loop.create_task(serve())

    def run():
        try:
            loop.run_until_complete(task)
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            if not isinstance(exc, asyncio.CancelledError):
                errors.append(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=run, daemon=True)
    try:
        thread.start()
    except BaseException:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()
        raise
    try:
        yield ready.result(timeout=startup_timeout)
    finally:
        try:
            loop.call_soon_threadsafe(task.cancel)
        except RuntimeError:
            pass
        finally:
            thread.join(timeout=10)
            assert not thread.is_alive()
        if errors:
            raise errors[0]


@pytest.fixture
def loopback_worker():
    with loopback_server() as address:
        yield address


def test_loopback_server_cleans_up_after_startup_timeout():
    started = threading.Event()
    cancelled = threading.Event()
    cleaned = threading.Event()

    async def on_cleanup(_app):
        cleaned.set()

    async def block_startup(_app):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(TimeoutError):
        with loopback_server(startup_hook=block_startup, cleanup_hook=on_cleanup, startup_timeout=2):
            pytest.fail("startup should not complete")
    assert started.is_set()
    assert cancelled.is_set()
    assert cleaned.is_set()


WAIT_FOR_CONNECTION = """\
from pathlib import Path
import socket
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen()
listener.settimeout(20)
Path(__file__).with_name("child_started").write_text(str(listener.getsockname()[1]))
listener.accept()[0].close()
listener.close()
"""


def assert_child_stopped(tmp_path):
    port = int((tmp_path / "child_started").read_text())
    with socket.socket() as probe:
        probe.settimeout(1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_child_stopped_check_rejects_a_live_listener(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        (tmp_path / "child_started").write_text(str(listener.getsockname()[1]))
        with pytest.raises(AssertionError):
            assert_child_stopped(tmp_path)


def run_baseline(tmp_path, test_command, timeout=10, distributor="local", extra_config=""):
    (tmp_path / "subject.py").write_text("value = 1\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(
        f"""[cosmic-ray]
module-path = "subject.py"
timeout = {timeout}
excluded-modules = []
test-command = '{test_command}'

[cosmic-ray.distributor]
name = "{distributor}"
{extra_config}
""",
        encoding="utf-8",
    )
    session = tmp_path / "session.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cosmic_ray.cli",
            "--verbosity=INFO",
            "baseline",
            str(config),
            "--session-file",
            str(session),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    with use_db(session, WorkDB.Mode.open) as db:
        _, work_result = next(db.results)
    return result, work_result


@pytest.mark.parametrize(
    ("body", "timeout", "expected_exit", "expected_outcome"),
    [
        ("print('passed')", 10, 0, Outcome.SURVIVED),
        ("raise SystemExit(1)", 10, 1, Outcome.KILLED),
        (WAIT_FOR_CONNECTION, 5, 1, Outcome.KILLED),
    ],
)
def test_baseline_test_command_outcomes(tmp_path, body, timeout, expected_exit, expected_outcome):
    (tmp_path / "run_test.py").write_text(body + "\n", encoding="utf-8")
    result, work_result = run_baseline(tmp_path, f'"{sys.executable}" run_test.py', timeout)
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert work_result.worker_outcome == WorkerOutcome.NORMAL
    assert work_result.test_outcome == expected_outcome
    if timeout == 5:
        assert_child_stopped(tmp_path)
        assert work_result.output == "timeout"


def test_baseline_fails_when_test_command_cannot_start(tmp_path):
    result, work_result = run_baseline(tmp_path, "cosmic_ray_missing_baseline_executable_7319")
    assert work_result.test_outcome == Outcome.INCOMPETENT
    assert "FileNotFoundError" in work_result.output
    assert result.returncode != 0, result.stdout + result.stderr
    assert "Baseline failed." in result.stdout + result.stderr
    assert "FileNotFoundError" in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("case", "expected_exit", "expected_outcome", "expected_output"),
    [
        ("pass", 0, Outcome.SURVIVED, "remote test passed"),
        ("fail", 1, Outcome.KILLED, "remote test failed"),
        ("missing", 1, Outcome.INCOMPETENT, "FileNotFoundError"),
        ("timeout", 1, Outcome.KILLED, "timeout"),
    ],
)
def test_baseline_with_loopback_worker(
    tmp_path, loopback_worker, case, expected_exit, expected_outcome, expected_output
):
    script = tmp_path / "remote_test.py"
    bodies = {
        "pass": "print('remote test passed')",
        "fail": "print('remote test failed'); raise SystemExit(1)",
        "timeout": WAIT_FOR_CONNECTION,
    }
    if case == "missing":
        command = "cosmic_ray_missing_baseline_executable_7319"
    else:
        script.write_text(bodies[case] + "\n", encoding="utf-8")
        command = f'"{sys.executable}" "{script.as_posix()}"'

    result, work_result = run_baseline(
        tmp_path,
        command,
        timeout=5,
        distributor="http",
        extra_config=f'\n[cosmic-ray.distributor.http]\nworker-urls = ["{loopback_worker}"]',
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert work_result.worker_outcome == WorkerOutcome.NORMAL
    assert work_result.test_outcome == expected_outcome
    assert expected_output in work_result.output
    if case == "timeout":
        assert_child_stopped(tmp_path)
        assert work_result.output == "timeout"


def test_baseline_fails_when_http_worker_cannot_be_reached(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        result, work_result = run_baseline(
            tmp_path,
            "unused",
            distributor="http",
            extra_config=f'\n[cosmic-ray.distributor.http]\nworker-urls = ["http://127.0.0.1:{port}"]',
        )
    assert work_result.worker_outcome == WorkerOutcome.ABNORMAL
    assert work_result.test_outcome is None
    assert result.returncode != 0, result.stdout + result.stderr
    assert "Baseline failed." in result.stdout + result.stderr

"""Focused checks for the reusable killable regex helper."""

import json
import socket
import subprocess
import threading
from typing import cast

import pytest

from atlawire import regex_helper

TOKEN_VARIABLE = "ATLAWIRE_JIRA_TOKEN"
TOKEN = "fixture-comment-token"


def test_document_batch_uses_one_helper_and_keeps_inputs_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    created: list[object] = []

    class Process:
        returncode = 0

        def __init__(self, args: list[str], **kwargs: object) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

        def communicate(
            self, data: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            captured["input"] = data
            captured["timeout"] = timeout
            return b'{"matches": [true, false, true]}', b""

        def poll(self) -> int:
            return self.returncode

        def kill(self) -> None:
            raise AssertionError("kill must not be needed")

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def factory(args: list[str], **kwargs: object) -> Process:
        process = Process(args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(regex_helper.subprocess, "Popen", factory)
    monkeypatch.setenv(TOKEN_VARIABLE, TOKEN)
    documents = ["first body", "second body", "third body"]

    result = regex_helper.match_documents(
        documents, "needle", ignore_case=True, timeout_s=2.0
    )

    assert result == [True, False, True]
    assert len(created) == 1
    arguments = cast(list[str], captured["args"])
    command = " ".join(arguments)
    for value in ["needle", *documents]:
        assert value not in command
    payload = json.loads(cast(bytes, captured["input"]).decode("utf-8"))
    assert payload == {
        "mode": "documents",
        "pattern": "needle",
        "ignore_case": True,
        "documents": documents,
    }
    captured_kwargs = cast(dict[str, object], captured["kwargs"])
    environment = cast(dict[str, str], captured_kwargs["env"])
    assert TOKEN_VARIABLE not in environment
    assert TOKEN not in environment.values()
    assert captured["timeout"] == 2.0


def test_line_mode_still_returns_one_based_line_numbers() -> None:
    assert regex_helper.match_lines(
        "one\r\nNEEDLE\r\nthree\r\n",
        "needle",
        ignore_case=True,
        limit=5,
        timeout_s=5.0,
    ) == [2]


def test_document_matching_is_whole_body_and_multiline() -> None:
    documents = ["alpha\nSECOND line", "alpha only"]

    assert regex_helper.match_documents(
        documents,
        r"alpha\nSECOND",
        ignore_case=False,
        timeout_s=5.0,
    ) == [True, False]
    assert regex_helper.match_documents(
        documents,
        r"(?mi)^second",
        ignore_case=False,
        timeout_s=5.0,
    ) == [True, False]


def test_document_batch_invalid_regex_is_sanitized() -> None:
    with pytest.raises(regex_helper.InvalidRegex) as error:
        regex_helper.match_documents(
            ["body"], "(", ignore_case=False, timeout_s=5.0
        )

    assert str(error.value) == "The regular expression is invalid."


def test_document_batch_timeout_kills_and_attempts_reap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class Process:
        returncode: int | None = None

        def __init__(self) -> None:
            self.killed = False
            self.waits = 0

        def communicate(
            self, data: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            if not self.killed:
                raise subprocess.TimeoutExpired("helper", timeout or 0)
            return b"", b""

        def poll(self) -> int | None:
            return self.returncode if self.killed else None

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            assert self.returncode is not None
            return self.returncode

    def factory(args: list[str], **kwargs: object) -> Process:
        process = Process()
        created.append(process)
        return process

    monkeypatch.setattr(regex_helper.subprocess, "Popen", factory)

    with pytest.raises(regex_helper.RegexTimeout) as error:
        regex_helper.match_documents(
            ["body"], "needle", ignore_case=False, timeout_s=0.1
        )

    assert str(error.value) == "The regular expression evaluation timed out."
    process = cast(Process, created[0])
    assert len(created) == 1
    assert process.killed is True
    assert process.waits == 1


def test_real_helper_timeout_kills_and_reaps_a_started_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A started helper must reach matching before the timeout and be reaped.

    The handshake is inserted into the real line-mode source immediately before
    ``pattern.search(line)``, after stdin parsing and pattern compilation. A
    helper that starts but never reaches matching therefore never signals and
    fails this test.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = cast(int, listener.getsockname()[1])
    started = threading.Event()

    def accept_handshake() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                if connection.recv(16) == b"started":
                    started.set()
        except OSError:
            pass

    server = threading.Thread(target=accept_handshake, daemon=True)
    server.start()

    source = regex_helper.HELPER_SOURCE
    assert source.count("import re\n") == 1
    assert source.count("        if pattern.search(line):\n") == 1
    handshake = (
        "        _handshake = socket.create_connection("
        f"('127.0.0.1', {port}), timeout=2)\n"
        "        _handshake.sendall(b'started')\n"
        "        _handshake.close()\n"
    )
    source = source.replace("import re\n", "import re\nimport socket\n", 1)
    source = source.replace(
        "        if pattern.search(line):\n",
        handshake + "        if pattern.search(line):\n",
        1,
    )
    monkeypatch.setattr(regex_helper, "HELPER_SOURCE", source)

    original_popen = subprocess.Popen
    handles: list[subprocess.Popen] = []

    def recording_popen(*args: object, **kwargs: object) -> subprocess.Popen:
        process = original_popen(*args, **kwargs)
        handles.append(process)
        return process

    monkeypatch.setattr(regex_helper.subprocess, "Popen", recording_popen)

    outcome: dict[str, BaseException] = {}

    def run_helper() -> None:
        try:
            regex_helper.match_lines(
                "a" * 50_000 + "!",
                "(a+)+$",
                ignore_case=False,
                limit=1,
                timeout_s=2.0,
                line_count=1,
            )
        except BaseException as exc:
            outcome["error"] = exc

    worker = threading.Thread(target=run_helper, daemon=True)
    worker.start()
    try:
        assert started.wait(5.0) is True
        assert worker.is_alive() is True
        worker.join(5.0)
        assert worker.is_alive() is False

        error = outcome.get("error")
        assert isinstance(error, regex_helper.RegexTimeout)
        assert str(error) == "The regular expression evaluation timed out."
        assert error.__cause__ is None
        assert "(a+)+$" not in str(error)
        assert "a" * 20 not in str(error)

        assert len(handles) == 1
        process = handles[0]
        assert process.poll() is not None
        assert process.wait(timeout=5.0) == process.returncode
        assert process.returncode is not None
    finally:
        listener.close()
        server.join(5.0)
        worker.join(5.0)
        assert server.is_alive() is False


def test_unreapable_cleanup_keeps_the_generic_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class Process:
        returncode: int | None = None

        def __init__(self) -> None:
            self.killed = False
            self.waits = 0

        def communicate(
            self, data: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            if not self.killed:
                raise subprocess.TimeoutExpired("helper", timeout or 0)
            return b"", b""

        def poll(self) -> int | None:
            return self.returncode if self.killed else None

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            raise subprocess.TimeoutExpired("helper", timeout or 0)

    def factory(args: list[str], **kwargs: object) -> Process:
        process = Process()
        created.append(process)
        return process

    monkeypatch.setattr(regex_helper.subprocess, "Popen", factory)

    with pytest.raises(regex_helper.RegexTimeout) as error:
        regex_helper.match_documents(
            ["body"], "needle", ignore_case=False, timeout_s=0.1
        )

    assert str(error.value) == "The regular expression evaluation timed out."
    process = cast(Process, created[0])
    assert process.killed is True
    assert process.waits == 1


@pytest.mark.parametrize(
    ("stdout", "count"),
    [
        (b"not json", 1),
        (b'{"value": []}', 1),
        (b'{"matches": []}', 1),
        (b'{"matches": [true, false]}', 1),
        (b'{"matches": [1]}', 1),
        (b'{"matches": [true, "false"]}', 2),
    ],
    ids=[
        "not-json",
        "missing-matches",
        "wrong-length",
        "too-many",
        "integer",
        "string",
    ],
)
def test_document_result_is_validated(stdout: bytes, count: int) -> None:
    with pytest.raises(regex_helper.HelperFailure):
        regex_helper.decode_document_matches(stdout, count=count)


def test_document_result_accepts_bool_list() -> None:
    assert regex_helper.decode_document_matches(
        b'{"matches": [true, false]}', count=2
    ) == [True, False]


def test_empty_document_batch_still_validates_the_pattern() -> None:
    assert (
        regex_helper.match_documents(
            [], "needle", ignore_case=False, timeout_s=5.0
        )
        == []
    )

    with pytest.raises(regex_helper.InvalidRegex):
        regex_helper.match_documents(
            [], "(", ignore_case=False, timeout_s=5.0
        )


def test_validate_regex_accepts_a_valid_pattern_and_rejects_an_invalid_one() -> None:
    assert (
        regex_helper.validate_regex(
            "needle", ignore_case=True, timeout_s=5.0
        )
        is None
    )

    with pytest.raises(regex_helper.InvalidRegex):
        regex_helper.validate_regex("(", ignore_case=False, timeout_s=5.0)


def test_helper_source_is_valid_python() -> None:
    compile(regex_helper.HELPER_SOURCE, "<regex-helper>", "exec")

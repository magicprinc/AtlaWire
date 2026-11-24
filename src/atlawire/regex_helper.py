"""Killable, isolated evaluation of caller-supplied Python regular expressions.

A short helper process is started with ``-I -S -c``; one JSON request carries
the pattern and text(s) on stdin, so no user text, pattern, URL, or credential
appears on the command line. The helper receives a minimal environment without
AtlaWire variables. A helper that exceeds its timeout is killed and a bounded
reap is attempted; a process that does not respond within the bounded waits is
left to the operating system. Errors never include the pattern, text, or a
cleanup-specific diagnostic.

Modes:

* ``lines`` evaluates one LF-delimited text and returns 1-based line numbers
  for matching lines, capped by ``limit``.
* ``documents`` evaluates a batch of whole strings and returns one boolean per
  input, in order, from one helper process. Python ``re.search`` runs over the
  entire string, so explicit newlines and ``(?m)``/``(?s)`` work; evaluation is
  not line-by-line.
* ``validate`` only compiles the pattern.

The timeout covers pattern compilation and the whole batch. Python's ``re`` has
no in-process timeout, so killing the helper is the only reliable way to stop
catastrophic backtracking. An in-flight subprocess is not cancelable except by
the documented kill-on-timeout path.
"""

import json
import math
import os
import subprocess
import sys
from collections.abc import Sequence

__all__ = [
    "HelperFailure",
    "InvalidRegex",
    "RegexHelperError",
    "RegexTimeout",
    "decode_document_matches",
    "decode_line_matches",
    "match_documents",
    "match_lines",
    "split_lines",
    "validate_regex",
]

HELPER_SOURCE = """
import json
import re
import sys

request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
try:
    pattern = re.compile(
        request["pattern"],
        re.IGNORECASE if request["ignore_case"] else 0,
    )
except (re.error, OverflowError, RecursionError):
    sys.stdout.buffer.write(b'{"error":"invalid_regex"}')
    raise SystemExit(3)
mode = request["mode"]
if mode == "validate":
    result = {"ok": True}
elif mode == "lines":
    text = request["text"]
    limit = request["limit"]
    lines = text.split("\\n")
    if lines and lines[-1] == "":
        lines.pop()
    matches = []
    for number, line in enumerate(lines, 1):
        if line.endswith("\\r"):
            line = line[:-1]
        if pattern.search(line):
            matches.append(number)
            if len(matches) >= limit:
                break
    result = {"matches": matches}
elif mode == "documents":
    result = {
        "matches": [
            bool(pattern.search(document))
            for document in request["documents"]
        ]
    }
else:
    raise SystemExit(2)
sys.stdout.buffer.write(json.dumps(result).encode("utf-8"))
"""

_INVALID_REGEX_EXIT = 3
_KILL_WAIT_SECONDS = 5.0


class RegexHelperError(Exception):
    """A sanitized regular-expression helper failure."""


class InvalidRegex(RegexHelperError):
    """The helper rejected the regular expression."""

    def __init__(self) -> None:
        super().__init__("The regular expression is invalid.")


class RegexTimeout(RegexHelperError):
    """The helper exceeded its timeout and was stopped."""

    def __init__(self) -> None:
        super().__init__("The regular expression evaluation timed out.")


class HelperFailure(RegexHelperError):
    """The helper could not start or returned an unusable result."""

    def __init__(self) -> None:
        super().__init__("The regular expression helper failed.")


def split_lines(text: str) -> list[str]:
    """Split LF-delimited lines, drop one final terminator and each CR of CRLF.

    The helper applies the same rule. A lone LF ends the preceding line, a final
    newline does not create a phantom empty line, and a CR is removed only when
    it belongs to a CRLF pair at the end of that line.
    """
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def match_lines(
    text: str,
    pattern: str,
    *,
    ignore_case: bool,
    limit: int,
    timeout_s: float,
    line_count: int | None = None,
) -> list[int]:
    """Return 1-based matching line numbers from one killable helper.

    ``line_count`` is an optional caller-computed count that must equal the
    text's line count; it guards the wire response against a broken helper.
    """
    if not isinstance(text, str):
        raise HelperFailure
    _validate_common(pattern, ignore_case, timeout_s)
    _validate_limit(limit)
    actual = len(split_lines(text))
    if line_count is not None:
        if (
            not isinstance(line_count, int)
            or isinstance(line_count, bool)
            or line_count < 0
            or line_count != actual
        ):
            raise HelperFailure
    request = {
        "mode": "lines",
        "pattern": pattern,
        "ignore_case": ignore_case,
        "text": text,
        "limit": limit,
    }
    stdout = _run(request, timeout_s)
    return decode_line_matches(stdout, limit=limit, line_count=actual)


def match_documents(
    documents: Sequence[str],
    pattern: str,
    *,
    ignore_case: bool,
    timeout_s: float,
) -> list[bool]:
    """Return one whole-string match flag per document from one helper.

    All documents are sent in one request, so a comment page costs one helper
    process rather than one per comment. An empty batch still validates the
    pattern in one helper and returns ``[]``. Matching uses Python
    ``re.search`` over each complete string, not line-by-line; explicit
    newlines and ``(?m)``/``(?s)`` apply.
    """
    _validate_common(pattern, ignore_case, timeout_s)
    if not isinstance(documents, Sequence) or isinstance(
        documents, (str, bytes)
    ):
        raise HelperFailure
    texts = list(documents)
    if any(not isinstance(document, str) for document in texts):
        raise HelperFailure
    if not texts:
        validate_regex(pattern, ignore_case=ignore_case, timeout_s=timeout_s)
        return []
    stdout = _run(
        {
            "mode": "documents",
            "pattern": pattern,
            "ignore_case": ignore_case,
            "documents": texts,
        },
        timeout_s,
    )
    return decode_document_matches(stdout, count=len(texts))


def validate_regex(
    pattern: str, *, ignore_case: bool, timeout_s: float
) -> None:
    """Compile the pattern in a killable helper without evaluating text."""
    _validate_common(pattern, ignore_case, timeout_s)
    stdout = _run(
        {
            "mode": "validate",
            "pattern": pattern,
            "ignore_case": ignore_case,
        },
        timeout_s,
    )
    value = _decode_json(stdout)
    if value.get("ok") is not True:
        raise HelperFailure


def decode_line_matches(
    stdout: bytes, *, limit: int, line_count: int
) -> list[int]:
    """Validate and decode one lines-mode helper response."""
    value = _decode_json(stdout)
    matches = value.get("matches")
    if not isinstance(matches, list) or len(matches) > limit:
        raise HelperFailure
    numbers: list[int] = []
    previous = 0
    for item in matches:
        if (
            not isinstance(item, int)
            or isinstance(item, bool)
            or item <= previous
            or item > line_count
        ):
            raise HelperFailure
        previous = item
        numbers.append(item)
    return numbers


def decode_document_matches(stdout: bytes, *, count: int) -> list[bool]:
    """Validate and decode one documents-mode helper response."""
    value = _decode_json(stdout)
    matches = value.get("matches")
    if not isinstance(matches, list) or len(matches) != count:
        raise HelperFailure
    if any(not isinstance(item, bool) for item in matches):
        raise HelperFailure
    return [bool(item) for item in matches]


def _validate_common(
    pattern: str, ignore_case: bool, timeout_s: float
) -> None:
    if not isinstance(pattern, str) or not isinstance(ignore_case, bool):
        raise HelperFailure
    if (
        not isinstance(timeout_s, (int, float))
        or isinstance(timeout_s, bool)
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise HelperFailure


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise HelperFailure


def _decode_json(stdout: bytes) -> dict[str, object]:
    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HelperFailure from None
    if not isinstance(value, dict):
        raise HelperFailure
    return value


def _run(request: dict[str, object], timeout_s: float) -> bytes:
    payload = json.dumps(request, ensure_ascii=True).encode("utf-8")
    executable = sys.executable
    if not executable:
        raise HelperFailure
    try:
        process = subprocess.Popen(
            [executable, "-I", "-S", "-c", HELPER_SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_helper_environment(),
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError:
        raise HelperFailure from None
    stdout = b""
    cleaned = False
    try:
        try:
            stdout, _ = process.communicate(payload, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _stop_helper(process)
            cleaned = True
            raise RegexTimeout from None
        except (OSError, ValueError):
            raise HelperFailure from None
    finally:
        if not cleaned and process.poll() is None:
            _stop_helper(process)
    if process.returncode == _INVALID_REGEX_EXIT:
        raise InvalidRegex
    if process.returncode != 0:
        raise HelperFailure
    return stdout


def _stop_helper(process: subprocess.Popen) -> None:
    """Attempt to kill and reap within bounded waits; reaping is not guaranteed.

    A process that remains unresponsive after ``kill`` and the bounded
    ``communicate``/``wait`` attempts is left to the operating system. This
    best-effort cleanup never raises a second, cleanup-specific error.
    """
    if process.poll() is None:
        process.kill()
    try:
        process.communicate(timeout=_KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
    try:
        process.wait(timeout=_KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _helper_environment() -> dict[str, str]:
    """Return a minimal environment that cannot carry an AtlaWire token."""
    names = ("SYSTEMROOT", "WINDIR", "PATH") if os.name == "nt" else ()
    return {name: os.environ[name] for name in names if name in os.environ}

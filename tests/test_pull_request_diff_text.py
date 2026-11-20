from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

HEADER = "# Bitbucket PR diff review (context=3; whitespace=ignore-all; not a patch)\n"


def line(text: object = "x") -> dict[str, object]:
    return {"line": text}


def segment(kind: object = "CONTEXT", *texts: object) -> dict[str, object]:
    return {"type": kind, "lines": [line(text) for text in texts]}


def ranges(**values: object) -> dict[str, object]:
    numbers: dict[str, object] = {
        "sourceLine": 1,
        "sourceSpan": 1,
        "destinationLine": 1,
        "destinationSpan": 1,
    }
    numbers.update(values)
    return numbers


def file_diff(
    source: object,
    destination: object,
    *segments: dict[str, object],
    **values: object,
) -> dict[str, object]:
    return {
        "source": source,
        "destination": destination,
        "hunks": [{**ranges(**values), "segments": list(segments)}],
    }


def render(value: object) -> str:
    return bitbucket._render_pull_request_diff_text(
        cast(dict[str, object], value), context=3
    )


def test_empty_diff_response_has_an_honest_no_hunk_marker() -> None:
    assert render({"diffs": []}) == (HEADER + "\n(no textual hunks in the response)\n")


def test_files_without_hunks_keep_declared_order_and_get_a_marker() -> None:
    value = {
        "diffs": [
            {"source": {"toString": "b.py"}, "destination": {"toString": "b.py"}},
            {
                "source": {"toString": "a.py"},
                "destination": {"toString": "a.py"},
                "hunks": [],
            },
        ]
    }

    assert render(value) == (
        HEADER + "\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "(no textual hunks in this file)\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "(no textual hunks in this file)\n"
    )


@pytest.mark.parametrize(
    ("source", "destination", "header"),
    [
        (
            {"toString": "new.py"},
            None,
            "--- a/new.py\n+++ /dev/null\n",
        ),
        (
            None,
            {"toString": "gone.py"},
            "--- /dev/null\n+++ b/gone.py\n",
        ),
    ],
    ids=["source-only", "destination-only"],
)
def test_an_absent_side_is_the_unprefixed_null_device(
    source: object, destination: object, header: str
) -> None:
    value = {"diffs": [{"source": source, "destination": destination, "hunks": []}]}

    assert header in render(value)


@pytest.mark.parametrize(
    "value",
    [
        {"diffs": [{"hunks": []}]},
        {
            "diffs": [
                {
                    "source": {"components": []},
                    "destination": {"toString": "x"},
                    "hunks": [],
                }
            ]
        },
        {"diffs": [{"source": 7, "destination": {"toString": "x"}, "hunks": []}]},
    ],
    ids=["both-absent", "malformed-source", "non-path-source"],
)
def test_missing_or_malformed_paths_are_rejected(value: dict[str, object]) -> None:
    with pytest.raises(AtlaWireError, match="path"):
        render(value)


def test_zero_range_numbers_are_printed_exactly() -> None:
    value = {
        "diffs": [
            file_diff(
                {"toString": "x"},
                {"toString": "x"},
                segment("CONTEXT", "x"),
                sourceLine=0,
                sourceSpan=0,
                destinationLine=0,
                destinationSpan=0,
            )
        ]
    }

    assert "@@ -0,0 +0,0 @@\n x\n" in render(value)


def test_hunks_keep_declared_order() -> None:
    value = {
        "diffs": [
            {
                "source": {"toString": "x"},
                "destination": {"toString": "x"},
                "hunks": [
                    {
                        **ranges(sourceLine=20, destinationLine=20),
                        "segments": [segment("CONTEXT", "second")],
                    },
                    {
                        **ranges(sourceLine=5, destinationLine=5),
                        "segments": [segment("CONTEXT", "first")],
                    },
                ],
            }
        ]
    }

    text = render(value)

    assert text.index("@@ -20,1 +20,1 @@") < text.index("@@ -5,1 +5,1 @@")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("sourceLine", "1"),
        ("sourceSpan", True),
        ("destinationLine", 1.5),
        ("destinationSpan", -1),
        ("sourceLine", None),
    ],
    ids=["string", "bool", "float", "negative", "null"],
)
def test_invalid_range_numbers_are_rejected(key: str, value: object) -> None:
    values = ranges()
    values[key] = value
    diff = {
        "diffs": [
            {
                "source": {"toString": "x"},
                "destination": {"toString": "x"},
                "hunks": [{"segments": [segment("CONTEXT", "x")], **values}],
            }
        ]
    }

    with pytest.raises(AtlaWireError, match="line range"):
        render(diff)


def test_a_missing_range_number_is_rejected() -> None:
    values = ranges()
    del values["destinationSpan"]
    diff = {
        "diffs": [
            {
                "source": {"toString": "x"},
                "destination": {"toString": "x"},
                "hunks": [{"segments": [segment("CONTEXT", "x")], **values}],
            }
        ]
    }

    with pytest.raises(AtlaWireError, match="line range"):
        render(diff)


def test_controls_and_backslashes_are_escaped_and_spaces_preserved() -> None:
    value = {
        "diffs": [
            file_diff(
                {"toString": "dir\\name\u202e.py"},
                {"toString": "dir\\name\u202e.py"},
                segment("CONTEXT", "  keep τ😀  "),
                segment("ADDED", "a\tb\\c\x1b\x85"),
                segment("REMOVED", ""),
            )
        ]
    }

    text = render(value)

    assert "--- a/dir\\\\name\\u202e.py\n" in text
    assert "+++ b/dir\\\\name\\u202e.py\n" in text
    assert "   keep τ😀  \n" in text
    assert "+a\\tb\\\\c\\x1b\\x85\n" in text
    assert "\n-\n" in text


@pytest.mark.parametrize(
    "text",
    ["a\nb", "a\rb", "a\u2028b", "a\u2029b"],
    ids=["lf", "cr", "line-separator", "paragraph-separator"],
)
def test_literal_line_breaks_in_line_text_are_rejected(text: str) -> None:
    value = {
        "diffs": [
            file_diff({"toString": "x"}, {"toString": "x"}, segment("CONTEXT", text))
        ]
    }

    with pytest.raises(AtlaWireError, match="line break"):
        render(value)


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        ([], "segments"),
        ([{"type": "COPIED", "lines": [line("x")]}], "type"),
        ([{"type": "CONTEXT", "lines": []}], "lines"),
        ([{"type": "CONTEXT", "lines": [line(7)]}], "text"),
        ([{"type": "CONTEXT", "lines": ["x"]}], "line object"),
    ],
    ids=[
        "no-segments",
        "unknown-type",
        "no-lines",
        "non-string-text",
        "non-object-line",
    ],
)
def test_empty_or_malformed_hunk_content_is_rejected(
    segments: list[object], expected: str
) -> None:
    value = {
        "diffs": [
            {
                "source": {"toString": "x"},
                "destination": {"toString": "x"},
                "hunks": [
                    {**ranges(), "segments": segments},
                ],
            }
        ]
    }

    with pytest.raises(AtlaWireError, match=expected):
        render(value)

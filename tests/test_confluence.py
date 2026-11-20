import pytest

from atlawire.confluence import page_id
from atlawire.http import AtlaWireError


@pytest.mark.parametrize("value", ["1", "123", "9007199254740993"])
def test_canonical_id_string_is_accepted_unchanged(value: str) -> None:
    assert page_id(value) == value


@pytest.mark.parametrize("value", [1, 123, 9007199254740993])
def test_positive_integer_id_is_converted_to_string(value: int) -> None:
    assert page_id(value) == str(value)


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "007",
        "-1",
        "+1",
        "",
        " 123",
        "123 ",
        "1\n",
        "١٢٣",
        "1.0",
        "0x10",
        "abc",
        "/pages/123",
        "pages/viewpage.action?pageId=123",
    ],
)
def test_non_canonical_id_strings_are_rejected(value: str) -> None:
    with pytest.raises(AtlaWireError):
        page_id(value)


@pytest.mark.parametrize("value", [0, -1, True, False])
def test_non_positive_or_boolean_integer_ids_are_rejected(
    value: int | bool,
) -> None:
    with pytest.raises(AtlaWireError):
        page_id(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://wiki.example.invalid/pages/viewpage.action?pageId=123", "123"),
        (
            (
                "http://other.example.invalid/confluence/display/DEMO/Page"
                "?spaceKey=DEMO&pageId=123#section"
            ),
            "123",
        ),
        ("https://wiki.example.invalid/pages/viewpage.action?pageId=%31%32%33", "123"),
    ],
)
def test_absolute_page_link_supplies_only_the_id(value: str, expected: str) -> None:
    assert page_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://wiki.example.invalid/pages/viewpage.action",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=123&pageId=124",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=0",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=007",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=abc",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=123%0A",
        "https://wiki.example.invalid/pages/viewpage.action?PageId=123",
        "ftp://wiki.example.invalid/pages/viewpage.action?pageId=123",
        "https:///pages/viewpage.action?pageId=123",
        "https://[::1/pages/viewpage.action?pageId=123",
        "/pages/viewpage.action?pageId=123",
    ],
)
def test_missing_ambiguous_or_malformed_links_are_rejected(value: str) -> None:
    with pytest.raises(AtlaWireError):
        page_id(value)


@pytest.mark.parametrize(
    "value",
    [
        " https://wiki.example.invalid/pages/viewpage.action?pageId=123",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=12\n3",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=12\t3",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=12\r3",
        "https://wiki.example.invalid/pages/view page.action?pageId=123",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=123\x7f",
    ],
)
def test_raw_ascii_whitespace_or_control_in_link_is_rejected(value: str) -> None:
    with pytest.raises(AtlaWireError):
        page_id(value)


def test_error_message_does_not_echo_the_rejected_link() -> None:
    link = "https://user:fixture-secret@wiki.example.invalid/?pageId=007"

    with pytest.raises(AtlaWireError) as error:
        page_id(link)

    assert "fixture-secret" not in str(error.value)

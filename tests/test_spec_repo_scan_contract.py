"""The partial-inventory report recognizes the page-budget type, not its text."""

from atlawire.bitbucket import PageLimitError
from atlawire.http import AtlaWireError
from atlawire.repo_scan import _is_page_limit_error


def test_the_dedicated_page_limit_stop_is_a_partial_report():
    error = PageLimitError("Bitbucket page limit reached; increase --max-pages.")

    assert _is_page_limit_error(error)


def test_a_plain_error_with_the_same_message_is_not_a_partial_report():
    error = AtlaWireError("Bitbucket page limit reached; increase --max-pages.")

    assert not _is_page_limit_error(error)

import pytest

from atlawire.bitbucket import list_repositories
from atlawire.http import AtlaWireError, normalize_base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.invalid/scm",
        "https://user:fixture@example.invalid/scm",
        "https://example.invalid/scm?",
        "https://example.invalid/scm#",
        "https://example.invalid:invalid/scm",
    ],
)
def test_unsafe_base_url_is_rejected_without_echoing_it(base_url: str) -> None:
    with pytest.raises(AtlaWireError, match="Use an HTTPS base URL") as error:
        normalize_base_url(base_url, allow_http_loopback=True)
    assert base_url not in str(error.value)


def test_https_keeps_the_context_path() -> None:
    assert (
        normalize_base_url("https://example.invalid/scm/", allow_http_loopback=False)
        == "https://example.invalid/scm"
    )


def test_http_loopback_requires_explicit_opt_in() -> None:
    with pytest.raises(AtlaWireError, match="Use an HTTPS base URL"):
        normalize_base_url("http://127.0.0.1:8080", allow_http_loopback=False)


@pytest.mark.parametrize("project", ["..", "A/B", "A%2fB", "A?B"])
def test_project_is_a_single_path_segment(project: str) -> None:
    with pytest.raises(AtlaWireError, match="project key"):
        list_repositories("https://example.invalid", project, token="fixture-only")

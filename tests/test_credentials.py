"""Unit contracts for saved BBK credential reuse."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.credentials import (
    CREDENTIALS_ENV,
    SavedCredentials,
    credentials_path,
    load_saved_credentials,
    resolve_saved_credentials,
)
from atlawire.http import AtlaWireError

JIRA_TOKEN = "jira-token-sentinel"
CONFLUENCE_TOKEN = "confluence-token-sentinel"
BITBUCKET_TOKEN = "bitbucket-token-sentinel"
JIRA_URL = "https://jira.example.invalid/jira/"
CONFLUENCE_URL = "https://wiki.example.invalid/confluence/"
BITBUCKET_URL = "https://bitbucket.example.invalid/scm/"
SECRET_MARKER = "payload-must-not-be-echoed"

COMPLETE = {
    "jira_url": JIRA_URL,
    "jira_token": JIRA_TOKEN,
    "confluence_url": CONFLUENCE_URL,
    "confluence_token": CONFLUENCE_TOKEN,
    "bitbucket_url": BITBUCKET_URL,
    "bitbucket_token": BITBUCKET_TOKEN,
}


def configured_file(
    monkeypatch: pytest.MonkeyPatch, path: Path, document: object
) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setenv(CREDENTIALS_ENV, str(path))
    return path


def test_credentials_path_honors_bbk_override_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "fixtures/credential-store.json"

    monkeypatch.setenv(CREDENTIALS_ENV, relative)

    assert credentials_path() == Path(relative)


def test_default_path_matches_the_bbk_home_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = Path("C:/fixture-home")
    monkeypatch.delenv(CREDENTIALS_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert credentials_path() == home / ".config" / "atlassian" / "credentials.json"


def test_saved_credentials_repr_does_not_expose_the_token() -> None:
    saved = SavedCredentials(
        base_url="https://jira.example.invalid/jira", token=JIRA_TOKEN
    )

    rendered = repr(saved)

    assert "SavedCredentials(" in rendered
    assert "base_url=" in rendered
    assert "token" not in rendered
    assert JIRA_TOKEN not in rendered
    assert JIRA_TOKEN not in str(saved)


@pytest.mark.parametrize(
    ("product", "expected_url", "expected_token"),
    [
        ("jira", JIRA_URL.rstrip("/"), JIRA_TOKEN),
        ("confluence", CONFLUENCE_URL.rstrip("/"), CONFLUENCE_TOKEN),
        ("bitbucket", BITBUCKET_URL.rstrip("/"), BITBUCKET_TOKEN),
    ],
)
def test_each_product_reads_only_its_own_matched_pair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    product: str,
    expected_url: str,
    expected_token: str,
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", COMPLETE)

    saved = load_saved_credentials(product, allow_http_loopback=False)

    assert saved.base_url == expected_url
    assert saved.token == expected_token


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"jira_url": JIRA_URL},
        {"jira_token": JIRA_TOKEN},
        {"jira_url": JIRA_URL, "jira_token": ""},
        {"jira_url": JIRA_URL, "jira_token": 123},
        {"jira_url": 123, "jira_token": JIRA_TOKEN},
        {"jira_url": JIRA_URL, "jira_token": ["nested"]},
        {"jira_url": JIRA_URL, "jira_token": "bad token"},
        {"jira_url": JIRA_URL, "jira_token": "line\nbreak"},
        {"jira_url": JIRA_URL, "confluence_token": CONFLUENCE_TOKEN},
        {"jira_token": JIRA_TOKEN, "confluence_url": CONFLUENCE_URL},
        {"jira_url": "http://jira.example.invalid/jira", "jira_token": JIRA_TOKEN},
        {
            "jira_url": "https://user:pass@jira.example.invalid",
            "jira_token": JIRA_TOKEN,
        },
        {"jira_url": "https://jira.example.invalid?x=1", "jira_token": JIRA_TOKEN},
        [],
        "text",
    ],
)
def test_invalid_documents_fail_generically_without_echoing_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    document: object,
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", document)

    with pytest.raises(AtlaWireError) as caught:
        load_saved_credentials("jira", allow_http_loopback=False)

    message = str(caught.value)
    assert message == "Saved BBK credentials are invalid for jira."
    assert JIRA_TOKEN not in message
    assert JIRA_URL not in message
    assert SECRET_MARKER not in message


@pytest.mark.parametrize(
    "raw",
    [
        b'{"jira_url": "'
        + JIRA_URL.encode()
        + b'", "jira_token": "'
        + SECRET_MARKER.encode(),
        b'{"jira_url": "\xff\xfe", "jira_token": "x"}',
        b'["jira_url", "jira_token"]',
    ],
)
def test_malformed_or_non_utf8_files_never_echo_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: bytes
) -> None:
    path = tmp_path / "credentials.json"
    path.write_bytes(raw)
    monkeypatch.setenv(CREDENTIALS_ENV, str(path))

    with pytest.raises(AtlaWireError) as caught:
        load_saved_credentials("jira", allow_http_loopback=False)

    assert str(caught.value) == "Saved BBK credentials are invalid for jira."
    assert SECRET_MARKER not in str(caught.value)


def test_missing_file_is_generic_and_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "missing.json"
    monkeypatch.setenv(CREDENTIALS_ENV, str(path))

    with pytest.raises(AtlaWireError) as caught:
        load_saved_credentials("jira", allow_http_loopback=False)

    assert str(caught.value) == "Saved BBK credentials are unavailable for jira."
    assert str(path) not in str(caught.value)


@pytest.mark.parametrize(
    "partial",
    [
        {"jira_url": JIRA_URL},
        {"jira_token": JIRA_TOKEN},
        {"confluence_url": CONFLUENCE_URL, "confluence_token": CONFLUENCE_TOKEN},
        {"bitbucket_url": BITBUCKET_URL, "bitbucket_token": BITBUCKET_TOKEN},
    ],
)
def test_partial_entries_do_not_fall_back_to_another_product(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, partial: dict[str, str]
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", partial)

    with pytest.raises(AtlaWireError) as caught:
        load_saved_credentials("jira", allow_http_loopback=False)

    message = str(caught.value)
    assert "jira" in message
    assert CONFLUENCE_TOKEN not in message
    assert BITBUCKET_TOKEN not in message


def test_saved_url_is_normalized_to_the_bbk_product_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", COMPLETE)

    saved = resolve_saved_credentials(
        "jira", supplied_base_url=None, allow_http_loopback=False
    )

    assert saved.base_url == "https://jira.example.invalid/jira"


@pytest.mark.parametrize(
    "supplied",
    [
        "https://jira.example.invalid/jira",
        "https://jira.example.invalid/jira/",
    ],
)
def test_equivalent_supplied_url_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, supplied: str
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", COMPLETE)

    saved = resolve_saved_credentials(
        "jira", supplied_base_url=supplied, allow_http_loopback=False
    )

    assert saved.base_url == "https://jira.example.invalid/jira"
    assert saved.token == JIRA_TOKEN


def test_different_supplied_url_is_rejected_without_echoing_the_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", COMPLETE)

    with pytest.raises(AtlaWireError) as caught:
        resolve_saved_credentials(
            "jira",
            supplied_base_url="https://other.example.invalid/jira",
            allow_http_loopback=False,
        )

    message = str(caught.value)
    assert message == (
        "The supplied base URL does not match saved BBK credentials for jira."
    )
    assert JIRA_TOKEN not in message


def test_malformed_supplied_url_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured_file(monkeypatch, tmp_path / "credentials.json", COMPLETE)

    with pytest.raises(AtlaWireError) as caught:
        resolve_saved_credentials(
            "jira",
            supplied_base_url="https://user:pass@jira.example.invalid/jira",
            allow_http_loopback=False,
        )

    assert "HTTPS base URL" in str(caught.value)
    assert JIRA_TOKEN not in str(caught.value)


def test_loopback_http_requires_the_explicit_test_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = {
        "jira_url": "http://127.0.0.1:8765/jira/",
        "jira_token": JIRA_TOKEN,
    }
    configured_file(monkeypatch, tmp_path / "credentials.json", document)

    with pytest.raises(AtlaWireError) as caught:
        load_saved_credentials("jira", allow_http_loopback=False)
    assert str(caught.value) == "Saved BBK credentials are invalid for jira."

    saved = load_saved_credentials("jira", allow_http_loopback=True)
    assert saved.base_url == "http://127.0.0.1:8765/jira"


def test_explicit_environment_mode_never_opens_the_saved_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("saved credentials must not be read")

    monkeypatch.setenv(CREDENTIALS_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setattr("atlawire.cli.resolve_saved_credentials", forbidden)
    monkeypatch.setenv("ATLAWIRE_JIRA_TOKEN", "")

    result = CliRunner().invoke(
        cli,
        [
            "jira-me",
            "--base-url",
            "https://jira.example.invalid/jira",
            "--token-from-env",
        ],
    )

    assert result.exit_code == 1
    assert "Missing or invalid bearer token" in result.stderr
    assert "saved credentials" not in result.stderr


def test_environment_mode_requires_a_url_and_never_falls_back_to_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("saved credentials must not be read")

    monkeypatch.setenv(CREDENTIALS_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setattr("atlawire.cli.resolve_saved_credentials", forbidden)
    monkeypatch.delenv("ATLAWIRE_JIRA_URL", raising=False)

    result = CliRunner().invoke(cli, ["jira-me", "--token-from-env"])

    assert result.exit_code == 2
    assert "Missing --base-url or ATLAWIRE_JIRA_URL" in result.stderr


@pytest.mark.parametrize("argument", ["--help", "--version"])
def test_help_and_version_never_read_saved_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argument: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("help and version must not read credentials")

    monkeypatch.setenv(CREDENTIALS_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setattr("atlawire.cli.resolve_saved_credentials", forbidden)

    result = CliRunner().invoke(cli, [argument])

    assert result.exit_code == 0

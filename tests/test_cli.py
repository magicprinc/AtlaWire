from click.testing import CliRunner

from atlawire import __version__
from atlawire.cli import cli


def test_help_lists_version_option() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "--version" in result.output


def test_version_reports_package_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"atlawire, version {__version__}"


def test_bare_invocation_shows_help() -> None:
    result = CliRunner().invoke(cli, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Error:" not in result.output

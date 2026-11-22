"""Focused unit checks for the Click-derived command catalog."""

import builtins
import json
import os
from pathlib import Path
from typing import NoReturn, cast

import click
import pytest
import requests

import atlawire.cli as cli_module
from atlawire.catalog import build_command_catalog
from atlawire.cli import cli


@pytest.fixture(autouse=True)
def _missing_bbk_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point credential reuse at a nonexistent fixture path for every test."""
    path = tmp_path / "fixture-missing-bbk-credentials.json"
    monkeypatch.setenv("BBK_CREDENTIALS", str(path))


def command_entry(catalog: dict[str, object], name: str) -> dict[str, object]:
    commands = cast(dict[str, dict[str, object]], catalog["commands"])
    return commands[name]


def params_by_name(command: dict[str, object]) -> dict[str, dict[str, object]]:
    params = cast(list[dict[str, object]], command["params"])
    return {cast(str, param["name"]): param for param in params}


def options_by_flag(command: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for param in params_by_name(command).values():
        for flag in cast(list[str], param.get("opts", [])):
            result[flag] = param
    return result


def test_catalog_uses_click_metadata_for_flat_commands() -> None:
    @click.group("root")
    def root() -> None:
        """Root tools."""

    @root.command("deploy")
    @click.argument("target")
    @click.option("--dry-run", is_flag=True, help="Plan without changes.")
    @click.option(
        "--mode",
        type=click.Choice(["safe", "fast"]),
        default="safe",
        envvar="ATLAWIRE_TEST_MODE",
    )
    @click.option("--token", envvar="ATLAWIRE_TEST_TOKEN", required=True)
    def deploy(
        target: str,
        dry_run: bool,
        mode: str,
        token: str,
    ) -> None:
        """Deploy to TARGET."""
        raise AssertionError("catalog executed a command callback")

    catalog = build_command_catalog(root)

    assert catalog["name"] == "root"
    assert catalog["help"] == "Root tools."
    entry = command_entry(catalog, "deploy")
    assert entry["help"] == "Deploy to TARGET."

    params = params_by_name(entry)
    assert params["target"]["param_type_name"] == "argument"
    assert params["target"]["required"] is True

    options = options_by_flag(entry)
    assert "--help" not in options
    assert options["--dry-run"]["param_type_name"] == "option"
    assert options["--dry-run"]["required"] is False
    assert options["--dry-run"]["type"]["param_type"] == "Bool"
    assert options["--mode"]["type"]["param_type"] == "Choice"
    assert list(options["--mode"]["type"]["choices"]) == ["safe", "fast"]
    assert options["--mode"]["default"] == "safe"
    assert options["--mode"]["envvar"] == "ATLAWIRE_TEST_MODE"
    assert options["--token"]["required"] is True
    assert options["--token"]["envvar"] == "ATLAWIRE_TEST_TOKEN"


def test_catalog_omits_hidden_commands_and_hidden_parameters() -> None:
    @click.group("visible-root")
    def root() -> None:
        """Visible root."""

    @root.command("visible")
    @click.option("--shown", help="Shown option.")
    @click.option("--internal", hidden=True)
    def visible(shown: str, internal: str) -> None:
        """Visible command."""

    @root.command("internal", hidden=True)
    def internal() -> None:
        """Hidden command."""

    catalog = build_command_catalog(root)

    assert set(cast(dict[str, object], catalog["commands"])) == {"visible"}
    assert set(options_by_flag(command_entry(catalog, "visible"))) == {"--shown"}


def test_catalog_does_not_evaluate_or_render_unsafe_defaults() -> None:
    calls: list[str] = []

    class Untouchable:
        def __repr__(self) -> str:
            raise AssertionError("unsafe default was rendered")

    def lazy_default() -> str:
        calls.append("default")
        return "synthetic-default"

    @click.group("defaults")
    def root() -> None:
        """Default tools."""

    @root.command("run")
    @click.option("--lazy", default=lazy_default)
    @click.option("--opaque", default=Untouchable())
    @click.option("--not-a-number", default=float("nan"))
    def run(lazy: str, opaque: object, not_a_number: float) -> None:
        calls.append("callback")

    catalog = build_command_catalog(root)

    assert calls == []
    options = options_by_flag(command_entry(catalog, "run"))
    for flag in ("--lazy", "--opaque", "--not-a-number"):
        assert "default" not in options[flag]
    assert "default_omitted" not in json.dumps(catalog, allow_nan=False)


def test_real_cli_catalog_contains_every_registered_command() -> None:
    catalog = build_command_catalog(cli)
    commands = cast(dict[str, dict[str, object]], catalog["commands"])
    expected_commands = {
        name: command for name, command in cli.commands.items() if not command.hidden
    }

    assert catalog["name"] == cli.name
    assert catalog["help"] == cli.help
    assert set(commands) == set(expected_commands)

    for name, command in expected_commands.items():
        entry = commands[name]
        assert entry["name"] == name
        assert entry["help"] == command.help

        expected_params = {
            param.name: param
            for param in command.params
            if not getattr(param, "hidden", False)
        }
        described_params = params_by_name(entry)
        assert set(described_params) == set(expected_params)
        for param_name, original in expected_params.items():
            described = described_params[param_name]
            assert described["required"] is original.required
            # The catalog contract is native JSON, so Click's tuples are
            # compared after the same JSON round-trip callers observe.
            expected_type = json.loads(json.dumps(original.type.to_info_dict()))
            assert described["type"] == expected_type
            expected_envvar = original.envvar if original.envvar else None
            assert described.get("envvar") == expected_envvar


def test_real_cli_catalog_describes_repos_and_pr_parameters() -> None:
    catalog = build_command_catalog(cli)

    repos = params_by_name(command_entry(catalog, "repos"))
    assert repos["project"]["param_type_name"] == "argument"
    assert repos["base_url"]["envvar"] == "ATLAWIRE_BITBUCKET_URL"
    assert repos["as_json"]["opts"] == ["--json"]
    assert repos["max_pages"]["default"] == 100
    assert all(
        "--help" not in cast(list[str], p.get("opts", [])) for p in repos.values()
    )

    pr = command_entry(catalog, "pr")
    pr_params = params_by_name(pr)
    assert pr_params["repo"]["required"] is True
    assert pr_params["action"]["required"] is False
    side = options_by_flag(pr)["--side"]
    assert side["type"]["param_type"] == "Choice"
    assert list(side["type"]["choices"]) == ["new", "old"]
    assert side["default"] is None


def test_real_cli_catalog_never_embeds_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "ATLAWIRE_BITBUCKET_URL": "synthetic-value-bb-url-4f8d",
        "ATLAWIRE_BITBUCKET_TOKEN": "synthetic-value-bb-token-4f8d",
        "ATLAWIRE_JIRA_URL": "synthetic-value-jira-url-4f8d",
        "ATLAWIRE_JIRA_TOKEN": "synthetic-value-jira-token-4f8d",
        "ATLAWIRE_CONFLUENCE_URL": "synthetic-value-confluence-url-4f8d",
        "ATLAWIRE_CONFLUENCE_TOKEN": "synthetic-value-confluence-token-4f8d",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    encoded = json.dumps(build_command_catalog(cli), allow_nan=False)

    for name, value in values.items():
        assert value not in encoded
        assert name in encoded


def test_catalog_needs_no_credentials_and_does_no_network(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    missing_credentials = Path(os.environ["BBK_CREDENTIALS"])
    assert not missing_credentials.exists()

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("catalog attempted I/O or credential/network access")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(cli_module, "resolve_saved_credentials", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)

    catalog = build_command_catalog(cli)

    assert catalog["commands"]
    assert str(missing_credentials) not in json.dumps(catalog)
    assert capfd.readouterr() == ("", "")


def test_catalog_is_strict_json_serializable() -> None:
    catalog = build_command_catalog(cli)

    encoded = json.dumps(catalog, allow_nan=False)

    assert json.loads(encoded) == catalog

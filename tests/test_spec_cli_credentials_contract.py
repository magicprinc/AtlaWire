"""Pin the credential contract every command shares, before the CLI refactor.

The refactor may move code between modules and replace repeated wiring with a
decorator. These tests state what must not change for a caller: a single-product
command takes the same three options, reads its own product's environment pair,
and reports a missing credential with exit 2 and a message naming the variable.
"""

import click
import pytest
from click.testing import CliRunner

from atlawire.cli import cli

# Commands that resolve no product pair: local, credential management, metadata.
NO_CREDENTIALS = frozenset({"login", "selftest", "operations"})
# Commands that read several products at once: they take per-product environment
# pairs, so a single --base-url would be ambiguous.
MULTI_PRODUCT = frozenset({"find", "whoami"})

STANDARD_OPTIONS = {"--base-url", "--token-from-env", "--allow-http-loopback"}

PRODUCT_ENV = {
    "jira": ("ATLAWIRE_JIRA_URL", "ATLAWIRE_JIRA_TOKEN"),
    "confluence": ("ATLAWIRE_CONFLUENCE_URL", "ATLAWIRE_CONFLUENCE_TOKEN"),
    "bitbucket": ("ATLAWIRE_BITBUCKET_URL", "ATLAWIRE_BITBUCKET_TOKEN"),
}


def catalog() -> dict[str, dict]:
    """Return the Click command table, the same way the other CLI tests do."""
    with click.Context(cli) as context:
        return context.to_info_dict()["command"]["commands"]


CATALOG = catalog()


def options_of(name: str) -> set[str]:
    params = CATALOG[name].get("params") or []
    return {
        option
        for param in params
        for option in (param.get("opts") or [])
        if option.startswith("--")
    }


def single_product_commands() -> list[str]:
    return sorted(set(CATALOG) - NO_CREDENTIALS - MULTI_PRODUCT)


def test_every_single_product_command_takes_the_three_standard_options():
    """A command that resolves one pair must let the caller override it."""
    missing = {}
    for name in single_product_commands():
        absent = STANDARD_OPTIONS - options_of(name)
        if absent:
            missing[name] = sorted(absent)
    assert missing == {}


def test_the_token_option_names_a_product_variable_or_says_it_is_selected():
    """A caller must be able to tell which variable the option reads."""
    unclear = {}
    for name in CATALOG:
        help_text = next(
            (
                param.get("help") or ""
                for param in CATALOG[name].get("params") or []
                if "--token-from-env" in (param.get("opts") or [])
            ),
            None,
        )
        if help_text is None:
            continue
        if not help_text.strip():
            unclear[name] = "(no help text)"
        elif "ATLAWIRE" not in help_text and "selected product" not in help_text:
            unclear[name] = help_text
    assert unclear == {}


@pytest.mark.parametrize(
    ("product", "argv"),
    [
        ("jira", ["jira-me"]),
        ("confluence", ["spaces", "--limit", "1"]),
        ("bitbucket", ["projects", "--limit", "1"]),
    ],
)
def test_a_missing_environment_pair_exits_two_and_names_the_variable(product, argv):
    """Environment mode never falls back to the saved file, and it says what is missing."""
    url_var, token_var = PRODUCT_ENV[product]

    result = CliRunner().invoke(
        cli, [*argv, "--token-from-env"], env={url_var: "", token_var: ""}
    )

    assert result.exit_code == 2, result.output
    combined = result.stdout + result.stderr
    assert url_var in combined or token_var in combined


def test_no_command_accepts_a_token_as_an_argument():
    """A token on the command line would land in shell history."""
    offenders = [
        name
        for name in CATALOG
        if any(
            option in {"--token", "--password", "--pat"}
            for param in CATALOG[name].get("params") or []
            for option in (param.get("opts") or [])
        )
    ]
    assert offenders == []


@pytest.mark.parametrize("name", ["issue", "page", "repos", "jql", "cql"])
def test_help_declares_the_three_options(name):
    """Click wiring survived: the options are declared and rendered."""
    assert name in CATALOG, f"{name} is not a command"
    missing = STANDARD_OPTIONS - options_of(name)
    assert missing == set(), f"{name} is missing {missing}"
    help_result = CliRunner().invoke(cli, [name, "--help"])
    assert help_result.exit_code == 0, help_result.output
    for option in STANDARD_OPTIONS:
        assert option in help_result.stdout, f"{name} --help omits {option}"


def test_the_multi_product_commands_are_the_only_single_url_less_ones():
    """Guard the exclusion list, so a new command cannot silently skip the options."""
    without_base_url = {
        name for name in CATALOG if "--base-url" not in options_of(name)
    }
    assert without_base_url == {"find", "operations", "selftest", "whoami"}, (
        "a command lost --base-url without being declared multi-product"
    )

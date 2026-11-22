"""Build a JSON-serializable description of the AtlaWire Click group."""

import math
from collections.abc import Mapping
from typing import cast

import click

__all__ = ["build_command_catalog"]


def build_command_catalog(group: click.Group) -> dict[str, object]:
    """Return the flat command metadata used for agent self-description.

    Click's documented ``Context.to_info_dict()`` supplies the schema and
    performs the traversal without running command callbacks. Only hidden
    commands and parameters plus the generated help option are removed.
    Defaults that are not JSON scalars are dropped without being called or
    rendered, and environment metadata is copied as names only.
    """
    with click.Context(group) as context:
        described = context.to_info_dict()

    root = cast(dict[str, object], described["command"])
    raw_commands = cast(dict[str, dict[str, object]], root.get("commands", {}))
    commands = {
        name: _command_entry(command)
        for name, command in raw_commands.items()
        if command.get("hidden") is not True
    }
    return cast(
        dict[str, object],
        _json_value(
            {
                "name": root.get("name"),
                "help": root.get("help"),
                "commands": commands,
            }
        ),
    )


def _command_entry(raw: dict[str, object]) -> dict[str, object]:
    entry = dict(raw)
    raw_params = cast(list[dict[str, object]], raw.get("params", []))
    entry["params"] = [
        _parameter_entry(param)
        for param in raw_params
        if param.get("hidden") is not True and not _is_help_option(param)
    ]
    return entry


def _json_value(value: object) -> object:
    """Return native JSON containers instead of Click's tuples.

    Click reports ``Choice.choices`` as a tuple. Encoding works, but decoding
    yields a list, so a caller comparing its own metadata with the parsed
    catalog must not compare ``tuple`` and ``list`` differently.
    """
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _parameter_entry(raw: dict[str, object]) -> dict[str, object]:
    entry = dict(raw)
    default = entry.get("default")
    if default is not None and not _is_json_scalar(default):
        entry.pop("default")
    return entry


def _is_json_scalar(value: object) -> bool:
    if isinstance(value, (bool, int, str)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _is_help_option(raw: dict[str, object]) -> bool:
    return "--help" in cast(list[str], raw.get("opts", []))

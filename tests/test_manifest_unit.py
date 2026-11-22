"""Contracts for the generated read manifest.

The manifest is derived from the versioned endpoint mappings. These tests check
the derived routes and their local validation independently of the registry
description, so a wrong path or a dropped argument fails.
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import cast
from urllib.parse import quote

import pytest

from atlawire import operations
from atlawire.operations import list_operations, read_operation

MANIFEST = json.loads(
    (Path(__file__).parents[1] / "src/atlawire/manifest.json").read_text(
        encoding="utf-8"
    )
)
OPERATIONS = cast(list[dict[str, object]], MANIFEST["operations"])
DEFERRED = cast(list[dict[str, object]], MANIFEST["deferred"])
PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
BASE = "https://example.invalid"


_CANDIDATES = (
    "1",
    "ABC-1",
    "ABC",
    "value1",
    "x",
    "0123456789abcdef0123456789abcdef01234567",
)
_SLASH_CANDIDATES = ("src/main.java", "dir/file.java", "a/b")


def _sample(argument: dict[str, object]) -> str:
    pattern = re.compile(cast(str, argument["pattern"]))
    candidates = _SLASH_CANDIDATES if argument.get("allow_slash") else _CANDIDATES
    for candidate in candidates:
        parts = candidate.split("/")
        if all(pattern.fullmatch(part) for part in parts):
            return candidate
    raise AssertionError(f"no sample matches {pattern.pattern}")


def _expected_url(entry: dict[str, object], arguments: dict[str, str]) -> str:
    path = cast(str, entry["path"])
    for name, value in arguments.items():
        encoded = "/".join(quote(part, safe="") for part in value.split("/"))
        path = path.replace("{" + name + "}", encoded)
        path = path.replace("{" + name + ":.*}", encoded)
    return f"{BASE}{path}"


def test_manifest_has_unique_well_formed_get_routes() -> None:
    assert OPERATIONS
    keys = set()
    for entry in OPERATIONS:
        assert entry["method"] == "GET"
        path = cast(str, entry["path"])
        assert path.startswith("/rest/")
        assert "//" not in path
        key = (entry["product"], entry["method"], path)
        assert key not in keys, f"duplicate route {key}"
        keys.add(key)

        argument_names = [
            cast(str, argument["name"])
            for argument in cast(list[dict[str, object]], entry["arguments"])
        ]
        placeholders = {
            match.group(1).removesuffix(":.*") for match in PLACEHOLDER.finditer(path)
        }
        assert set(argument_names) == placeholders
        assert len(argument_names) == len(set(argument_names))


def test_deferred_routes_state_a_reason() -> None:
    reasons = [cast(str, item["reason"]) for item in DEFERRED]

    assert DEFERRED
    assert all(item.get("product") and item.get("path") for item in DEFERRED)
    assert all(reasons)
    assert sum("non-JSON body" in reason for reason in reasons) == 8
    assert sum("semantic POST" in reason for reason in reasons) == 3
    assert sum("inconsistently" in reason for reason in reasons) == 1
    assert sum("administrative" in reason for reason in reasons) == 9
    # Every required row is either registered or explicitly deferred.
    assert len(OPERATIONS) + len(DEFERRED) == 211


def test_registry_advertises_every_manifest_route() -> None:
    advertised = {
        (entry["product"], entry["method"], entry["path"])
        for entry in list_operations()
    }

    for entry in OPERATIONS:
        assert (
            entry["product"],
            entry["method"],
            entry["path"],
        ) in advertised


@contextmanager
def _capturing_transport(
    object_payload: dict[str, object] | None = None,
    array_item: dict[str, object] | None = None,
) -> Iterator[list[str]]:
    seen: list[str] = []
    obj = object_payload or {}

    def fake_any(session: object, url: str, *, params: object) -> object:
        seen.append(url)
        return obj

    def fake_array(session: object, url: str, *, params: object) -> object:
        seen.append(url)
        return [array_item] if array_item is not None else []

    def fake_object(session: object, url: str, *, params: object) -> object:
        seen.append(url)
        return obj

    originals = {
        "bearer_session": operations.bearer_session,
        "get_json_any": operations.get_json_any,
        "get_json_array": operations.get_json_array,
        "get_json_object": operations.get_json_object,
        "get_json_object_allow_no_content": (
            operations.get_json_object_allow_no_content
        ),
    }

    operations.bearer_session = lambda token: nullcontext(None)  # type: ignore[assignment]
    operations.get_json_any = fake_any  # type: ignore[assignment]
    operations.get_json_array = fake_array  # type: ignore[assignment]
    operations.get_json_object = fake_object  # type: ignore[assignment]
    operations.get_json_object_allow_no_content = fake_object  # type: ignore[assignment]
    try:
        yield seen
    finally:
        operations.bearer_session = originals["bearer_session"]  # type: ignore[assignment]
        operations.get_json_any = originals["get_json_any"]  # type: ignore[assignment]
        operations.get_json_array = originals["get_json_array"]  # type: ignore[assignment]
        operations.get_json_object = originals["get_json_object"]  # type: ignore[assignment]
        operations.get_json_object_allow_no_content = originals[  # type: ignore[assignment]
            "get_json_object_allow_no_content"
        ]


def _query_sample(field: dict[str, object]) -> object:
    if field.get("type") == "integer":
        minimum = field.get("minimum")
        return minimum if isinstance(minimum, int) else 1
    if field.get("format"):
        return "PRJ/repo"
    allowed = cast(list[object], field.get("enum") or [])
    if allowed:
        return allowed[0]
    return "value1"


def _typed(kind: object) -> object:
    return {"string": "x", "integer": 1, "boolean": True}.get(str(kind), {})


def _payload_for(
    response: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Build a minimal response satisfying the registered shape."""
    if response.get("kind") == "array":
        item = {
            cast(str, field["name"]): _typed(field["type"])
            for field in cast(list[dict[str, object]], response["items_required"])
        }
        return None, item
    if response.get("kind") == "object":
        payload = {
            cast(str, field["name"]): _typed(field["type"])
            for field in cast(list[dict[str, object]], response["required"])
        }
        for name in cast(list[str], response["optional_object_arrays"]):
            payload[name] = []
        return payload, None
    return {}, None


@pytest.mark.parametrize(
    "entry", OPERATIONS, ids=[cast(str, row["id"]) for row in OPERATIONS]
)
def test_every_route_renders_exactly_its_documented_path(
    entry: dict[str, object],
) -> None:
    registered = {
        (row["product"], row["method"], row["path"]): row for row in list_operations()
    }
    operation = registered[(entry["product"], entry["method"], entry["path"])]
    arguments = {
        cast(str, argument["name"]): _sample(argument)
        for argument in cast(list[dict[str, object]], operation["arguments"])
    }
    fields = {
        cast(str, field["name"]): field
        for field in cast(list[dict[str, object]], operation["query"])
    }
    rules = cast(dict[str, list[str]], operation["query_rules"])
    needed = {name for name, field in fields.items() if field.get("required")}
    for rule in ("exactly_one", "at_least_one"):
        names = rules.get(rule) or []
        if names:
            needed.add(names[0])
    query = {name: _query_sample(fields[name]) for name in sorted(needed)}

    response = cast(dict[str, object], operation["response"])
    object_payload, array_item = _payload_for(response)

    with _capturing_transport(object_payload, array_item) as seen:
        read_operation(
            cast(str, operation["id"]),
            BASE,
            token="synthetic-manifest-token",
            arguments=arguments,
            query=query or None,
        )

    assert seen == [_expected_url(entry, arguments)]


def test_registry_never_advertises_an_administrative_route() -> None:
    from atlawire.sdk import _ADMIN_SEGMENTS

    offenders = [
        entry["id"]
        for entry in list_operations()
        if {part.lower() for part in entry["path"].split("/") if part} & _ADMIN_SEGMENTS
    ]

    assert offenders == []

"""Resolve one product's matched URL and token from saved BBK credentials.

AtlaWire does not import BBK. It reads only the per-user JSON schema that BBK
documents, so an owner who already configured BBK can authorize read-only
AtlaWire commands without copying a token into the environment. Diagnostics stay
generic: a failed read never echoes the file, its contents, or a token.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from atlawire.http import AtlaWireError, normalize_base_url

PRODUCTS = ("bitbucket", "confluence", "jira")
CREDENTIALS_ENV = "BBK_CREDENTIALS"
_DEFAULT_PATH = Path(".config") / "atlassian" / "credentials.json"
_MAX_FILE_SIZE = 1024 * 1024
_BEARER_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]+")
_UNAVAILABLE = "Saved BBK credentials are unavailable for {product}."
_INVALID = "Saved BBK credentials are invalid for {product}."
_MISMATCH = "The supplied base URL does not match saved BBK credentials for {product}."


@dataclass(frozen=True, slots=True)
class SavedCredentials:
    """One product's normalized base URL and token from the shared BBK file."""

    base_url: str
    token: str = field(repr=False)


def credentials_path() -> Path:
    """Return the BBK credentials path, honoring ``BBK_CREDENTIALS``."""
    override = os.environ.get(CREDENTIALS_ENV)
    if override:
        return Path(override)
    return Path.home() / _DEFAULT_PATH


def _read_document(product: str) -> dict[str, object]:
    """Read one bounded JSON object without exposing file contents."""
    try:
        with credentials_path().open("rb") as stream:
            raw = stream.read(_MAX_FILE_SIZE + 1)
    except OSError:
        raise AtlaWireError(_UNAVAILABLE.format(product=product)) from None
    if len(raw) > _MAX_FILE_SIZE:
        raise AtlaWireError(_INVALID.format(product=product))
    try:
        document = json.loads(raw.decode("utf-8"))
    except ValueError, RecursionError:
        raise AtlaWireError(_INVALID.format(product=product)) from None
    if not isinstance(document, dict):
        raise AtlaWireError(_INVALID.format(product=product))
    return document


def load_saved_credentials(
    product: str, *, allow_http_loopback: bool
) -> SavedCredentials:
    """Load exactly one product's matched pair from the saved BBK file.

    Both ``<product>_url`` and ``<product>_token`` must be present, non-empty,
    and valid. There is no fallback to another product's entry and no mixing of
    a URL from one entry with a token from another.
    """
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product: {product}.")
    document = _read_document(product)
    url = document.get(f"{product}_url")
    token = document.get(f"{product}_token")
    if (
        not isinstance(url, str)
        or not isinstance(token, str)
        or _BEARER_TOKEN.fullmatch(token) is None
    ):
        raise AtlaWireError(_INVALID.format(product=product))
    try:
        base_url = normalize_base_url(url, allow_http_loopback=allow_http_loopback)
    except AtlaWireError:
        raise AtlaWireError(_INVALID.format(product=product)) from None
    return SavedCredentials(base_url=base_url, token=token)


def resolve_saved_credentials(
    product: str,
    *,
    supplied_base_url: str | None,
    allow_http_loopback: bool,
) -> SavedCredentials:
    """Return saved credentials only for the saved destination.

    An optional ``--base-url`` or product URL from the environment is an
    override request. It is accepted only when it normalizes to the saved
    product URL, so a saved token can never be sent to a different destination.
    """
    credentials = load_saved_credentials(
        product, allow_http_loopback=allow_http_loopback
    )
    if supplied_base_url is None:
        return credentials
    supplied = normalize_base_url(
        supplied_base_url, allow_http_loopback=allow_http_loopback
    )
    if supplied != credentials.base_url:
        raise AtlaWireError(_MISMATCH.format(product=product))
    return credentials

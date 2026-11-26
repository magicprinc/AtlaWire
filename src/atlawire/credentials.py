"""Resolve one product's matched URL and token from saved BBK credentials.

AtlaWire does not import BBK. It reads only the per-user JSON schema that BBK
documents, so an owner who already configured BBK can authorize read-only
AtlaWire commands without copying a token into the environment. Diagnostics stay
generic: a failed read never echoes the file, its contents, or a token.

[save_credentials][atlawire.credentials.save_credentials] writes the same
schema. It exists so a token can go from a hidden prompt straight to disk
without appearing in an argument list, a shell history, or a terminal echo.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from atlawire.file_publication import (
    create_temporary_file,
    discard_temporary_file,
    replace_file,
)
from atlawire.http import BEARER_TOKEN_GRAMMAR, AtlaWireError, normalize_base_url

PRODUCTS = ("bitbucket", "confluence", "jira")
CREDENTIALS_ENV = "BBK_CREDENTIALS"
_DEFAULT_PATH = Path(".config") / "atlassian" / "credentials.json"
_MAX_FILE_SIZE = 1024 * 1024
_UNAVAILABLE = "Saved BBK credentials are unavailable for {product}."
_INVALID = "Saved BBK credentials are invalid for {product}."
_MISMATCH = "The supplied base URL does not match saved BBK credentials for {product}."
_SAVE_INVALID = "The provided base URL or token is invalid."
_SAVE_EXISTING_INVALID = (
    "The saved credentials file is not a JSON object; fix or remove it before saving."
)
_SAVE_WRITE_FAILED = "Could not write the saved credentials file."
_FILE_MODE = 0o600
_DIRECTORY_MODE = 0o700


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
        raise AtlaWireError(
            _UNAVAILABLE.format(product=product),
            category="credentials",
            product=product,
        ) from None
    if len(raw) > _MAX_FILE_SIZE:
        raise AtlaWireError(
            _INVALID.format(product=product), category="credentials", product=product
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except ValueError, RecursionError:
        raise AtlaWireError(
            _INVALID.format(product=product), category="credentials", product=product
        ) from None
    if not isinstance(document, dict):
        raise AtlaWireError(
            _INVALID.format(product=product), category="credentials", product=product
        )
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
        or BEARER_TOKEN_GRAMMAR.fullmatch(token) is None
    ):
        raise AtlaWireError(
            _INVALID.format(product=product), category="credentials", product=product
        )
    try:
        base_url = normalize_base_url(url, allow_http_loopback=allow_http_loopback)
    except AtlaWireError:
        raise AtlaWireError(
            _INVALID.format(product=product), category="credentials", product=product
        ) from None
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
        raise AtlaWireError(
            _MISMATCH.format(product=product),
            category="credentials",
            product=product,
        )
    return credentials


def _existing_document() -> dict[str, object]:
    """Return the current credentials document, or an empty one.

    A missing file is an empty document. A file that exists but cannot be read
    as a JSON object is refused instead of replaced: another product's saved
    token may be in it, and saving must never destroy what it cannot read.
    """
    if not credentials_path().exists():
        return {}
    try:
        return _read_document("credentials")
    except AtlaWireError:
        raise AtlaWireError(_SAVE_EXISTING_INVALID, category="credentials") from None


def save_credentials(
    product: str,
    base_url: str,
    token: str,
    *,
    allow_http_loopback: bool = False,
) -> Path:
    """Write one product's URL and token into the saved credentials file.

    The destination and the token are validated with the same rules the reader
    applies, so a saved pair always loads. Existing entries for other products
    and unrelated keys are preserved. The document is staged beside the
    destination and renamed over it, so a concurrent reader sees either the old
    file or the new one, and the file is created with owner-only permissions.

    Neither the token nor the document contents are ever included in an error.
    """
    if product not in PRODUCTS:
        raise ValueError(f"Unknown product: {product}.")
    if BEARER_TOKEN_GRAMMAR.fullmatch(token) is None:
        raise AtlaWireError(_SAVE_INVALID, category="credentials", product=product)
    try:
        base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    except AtlaWireError:
        raise AtlaWireError(
            _SAVE_INVALID, category="credentials", product=product
        ) from None
    document = _existing_document()
    document[f"{product}_url"] = base
    document[f"{product}_token"] = token
    _write_document(document, product=product)
    return credentials_path()


def _write_document(document: dict[str, object], *, product: str) -> None:
    """Stage the document beside the destination and rename it into place."""
    path = credentials_path()
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            _restrict_directory(path.parent)
        temporary = create_temporary_file(path)
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temporary, path, mode=_FILE_MODE)
    except AtlaWireError as exc:
        raise AtlaWireError(
            _SAVE_WRITE_FAILED, category="credentials", product=product
        ) from exc
    except OSError:
        raise AtlaWireError(
            _SAVE_WRITE_FAILED, category="credentials", product=product
        ) from None
    finally:
        if temporary is not None:
            discard_temporary_file(temporary)


def _restrict_directory(directory: Path) -> None:
    """Best-effort owner-only directory mode; an ACL may already be stricter."""
    try:
        os.chmod(directory, _DIRECTORY_MODE)
    except OSError:
        return

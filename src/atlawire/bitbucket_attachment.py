"""Read-only download of one Bitbucket Server repository attachment.

The route appears in the legacy BBK client (``bbk/write.py``,
``attachment_download``) as a fixed ``GET`` on
``/rest/api/1.0/projects/{project}/repos/{slug}/attachments/{attachment}``.
The local Bitbucket Server 5.10 core reference does not document it. Support is
therefore BBK-observed only and depends on the installed plugin and server
version; it is not verified here.

This module issues exactly one authenticated ``GET`` against the configured
origin, returns the response bytes to the caller, never writes a local file, and
never follows a response link or redirect.
"""

import re
from urllib.parse import quote

import requests

from atlawire.http import (
    AtlaWireError,
    _check_status,
    bearer_session,
    normalize_base_url,
    read_encoded_limited,
    reject_credential_echo,
)

# Shared grammar: a Bitbucket key is not a Jira key, so the concept is imported.
from atlawire.identifiers import BITBUCKET_PROJECT_KEY as _PROJECT_KEY
from atlawire.identifiers import REPOSITORY_SLUG as _REPOSITORY_SLUG

__all__ = ["get_repository_attachment"]

# One path segment only: an alphanumeric lead excludes ``.``, ``..``, a leading
# separator and an empty value. The remaining set excludes ``/``, ``\``, ``%``
# and every character a proxy could reinterpret as an escape or separator.
_ATTACHMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_INVALID_REPO = "Expected a repository as PROJECT/slug."
_INVALID_ATTACHMENT_ID = "Expected a single attachment ID segment."
_INVALID_MAX_BYTES = "The attachment size limit must be a positive integer."
# The caller-visible default transport bound. It matches the shared 8 MiB JSON
# response budget in atlawire.http; it is not a claim about attachment sizes.
_DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def get_repository_attachment(
    base_url: str,
    repo: str,
    attachment_id: str,
    *,
    token: str,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    allow_http_loopback: bool = False,
) -> bytes:
    """Return the exact bytes of one repository attachment.

    ``repo`` is ``PROJECT/slug``. ``attachment_id`` must be one path segment: an
    alphanumeric lead followed by letters, digits, ``.``, ``_`` or ``-``. Both
    identities are validated before any request, and the URL is rebuilt from the
    normalized configured origin and those validated values; a response body or
    link is never used to choose a destination.

    The single authenticated request is ``GET`` on
    ``/rest/api/1.0/projects/{project}/repos/{slug}/attachments/{attachment}``
    with ``Accept: */*``, the shared bearer session, the shared 5 s connect and
    30 s read timeouts, redirects disabled, and the shared read-only status
    policy. A redirect, HTTP 206, authentication or authorization failure, or
    any other non-2xx status raises without returning bytes.

    ``max_bytes`` is the caller's explicit positive bound on the returned
    content, counted after content decoding. Its 8 MiB default matches the
    shared JSON response budget; it is a transport bound, not a statement about
    expected attachment sizes. A body larger than the bound raises; it is never
    truncated, and no partial content is returned. A gzip body is decoded with
    a validating decoder, so an incomplete member (missing or corrupt trailer)
    raises the shared generic transport error instead of returning its prefix.

    The returned value is the exact response body for a successful read; bytes
    that are not part of the response are never added. Before returning, the
    body is checked with the shared credential guard through an ASCII-preserving
    Latin-1 view, so a literal token or a common percent/base64 spelling in the
    body raises the shared generic error instead of returning those bytes. The
    guard reads a separate text view and never mutates the returned bytes. As
    with the shared guard, substring matching means a short or common token can
    collide with ordinary data; rejecting that case is the deliberate
    fail-closed trade-off.

    The response is closed on every path, and the session is closed when this
    function returns or raises. Nothing is written to local storage. Diagnostics
    never contain the URL, path, attachment ID, body or credential.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    identifier = _attachment_id(attachment_id)
    limit = _max_bytes(max_bytes)
    url = (
        f"{base}/rest/api/1.0/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/attachments/{quote(identifier, safe='')}"
    )
    with bearer_session(token, product="bitbucket") as session:
        try:
            with session.get(
                url,
                headers={"Accept": "*/*"},
                timeout=(5, 30),
                allow_redirects=False,
                stream=True,
            ) as response:
                _check_status(response.status_code, product="bitbucket")
                payload = read_encoded_limited(
                    response,
                    limit=limit,
                    message=f"The attachment exceeds the {limit}-byte limit.",
                )
        except requests.Timeout:
            raise AtlaWireError("Request timed out.") from None
        except requests.RequestException:
            raise AtlaWireError(
                "Request failed; check connectivity and TLS settings."
            ) from None
    _reject_payload_token_echo(payload, token)
    return payload


def _split_repo(repo: str) -> tuple[str, str]:
    """Validate ``PROJECT/slug`` exactly like the shared Bitbucket adapter.

    The shared validator is duplicated rather than imported because this module
    is owned independently of ``atlawire.bitbucket``; the accepted forms must
    stay identical.
    """
    if not isinstance(repo, str):
        raise AtlaWireError(_INVALID_REPO)
    project, separator, slug = repo.partition("/")
    if (
        not separator
        or "/" in slug
        or not _PROJECT_KEY.fullmatch(project)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError(_INVALID_REPO)
    return project, slug


def _attachment_id(value: str) -> str:
    """Accept exactly one safe attachment ID path segment."""
    if not isinstance(value, str) or not _ATTACHMENT_ID.fullmatch(value):
        raise AtlaWireError(_INVALID_ATTACHMENT_ID)
    return value


def _max_bytes(value: int) -> int:
    """Require a positive integer bound; ``bool`` is not a byte count."""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AtlaWireError(_INVALID_MAX_BYTES)
    return value


def _reject_payload_token_echo(payload: bytes, token: str) -> None:
    """Reject bytes that expose the active token without changing them.

    Latin-1 is a total, one-code-point-per-byte mapping that preserves every
    ASCII character, so literal and ASCII-encoded token spellings are visible to
    the shared guard. The decode creates a separate text view; ``payload`` is
    returned unchanged when the guard accepts it.
    """
    reject_credential_echo(payload.decode("latin-1"), tokens=(token,))

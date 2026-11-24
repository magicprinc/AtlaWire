"""Check which self-hosted Atlassian products accept the caller's credentials.

This is the read-only counterpart of BBK's ``whoami``: each of the three
products is probed with its own explicit base URL and token, and the result
reports every product independently. BBK's probe is corrected here:

* BBK read ``/rest/api/1.0/application-properties`` for Bitbucket and treated a
  200 response as proof of authentication. That route is anonymous on Bitbucket
  Server, so it proves only that the server answers. AtlaWire instead reads the
  authenticated dashboard and reports access, never an invented identity.
* Confluence's documented ``/rest/api/user/current`` answers an anonymous
  caller with HTTP 200, so a successful status alone proves nothing. The
  ``type``, ``username``, and ``displayName`` fields are validated as one
  identity, and an anonymous or non-identity result is reported as a failure.
* No base URL, token, response body, or server-returned link is printed or
  followed. Diagnostics name the product and one closed-set reason only.

Target versions are documented, not live-verified here. Jira uses the existing
``/rest/api/2/myself`` adapter (Jira Software Server 8.3). Confluence requires
the ``CurrentUser`` object of the 6.6.0 REST documentation: ``type`` is exactly
``known`` and ``username`` is non-empty. A later Confluence version that returns
only ``accountId`` fails closed rather than reporting a weak success. Bitbucket
uses the Server 5.10 dashboard route, which requires authentication; an empty
dashboard page is still an authenticated read.
"""

import re
from collections.abc import Callable, Mapping
from typing import TypedDict

from atlawire.bitbucket import list_my_pull_requests
from atlawire.federated import ProductTarget
from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)
from atlawire.jira import get_current_user

__all__ = [
    "CONFLUENCE_CURRENT_USER_PATH",
    "ConfluenceIdentity",
    "IdentityCheck",
    "JiraIdentity",
    "whoami",
]

CONFLUENCE_CURRENT_USER_PATH = "/rest/api/user/current"
_BEARER_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]+")
_HTTP_STATUS = re.compile(r"HTTP ([0-9]{3}):")
_NO_IDENTITY = "Expected an authenticated identity with readable text."
_TIMEOUT = "Request timed out."
_CONNECTION_FAILURE = "Request failed;"


class ConfluenceIdentity(TypedDict):
    """The authenticated Confluence user's documented identity fields."""

    username: str
    displayName: str | None


class JiraIdentity(TypedDict):
    """The authenticated Jira user's identity fields without contact data."""

    name: str
    displayName: str | None


class IdentityCheck(TypedDict, total=False):
    """One product's explicit success or failure entry.

    A success carries ``ok`` plus either ``identity`` (Confluence and Jira) or
    ``authenticated`` (Bitbucket, whose identity is deliberately not read). A
    failure carries ``ok`` and one generic, sanitized ``error``.
    """

    ok: bool
    identity: ConfluenceIdentity | JiraIdentity
    authenticated: bool
    error: str


class _NoIdentity(AtlaWireError):
    """The product answered without a readable authenticated identity."""


class _InvalidTarget(AtlaWireError):
    """The explicit product pair is missing or invalid; no request was sent."""


def whoami(
    *,
    confluence: ProductTarget | None,
    jira: ProductTarget | None,
    bitbucket: ProductTarget | None,
    allow_http_loopback: bool = False,
) -> dict[str, IdentityCheck]:
    """Probe all three products and report each one independently.

    ``confluence``, ``jira``, and ``bitbucket`` are separate explicit pairs.
    ``None`` means the caller could not supply that product's matched pair.
    Each product receives only its own base URL and token: Confluence
    ``GET {base}/rest/api/user/current``, Jira
    ``GET {base}/rest/api/2/myself``, and the Bitbucket Server dashboard
    ``GET {base}/rest/api/1.0/dashboard/pull-requests`` through
    [list_my_pull_requests][atlawire.bitbucket.list_my_pull_requests] with
    ``limit=1``.

    Returns one JSON-serializable object keyed in ``confluence``, ``jira``,
    ``bitbucket`` order:

    * ``{"ok": True, "identity": {"username": ..., "displayName": ...}}`` for a
      Confluence ``CurrentUser`` whose ``type`` is ``known``;
    * ``{"ok": True, "identity": {"name": ..., "displayName": ...}}`` for Jira
      (the email address is not reported because this check is not a profile
      read);
    * ``{"ok": True, "authenticated": True}`` for Bitbucket, whose dashboard
      read proves authenticated access but yields no identity here;
    * ``{"ok": False, "error": "<Product> check failed: <reason>."}`` for a
      failed product.

    A failure never stops the other probes and is never reported as a success,
    matching BBK's explicit partial reporting. ``error`` contains only the
    product name and a reason from a closed set (``authentication rejected``,
    ``access denied``, ``redirect refused``, ``partial response refused``,
    ``request failed``, ``request timed out``, ``connection failed``,
    ``configuration is missing or invalid``,
    ``no authenticated identity was returned``, or ``unexpected response``), so
    no token, base URL, response body, or server-supplied link can leak.

    Every pair is validated inside its own probe, immediately before that
    product's first request. A ``None`` pair, or one whose URL or token is
    invalid, fails only that product with the sanitized configuration reason;
    no request is sent for it, and the other products are still probed. Thus
    this function does not raise for a missing or invalid product pair.
    """
    checks: dict[str, IdentityCheck] = {}
    checks["confluence"] = _run(
        "Confluence",
        lambda: _confluence_check(confluence, allow_http_loopback),
    )
    checks["jira"] = _run(
        "Jira",
        lambda: _jira_check(jira, allow_http_loopback),
    )
    checks["bitbucket"] = _run(
        "Bitbucket",
        lambda: _bitbucket_check(bitbucket, allow_http_loopback),
    )
    return checks


def _run(product: str, probe: Callable[[], IdentityCheck]) -> IdentityCheck:
    """Return one probe's success or a sanitized failure without stopping."""
    try:
        return probe()
    except AtlaWireError as exc:
        return IdentityCheck(ok=False, error=f"{product} check failed: {_reason(exc)}.")


def _confluence_check(
    target: ProductTarget | None, allow_http_loopback: bool
) -> IdentityCheck:
    """Validate one pair, then read the documented current user."""
    resolved = _target("Confluence", target, allow_http_loopback)
    with bearer_session(resolved.token, product="confluence") as session:
        user = get_json_object(
            session,
            f"{resolved.base_url}{CONFLUENCE_CURRENT_USER_PATH}",
            params={},
        )
    return IdentityCheck(ok=True, identity=_confluence_identity(user))


def _confluence_identity(value: dict[str, object]) -> ConfluenceIdentity:
    """Reject anonymous, unknown, and non-identity Confluence results.

    Confluence 6.6.0 documents ``type`` as ``known``, ``anonymous``, or
    ``unknown`` and gives anonymous callers HTTP 200. Only ``known`` with a
    non-empty ``username`` is an authenticated identity; no fallback to
    ``userKey`` or ``accountId`` is attempted because those fields are not part
    of the documented 6.6.0 object and would weaken the check.
    """
    if value.get("type") != "known":
        raise _NoIdentity(_NO_IDENTITY)
    return ConfluenceIdentity(
        username=_required_identity_text(value.get("username")),
        displayName=_optional_identity_text(value.get("displayName")),
    )


def _jira_check(
    target: ProductTarget | None, allow_http_loopback: bool
) -> IdentityCheck:
    """Validate one pair, then project only the promised identity fields."""
    resolved = _target("Jira", target, allow_http_loopback)
    user = get_current_user(
        resolved.base_url,
        token=resolved.token,
        allow_http_loopback=allow_http_loopback,
    )
    if not isinstance(user, Mapping):
        raise _NoIdentity(_NO_IDENTITY)
    return IdentityCheck(ok=True, identity=_jira_identity(user))


def _jira_identity(user: Mapping[str, object]) -> JiraIdentity:
    """Keep the name and display name; never report the email address."""
    return JiraIdentity(
        name=_required_identity_text(user.get("name")),
        displayName=_optional_identity_text(user.get("displayName")),
    )


def _bitbucket_check(
    target: ProductTarget | None, allow_http_loopback: bool
) -> IdentityCheck:
    """Validate one pair, then prove authenticated dashboard access.

    The dashboard route requires authentication on Bitbucket Server 5.10, so a
    complete empty page still confirms access. No current-user endpoint is
    called, and no name is derived from a page: the result reports only that the
    authenticated read succeeded.
    """
    resolved = _target("Bitbucket", target, allow_http_loopback)
    list_my_pull_requests(
        resolved.base_url,
        token=resolved.token,
        limit=1,
        allow_http_loopback=allow_http_loopback,
    )
    return IdentityCheck(ok=True, authenticated=True)


def _required_identity_text(value: object) -> str:
    """Return one required identity field that must be non-blank UTF-8 text."""
    if not isinstance(value, str) or not value.strip():
        raise _NoIdentity(_NO_IDENTITY)
    _check_utf8(value)
    return value


def _optional_identity_text(value: object) -> str | None:
    """Return an absent optional field or require readable text for it."""
    if value is None:
        return None
    return _required_identity_text(value)


def _check_utf8(value: str) -> None:
    """Reject text that the UTF-8 output layer cannot represent."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _NoIdentity(_NO_IDENTITY) from None


def _reason(exc: AtlaWireError) -> str:
    """Map one adapter failure to a closed, sanitized reason.

    The exception text is compared and never copied. The adapters own these
    exact messages, and echoing arbitrary exception text could publish a base
    URL or a response fragment from a future or replaced adapter.
    """
    if isinstance(exc, _NoIdentity):
        return "no authenticated identity was returned"
    if isinstance(exc, _InvalidTarget):
        return "configuration is missing or invalid"
    text = str(exc)
    match = _HTTP_STATUS.match(text)
    if match is not None:
        status = int(match.group(1))
        if status == 401:
            return "authentication rejected"
        if status == 403:
            return "access denied"
        if 300 <= status < 400:
            return "redirect refused"
        if status == 206:
            return "partial response refused"
        return "request failed"
    if text == _TIMEOUT:
        return "request timed out"
    if text.startswith(_CONNECTION_FAILURE):
        return "connection failed"
    return "unexpected response"


def _target(product: str, value: object, allow_http_loopback: bool) -> ProductTarget:
    """Validate one explicit pair and normalize only its destination.

    Every rejection is ``_InvalidTarget``: it becomes that product's sanitized
    configuration failure and is never allowed to stop the other probes. The
    messages name only the product, because the reason mapping never echoes
    them.
    """
    if not isinstance(value, ProductTarget):
        raise _InvalidTarget(
            f"Expected an explicit {product} base URL and token pair.",
            category="credentials",
            product=product,
        )
    if not isinstance(value.base_url, str) or not isinstance(value.token, str):
        raise _InvalidTarget(
            f"The {product} base URL or token is invalid.",
            category="credentials",
            product=product,
        )
    try:
        base_url = normalize_base_url(
            value.base_url, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError:
        raise _InvalidTarget(
            f"The {product} base URL is invalid.",
            category="validation",
            product=product,
        ) from None
    if _BEARER_TOKEN.fullmatch(value.token) is None:
        raise _InvalidTarget(
            f"The {product} token is missing or invalid.",
            category="credentials",
            product=product,
        )
    return ProductTarget(base_url=base_url, token=value.token)

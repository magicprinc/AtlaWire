"""Read-only facade over atlassian-python-api.

The library owns client construction, authentication, the base URL and the
session. This module adds the read-only boundary the library does not provide:
one validated route per call, refused redirects, a bounded streamed body, one
retry policy, and an error object that keeps the HTTP status and a sanitized
diagnostic excerpt.
"""

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import requests
from atlassian import Bitbucket, ConfluenceServer, Jira
from atlassian.rest_client import AtlassianRestAPI

from atlawire.file_publication import (
    create_temporary_file,
    discard_temporary_file,
    publish_new_file,
)
from atlawire.http import (
    _TRANSPORT_MESSAGE,
    AtlaWireError,
    _NoRedirectSession,
    error_detail,
    normalize_base_url,
    read_encoded_limited,
    reject_credential_echo,
    reject_side_effect_query,
)

__all__ = [
    "SdkRequestError",
    "client_for",
    "download_to_file",
    "get_json",
    "get_json_with_status",
    "request_json",
    "request_json_with_status",
]

Product = Literal["jira", "confluence", "bitbucket"]
_MAX_PATH = 2048
_UNSAFE_PATH = re.compile(r"[\\\x00-\x20\x7f?#]")
_ADMIN_SEGMENTS = frozenset(
    {
        "admin",
        "application-properties",
        "applicationrole",
        "audit",
        "auditing",
        "cluster",
        "issuetypescheme",
        "issuesecurityschemes",
        "license",
        "logs",
        "mail-server",
        "notificationscheme",
        "permissions",
        "permissionscheme",
        "priorityschemes",
        "reindex",
        "screens",
        "settings",
        "workflow",
        "workflows",
        "workflowscheme",
    }
)
logging.getLogger("atlassian").setLevel(logging.WARNING)

_CLIENTS = {
    "jira": Jira,
    "confluence": ConfluenceServer,
    "bitbucket": Bitbucket,
}


def _supported_product(product: object) -> str | None:
    """Return the product name only when it is one of the fixed supported names.

    Pre-request errors run before ``_raw_client_for`` validates the product, so
    an arbitrary caller string must not reach structured metadata.
    """
    return product if isinstance(product, str) and product in _CLIENTS else None


# Each semantic-read POST belongs to exactly one product. A Confluence
# conversion sent through the Jira client is a product mismatch, not a read.
_READ_ONLY_POSTS: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "jira": (frozenset({"/rest/api/2/search", "/rest/api/2/worklog/list"}), ()),
    "bitbucket": (frozenset({"/rest/api/1.0/markup/preview"}), ()),
    "confluence": (frozenset(), ("/rest/api/contentbody/convert/",)),
}

# Shared read budgets, measured on content-decoded bytes read from the stream.
_JSON_LIMIT = 8 * 1024 * 1024
_BINARY_LIMIT = 32 * 1024 * 1024
_BODY_LIMIT = 8 * 1024
_TIMEOUT = (5, 30)
_CHUNK = 64 * 1024

# One retry owner: this adapter. Chosen client defaults, not a measured SLA.
_MAX_ATTEMPTS = 3
_RETRY_BUDGET = 5.0
_RETRY_STATUSES = frozenset({429, 503})
_BACKOFF_SECONDS = (1.0, 2.0)

# One message for every local staging failure: the CLI reports it as JSON.
_LOCAL_WRITE_MESSAGE = "Could not write the destination file."


_TRANSPORT_CLASSIFICATIONS = frozenset({"transport", "timeout"})
_UPSTREAM_CLASSIFICATIONS = frozenset({"invalid_response", "response_too_large"})
# Only categories that describe an arrived response keep the real status.
_STATUS_CATEGORIES = frozenset({"http", "upstream"})


def _error_category(status: int | None, classification: str) -> str | None:
    """Map the adapter classification to the public category without guessing."""
    if classification in _TRANSPORT_CLASSIFICATIONS:
        return "transport"
    if classification in _UPSTREAM_CLASSIFICATIONS:
        return "upstream"
    if status is not None:
        return "http"
    return None


class SdkRequestError(AtlaWireError):
    """One failed library request with the original response preserved."""

    def __init__(
        self,
        *,
        status: int | None,
        code: str,
        classification: str,
        message: str,
        body: str | None,
        content_type: str | None,
        path: str,
        body_truncated: bool = False,
        product: str | None = None,
        method: str | None = None,
        detail: str | None = None,
    ) -> None:
        category = _error_category(status, classification)
        super().__init__(
            message,
            product=product,
            category=category,
            http_status=(
                status
                if category in _STATUS_CATEGORIES and status is not None
                else None
            ),
            method=method,
            path=path,
            detail=detail,
        )
        self.status = status
        self.code = code
        self.classification = classification
        self.message = message
        self.body = body
        self.content_type = content_type
        self.path = path
        self.body_truncated = body_truncated

    def to_dict(self, *, product: str, token: str) -> dict[str, object]:
        body = _redact(self.body, token)
        parsed: object | None = None
        if body:
            try:
                parsed = _strict_json(body)
            except ValueError, RecursionError:
                parsed = None
        return {
            "ok": False,
            "product": product,
            "error": {
                "status": self.status,
                "code": self.code,
                "classification": self.classification,
                "message": self.message,
                "path": self.path,
                "content_type": self.content_type,
                "body": body,
                "body_json": parsed,
                "body_truncated": self.body_truncated,
            },
        }


def _redact(value: str | None, token: str) -> str | None:
    if value is None or not token:
        return value
    return value.replace(token, "[REDACTED]")


def _non_finite(value: str) -> object:
    """Reject ``NaN``/``Infinity``: neither belongs in a JSON contract."""
    raise ValueError(f"Non-finite JSON value: {value}.")


def _finite_float(value: str) -> float:
    """Reject a JSON number that leaves the finite double range.

    ``json.loads`` maps an overflowing literal such as ``1e999`` to ``inf``
    without consulting ``parse_constant``, which only sees the bare ``NaN`` and
    ``Infinity`` spellings. The float hook is therefore the only place the
    finite-only contract can hold for exponent notation.
    """
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite JSON value: {value}.")
    return number


def _strict_json(text: str) -> object:
    return json.loads(text, parse_constant=_non_finite, parse_float=_finite_float)


def _classify(status: int | None) -> tuple[str, str]:
    if status is None:
        return "transport_error", "transport"
    if status == 401:
        return "http_401", "authentication"
    if status == 403:
        return "http_403", "authorization"
    if status == 404:
        return "http_404", "not_found"
    if status == 429:
        return "http_429", "rate_limited"
    if 300 <= status < 400:
        return f"http_{status}", "unexpected_redirect"
    if 400 <= status < 500:
        return f"http_{status}", "client_error"
    if 500 <= status < 600:
        return f"http_{status}", "server_error"
    return f"http_{status}", "unexpected_status"


def _raw_client_for(
    product: str,
    base_url: str,
    token: str,
    *,
    allow_http_loopback: bool = False,
) -> AtlassianRestAPI:
    """Create the underlying library client for the internal facade.

    The library builds a stock [requests.Session][requests.Session] unless one
    is supplied. Such a session honours ambient ``netrc``/proxy/CA settings and
    its ``resolve_redirects`` generator pre-reads a refused redirect body before
    the status reaches this adapter. The session is therefore created here as a
    no-redirect session with ``trust_env`` disabled and handed to the library,
    which then applies its own headers, auth, verify/cert and proxy state on top
    of it.
    """
    client_class = _CLIENTS.get(product)
    if client_class is None:
        raise AtlaWireError("Unknown Atlassian product.", category="validation")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    session = _NoRedirectSession()
    # Ambient netrc/proxy/CA state must not alter the explicit transport.
    session.trust_env = False
    return client_class(
        url=base,
        token=token,
        cloud=False,
        timeout=_TIMEOUT[1],
        verify_ssl=True,
        session=session,
        # The library must not retry: this module owns attempts and delays.
        backoff_and_retry=False,
    )


_MUTATING = re.compile(
    r"(?:^|_)(?:add|create|delete|update|set|remove|archive|restore|move|"
    r"assign|transition|do|post|put|upload|edit|rename|merge|close|disable|"
    r"enable|register|unregister|pin|unpin|watch|unwatch|vote|unvote|mark|"
    r"unmark|bulk|change|copy|reset|clean|reindex|start|cancel|approve|"
    r"decline|write|deactivate|reopen|open|grant|attach|trigger|revoke|"
    r"publish|schedule|execute|send|notify|invite|subscribe|unsubscribe|"
    r"follow|unfollow|save|push|sync|import|install|uninstall|migrate|"
    r"login|logout|apply|rollback|detach|unlink)(?:_|$)",
    re.IGNORECASE,
)
_RAW_TRANSPORT = frozenset({"request", "get", "post", "put", "delete", "patch"})
# Plain metadata that is safe to read from a caller; every other non-callable
# attribute stays private, including the underlying transport session.
_SAFE_METADATA = frozenset(
    {"timeout", "cloud", "backoff_and_retry", "verify_ssl", "url"}
)


class ReadOnlyClient:
    """Proxy that exposes only non-mutating library methods and safe metadata.

    A named attribute is forwarded only when it is a callable library method and
    its name passes the mutating-name and raw-verb filters. ``timeout``,
    ``cloud``, ``backoff_and_retry``, ``verify_ssl`` and ``url`` are exposed as
    read-only metadata. Every other name, including the underlying
    ``session``/``_session`` transport state, raises ``AttributeError``; the raw
    client stays reachable only through the private ``_client`` attribute.
    """

    # Класс-аннотация обязательна: без неё обращение к ``self._client``
    # разрешается через ``__getattr__`` и получает выведенный тип возврата,
    # а не реальный близкий клиент библиотеки.
    _client: AtlassianRestAPI

    def __init__(self, client: AtlassianRestAPI) -> None:
        object.__setattr__(self, "_client", client)

    def __getattr__(self, name: str):
        client = object.__getattribute__(self, "_client")
        if name in _SAFE_METADATA:
            return getattr(client, name)
        if name.startswith("_") or name in _RAW_TRANSPORT or _MUTATING.search(name):
            raise AttributeError(f"Read-only client does not expose {name}.")
        candidate = getattr(client, name)
        if callable(candidate):
            return candidate
        raise AttributeError(f"Read-only client does not expose {name}.")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def client_for(
    product: str,
    base_url: str,
    token: str,
    *,
    allow_http_loopback: bool = False,
) -> ReadOnlyClient:
    """Create one read-only library client; the caller must close it."""
    return ReadOnlyClient(
        _raw_client_for(
            product,
            base_url,
            token,
            allow_http_loopback=allow_http_loopback,
        )
    )


def get_json(
    product: str,
    base_url: str,
    path: str,
    *,
    token: str,
    params: Mapping[str, object] | None = None,
    allow_http_loopback: bool = False,
) -> object:
    """Read one standard non-admin JSON GET through the library client."""
    return request_json(
        product,
        base_url,
        path,
        method="GET",
        token=token,
        params=params,
        allow_http_loopback=allow_http_loopback,
    )


def get_json_with_status(
    product: str,
    base_url: str,
    path: str,
    *,
    token: str,
    params: Mapping[str, object] | None = None,
    allow_http_loopback: bool = False,
) -> tuple[int, object]:
    """Read one JSON GET and return ``(status, payload)``."""
    return request_json_with_status(
        product,
        base_url,
        path,
        method="GET",
        token=token,
        params=params,
        allow_http_loopback=allow_http_loopback,
    )


def request_json(
    product: str,
    base_url: str,
    path: str,
    *,
    method: str,
    token: str,
    params: Mapping[str, object] | None = None,
    body: Mapping[str, object] | None = None,
    allow_http_loopback: bool = False,
) -> object:
    """Read one standard non-admin JSON endpoint and return its payload."""
    return request_json_with_status(
        product,
        base_url,
        path,
        method=method,
        token=token,
        params=params,
        body=body,
        allow_http_loopback=allow_http_loopback,
    )[1]


def request_json_with_status(
    product: str,
    base_url: str,
    path: str,
    *,
    method: str,
    token: str,
    params: Mapping[str, object] | None = None,
    body: Mapping[str, object] | None = None,
    allow_http_loopback: bool = False,
    allow_admin: bool = False,
) -> tuple[int, object]:
    """Read one standard JSON endpoint with its HTTP status.

    ``allow_admin`` opens the administrative path guard for a call whose
    registered scope is admin; the registry refuses such an operation first.

    Exactly one route is requested per attempt. Redirects are refused rather
    than followed, the body is read in bounded chunks, and retries are owned
    here: at most three total attempts and five seconds of scheduled waits for
    dropped connections and the two retryable statuses. A TLS certificate
    failure is deterministic and is reported once, without retrying.
    HTTP errors keep their status; a failure without a response has
    ``status=None``, while a body that is interrupted after the status line
    keeps the real status and is reported as a transport error.
    """
    normalized = method.upper()
    if normalized not in {"GET", "POST"}:
        raise AtlaWireError(
            "Only read-only GET and POST are supported.",
            category="validation",
            product=_supported_product(product),
        )
    _validate_path(path, product=product, allow_admin=allow_admin)
    if normalized == "POST":
        _check_semantic_post(product, path)
    if normalized == "GET" and body is not None:
        raise AtlaWireError(
            "A GET request cannot carry a JSON body.",
            category="validation",
            product=_supported_product(product),
            method="GET",
        )
    if normalized == "POST" and body is None:
        raise AtlaWireError(
            "A POST request requires a JSON body.",
            category="validation",
            product=_supported_product(product),
            method="POST",
        )

    client = _raw_client_for(
        product, base_url, token, allow_http_loopback=allow_http_loopback
    )
    try:
        status, payload = _attempt_loop(
            client,
            normalized,
            path,
            params=_checked_params(params, product=product),
            body=dict(body) if body is not None else None,
            retryable=normalized == "GET",
            product=product,
        )
    finally:
        client.close()
    if payload is not None:
        reject_credential_echo(payload, tokens=(token,))
    return status, payload


def download_to_file(
    product: str,
    base_url: str,
    path: str,
    *,
    token: str,
    destination: str | Path,
    params: Mapping[str, object] | None = None,
    max_bytes: int = _BINARY_LIMIT,
    allow_http_loopback: bool = False,
    allow_admin: bool = False,
) -> tuple[str | None, int, str]:
    """Read one bounded read-only response into a file and return its receipt.

    The destination must not exist. Bytes are written to an exclusive sibling
    temporary file and published atomically only after a complete, bounded
    read; a destination created during publication is refused, never replaced.
    On any failure the temporary file is removed and nothing is published.
    Only HTTP 200 is a successful file read: 206 is rejected as incomplete
    partial content, every other non-200 status is one ``invalid_response``
    error that keeps the status, and a body interrupted after the status line
    is reported as one transport error that keeps the real status. A request
    that fails before any response is one ``transport_error`` with no status.
    A local staging failure (directory, temporary file, write) is one
    [AtlaWireError][atlawire.http.AtlaWireError] instead of a traceback. None of
    these paths leaves a published file, a receipt or a staging ``.part`` name.
    """
    target = Path(destination)
    if target.exists():
        raise AtlaWireError(
            "The destination already exists.",
            category="validation",
            product=_supported_product(product),
        )
    _validate_path(path, product=product, allow_admin=allow_admin)
    if max_bytes < 1:
        raise AtlaWireError(
            "The byte limit must be a positive integer.",
            category="validation",
            product=_supported_product(product),
        )
    client = _raw_client_for(
        product, base_url, token, allow_http_loopback=allow_http_loopback
    )
    temporary: Path | None = None
    try:
        temporary = _create_staging_file(target)
        response = _send_binary(
            client,
            path,
            _checked_params(params, product=product),
            product=product,
        )
        try:
            written, digest = _write_binary_body(
                response, temporary, path, max_bytes, product=product
            )
        finally:
            response.close()
        content_type = response.headers.get("Content-Type")
        publish_new_file(temporary, target)
        return content_type, written, digest
    finally:
        client.close()
        if temporary is not None:
            discard_temporary_file(temporary)


def _create_staging_file(target: Path) -> Path:
    """Create the destination directory and one exclusive staging file."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        return create_temporary_file(target)
    except OSError:
        raise AtlaWireError(_LOCAL_WRITE_MESSAGE) from None


def _send_binary(
    client: AtlassianRestAPI,
    path: str,
    params: dict[str, str | int],
    *,
    product: str,
) -> requests.Response:
    """Send one binary GET; a pre-response failure is one transport error."""
    try:
        return _send(client, "GET", path, params=params, body=None)
    except requests.RequestException:
        raise SdkRequestError(
            status=None,
            code="transport_error",
            classification="transport",
            message=_TRANSPORT_MESSAGE,
            body=None,
            content_type=None,
            path=path,
            product=product,
            method="GET",
        ) from None


def _write_binary_body(
    response: requests.Response,
    temporary: Path,
    path: str,
    max_bytes: int,
    *,
    product: str,
) -> tuple[int, str]:
    """Validate the status, then read and write one complete bounded body."""
    status = response.status_code
    if 300 <= status < 400:
        raise _error(
            response,
            path=path,
            code=f"http_{status}",
            classification="unexpected_redirect",
            message="The server returned a redirect; it was not followed.",
            product=product,
            method="GET",
        )
    if status >= 400:
        code, classification = _classify(status)
        raise _error(
            response,
            path=path,
            code=code,
            classification=classification,
            message=f"HTTP {status}: request failed.",
            product=product,
            method="GET",
        )
    if status == 206:
        # A partial body is never the complete representation the
        # receipt promises, even when the server chose to send 206
        # without a Range request.
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="partial_content",
            message="HTTP 206: partial content is not a supported read.",
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            product=product,
            method="GET",
        )
    if status != 200:
        # A file read promises the complete representation; only 200 is one.
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="unexpected_status",
            message=f"HTTP {status}: a file read requires a complete 200 response.",
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            product=product,
            method="GET",
        )
    try:
        payload = read_encoded_limited(
            response,
            limit=max_bytes,
            message=f"The response exceeds the {max_bytes}-byte limit.",
        )
    except AtlaWireError as exc:
        if exc.category == "transport":
            # An interrupted or undecodable body must not surface as a
            # traceback or leave a partial file behind.
            raise SdkRequestError(
                status=status,
                code="transport_error",
                classification="transport",
                message=_TRANSPORT_MESSAGE,
                body=None,
                content_type=response.headers.get("Content-Type"),
                path=path,
                product=product,
                method="GET",
            ) from None
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="response_too_large",
            message=f"The response exceeds the {max_bytes}-byte limit.",
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            body_truncated=True,
            product=product,
            method="GET",
        ) from None
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
    except OSError:
        raise AtlaWireError(_LOCAL_WRITE_MESSAGE) from None
    return len(payload), hashlib.sha256(payload).hexdigest()


def _check_semantic_post(product: str, path: str) -> None:
    exact, prefixes = _READ_ONLY_POSTS.get(product, (frozenset(), ()))
    if path in exact or path.startswith(prefixes):
        return
    raise AtlaWireError(
        "This POST endpoint is not read-only for this product.",
        category="validation",
        product=_supported_product(product),
    )


def _checked_params(
    params: Mapping[str, object] | None, *, product: str
) -> dict[str, str | int]:
    """Accept only scalar query values, so encoding is predictable."""
    reject_side_effect_query(params, product=product)
    checked: dict[str, str | int] = {}
    for name, value in (params or {}).items():
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise AtlaWireError(
                "Query parameters must be strings or integers.",
                category="validation",
                product=_supported_product(product),
            )
        checked[name] = value
    return checked


def _attempt_loop(
    client: AtlassianRestAPI,
    method: str,
    path: str,
    *,
    params: dict[str, str | int],
    body: dict[str, object] | None,
    retryable: bool,
    product: str,
) -> tuple[int, object]:
    waited = 0.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = _send(client, method, path, params=params, body=body)
        except requests.Timeout:
            delay = _pause(attempt, waited, None) if retryable else None
            if delay is None:
                raise SdkRequestError(
                    status=None,
                    code="timeout",
                    classification="timeout",
                    message="Request timed out.",
                    body=None,
                    content_type=None,
                    path=path,
                    product=product,
                    method=method,
                ) from None
            if delay:
                time.sleep(delay)
            waited += delay
            continue
        except requests.exceptions.SSLError:
            # A certificate rejection is deterministic: another attempt cannot
            # turn it into a success, so it is reported once with no status.
            raise SdkRequestError(
                status=None,
                code="transport_error",
                classification="transport",
                message=_TRANSPORT_MESSAGE,
                body=None,
                content_type=None,
                path=path,
                product=product,
                method=method,
            ) from None
        except requests.ConnectionError:
            delay = _pause(attempt, waited, None) if retryable else None
            if delay is None:
                raise SdkRequestError(
                    status=None,
                    code="transport_error",
                    classification="transport",
                    message=_TRANSPORT_MESSAGE,
                    body=None,
                    content_type=None,
                    path=path,
                    product=product,
                    method=method,
                ) from None
            if delay:
                time.sleep(delay)
            waited += delay
            continue
        except requests.RequestException:
            raise SdkRequestError(
                status=None,
                code="transport_error",
                classification="transport",
                message=_TRANSPORT_MESSAGE,
                body=None,
                content_type=None,
                path=path,
                product=product,
                method=method,
            ) from None

        try:
            return _consume(
                response,
                path,
                attempt,
                waited,
                retryable=retryable,
                product=product,
                method=method,
            )
        except _Retry as retry:
            waited = retry.waited
            continue
        finally:
            response.close()

    raise SdkRequestError(  # pragma: no cover - the loop returns or raises
        status=None,
        code="transport_error",
        classification="transport",
        message="Request failed.",
        body=None,
        content_type=None,
        path=path,
        product=product,
        method=method,
    )


class _Retry(Exception):
    """Internal signal: one bounded wait was scheduled and fits the budget."""

    def __init__(self, waited: float) -> None:
        super().__init__("retry")
        self.waited = waited


def _pause(attempt: int, waited: float, retry_after: float | None) -> float | None:
    """Return an allowed delay, or ``None`` when no further attempt fits."""
    if attempt >= _MAX_ATTEMPTS:
        return None
    if retry_after is not None:
        delay = retry_after
    else:
        delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
    if delay < 0 or waited + delay > _RETRY_BUDGET:
        return None
    return delay


def _send(
    client: AtlassianRestAPI,
    method: str,
    path: str,
    *,
    params: dict[str, str | int],
    body: dict[str, object] | None,
) -> requests.Response:
    """Send one request through the library session, without following it."""
    url = f"{str(client.url).rstrip('/')}{path}"
    return client.session.request(
        method,
        url,
        params=params or None,
        data=json.dumps(body) if body is not None else None,
        headers=({"Content-Type": "application/json"} if body is not None else None),
        timeout=_TIMEOUT,
        allow_redirects=False,
        stream=True,
    )


def _consume(
    response: requests.Response,
    path: str,
    attempt: int,
    waited: float,
    *,
    retryable: bool,
    product: str,
    method: str,
) -> tuple[int, object]:
    """Validate status and return the decoded JSON, or schedule one retry."""
    status = response.status_code
    if 300 <= status < 400:
        raise _error(
            response,
            path=path,
            code=f"http_{status}",
            classification="unexpected_redirect",
            message="The server returned a redirect; it was not followed.",
            product=product,
            method=method,
        )
    if status >= 400:
        delay = (
            _pause(attempt, waited, _retry_after(response))
            if retryable and status in _RETRY_STATUSES
            else None
        )
        if delay is not None:
            if delay:
                time.sleep(delay)
            raise _Retry(waited + delay)
        code, classification = _classify(status)
        raise _error(
            response,
            path=path,
            code=code,
            classification=classification,
            message=f"HTTP {status}: request failed.",
            product=product,
            method=method,
        )

    if status == 206:
        # A partial body is never a complete read, even without a Range header.
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="partial_content",
            message="HTTP 206: partial content is not a supported read.",
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            product=product,
            method=method,
        )

    try:
        payload = _read_limited(response, _JSON_LIMIT)
    except _TooLarge:
        # The success body is already over budget; do not keep reading a
        # diagnostic excerpt from the remainder of that same body.
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="response_too_large",
            message=f"The JSON response exceeds the {_JSON_LIMIT}-byte limit.",
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            body_truncated=True,
            product=product,
            method=method,
        ) from None
    except AtlaWireError:
        # A truncated or undecodable gzip member: the shared reader already
        # kept the diagnostic generic.
        raise SdkRequestError(
            status=status,
            code="transport_error",
            classification="transport",
            message=_TRANSPORT_MESSAGE,
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            product=product,
            method=method,
        ) from None
    except requests.RequestException:
        # The status line arrived but the body did not: the request is neither a
        # success nor an HTTP-status failure, so keep the real status and report
        # one sanitized transport error.
        raise SdkRequestError(
            status=status,
            code="transport_error",
            classification="transport",
            message=_TRANSPORT_MESSAGE,
            body=None,
            content_type=response.headers.get("Content-Type"),
            path=path,
            product=product,
            method=method,
        ) from None
    if not payload:
        if status == 204:
            # Documented no-content: the caller decides whether this route
            # allows it. A 200 with an empty body stays an error.
            return status, None
        raise _error(
            response,
            path=path,
            code="invalid_response",
            classification="invalid_response",
            message="The response body is empty; JSON was expected.",
            product=product,
            method=method,
        )
    try:
        return status, _strict_json(payload.decode("utf-8"))
    except UnicodeDecodeError, ValueError, RecursionError:
        body, truncated = _excerpt(payload)
        raise SdkRequestError(
            status=status,
            code="invalid_response",
            classification="invalid_response",
            message="The response body is not valid JSON.",
            body=body,
            content_type=response.headers.get("Content-Type"),
            path=path,
            body_truncated=truncated,
            product=product,
            method=method,
        ) from None


def _excerpt(payload: bytes) -> tuple[str, bool]:
    """Return a bounded diagnostic excerpt of bytes already read."""
    truncated = len(payload) > _BODY_LIMIT
    raw = payload[:_BODY_LIMIT]
    try:
        return raw.decode("utf-8"), truncated
    except UnicodeDecodeError:
        return raw.decode("latin-1"), truncated


class _TooLarge(Exception):
    pass


def _read_limited(response: requests.Response, limit: int) -> bytes:
    """Read content-decoded bytes under ``limit`` and validate a gzip member.

    The shared reader owns the gzip-trailer check, so a truncated member is a
    transport failure instead of a plausible prefix. An oversize body keeps the
    local ``_TooLarge`` signal, which lets the caller classify it without
    matching diagnostic text.
    """
    try:
        return read_encoded_limited(
            response,
            limit=limit,
            message=f"The JSON response exceeds the {limit}-byte limit.",
        )
    except AtlaWireError as exc:
        if exc.category == "transport":
            raise
        raise _TooLarge from None


def _read_excerpt(response: requests.Response) -> tuple[str | None, bool]:
    """Return a bounded diagnostic excerpt and whether the body was cut."""
    chunks: list[bytes] = []
    total = 0
    truncated = False
    try:
        for chunk in response.iter_content(chunk_size=_CHUNK):
            room = _BODY_LIMIT - total
            if room <= 0 or len(chunk) > room:
                chunks.append(chunk[:room])
                truncated = True
                break
            chunks.append(chunk)
            total += len(chunk)
    except requests.RequestException:
        return None, truncated
    try:
        return b"".join(chunks).decode("utf-8"), truncated
    except UnicodeDecodeError:
        return b"".join(chunks).decode("latin-1"), truncated


def _retry_after(response: requests.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if not header:
        return None
    value = header.strip()
    if value.isascii() and value.isdigit():
        return float(value)
    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def _request_token(response: requests.Response) -> tuple[str, ...]:
    """Return the bearer credential this response's request carried, if any.

    The message is hardened against echoing the credential, and this layer has no
    session object, so the value is read back from the prepared request instead
    of being threaded through every call site.
    """
    request = getattr(response, "request", None)
    headers = getattr(request, "headers", None)
    if not isinstance(headers, Mapping):
        return ()
    value = headers.get("Authorization")
    if not isinstance(value, str):
        return ()
    scheme, separator, token = value.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return ()
    stripped = token.strip()
    return (stripped,) if stripped else ()


def _error(
    response: requests.Response,
    *,
    path: str,
    code: str,
    classification: str,
    message: str,
    product: str,
    method: str,
) -> SdkRequestError:
    body, truncated = _read_excerpt(response)
    if not truncated and body is not None and body.endswith("\n"):
        body = body.rstrip("\n")
    reason: str | None = None
    if message == f"HTTP {response.status_code}: request failed." and body is not None:
        # The typed transport records the documented reason for a rejected
        # request; this layer must not be less useful than the one above it.
        # `error_detail` is the shared, redacted parser, so no body text that is
        # not a documented error field survives, and the message stays generic.
        reason = error_detail(body, tokens=_request_token(response)) or None
    return SdkRequestError(
        status=response.status_code,
        code=code,
        classification=classification,
        message=message,
        body=body,
        detail=reason,
        content_type=response.headers.get("Content-Type"),
        path=path,
        body_truncated=truncated,
        product=product,
        method=method,
    )


def _fully_unquoted(path: str) -> str:
    """Decode every percent-encoding layer until the spelling stops changing.

    ``requests`` normalises a URL with ``requote_uri``, which leaves unreserved
    bytes (letters, digits, ``-._~``) literal. ``%61dmin`` therefore reaches the
    server as ``admin`` and encoded ``..`` as a traversal segment. Decoding to a
    fixed point before the route checks mirrors that normalisation for every
    layer, including double encoding. Each changing pass shortens the string, so
    the loop terminates within the original path length.
    """
    decoded = path
    while True:
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value


def _validate_path(
    path: str, *, product: str | None = None, allow_admin: bool = False
) -> None:
    if (
        not isinstance(path, str)
        or not path.startswith("/rest/")
        or len(path) > _MAX_PATH
        or "//" in path
        or _UNSAFE_PATH.search(path)
    ):
        raise AtlaWireError(
            "Expected a safe standard REST path.",
            category="validation",
            product=_supported_product(product),
        )
    decoded_segments = _fully_unquoted(path).split("/")
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise AtlaWireError(
            "Expected a safe standard REST path.",
            category="validation",
            product=_supported_product(product),
        )
    if not allow_admin and any(
        segment in _ADMIN_SEGMENTS for segment in decoded_segments
    ):
        # The message stays stable and flag-free: `api-get` has no --allow-admin,
        # so suggesting it there would be wrong. The registry refuses an admin
        # operation first and names the flag in its own message.
        raise AtlaWireError(
            "Administrative REST paths are not supported.",
            category="validation",
            product=_supported_product(product),
        )

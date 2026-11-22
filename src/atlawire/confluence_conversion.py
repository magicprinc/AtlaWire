"""Convert one Confluence 6.6 content body through a fixed semantic read POST.

Confluence 6.6 documents ``POST /rest/api/contentbody/convert/{to}`` as a
conversion between content-body representations. The documented source and
destination pairs are:

* ``storage`` to ``view``, ``export_view``, ``styled_view`` or ``editor``;
* ``editor`` to ``storage``.

The request body is a JSON object with exactly ``value`` and ``representation``;
``expand`` is the only accepted query parameter. This module sends one such
request to the configured origin, returns the decoded JSON object unchanged,
and never follows a response link or redirect.

The "read-only" claim is limited to the HTTP method and route. Rendering
storage or editor content can run server-side macros and plugins, and the 6.6
documentation does not establish that every installed plugin is free of side
effects. Treat the call as a semantic read whose server-side effects are not
guaranteed by this client.

Reference:
https://docs.atlassian.com/atlassian-confluence/REST/6.6.0/
"""

from urllib.parse import urlencode

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    normalize_base_url,
    post_json_object,
    reject_credential_echo,
)

__all__ = ["convert_content_body"]

# The 6.6 reference titles the route ``POST /rest/contentbody/convert/{to}``
# while its own example URI includes the ``/rest/api`` context prefix. This
# adapter follows the example and the caller contract; the exact server route
# still needs confirmation against a live 6.6 instance.
_CONVERT_PATH = "/rest/api/contentbody/convert"
_ALLOWED_TARGETS: dict[str, frozenset[str]] = {
    "storage": frozenset({"view", "export_view", "styled_view", "editor"}),
    "editor": frozenset({"storage"}),
}
_INVALID_PAIR = (
    "Expected a supported content body conversion: storage to view, export_view, "
    "styled_view, or editor, or editor to storage."
)
_INVALID_VALUE = "Expected the content body value to be a UTF-8 string."
_INVALID_EXPAND = "Expected expand to be an optional UTF-8 string."
_INVALID_RESPONSE = "Expected a JSON response with value and representation strings."
_REQUEST_ECHO = "The request would include the session bearer token."


def convert_content_body(
    base_url: str,
    value: str,
    *,
    representation: str,
    to: str,
    token: str,
    expand: str | None = None,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Convert one content body and return the raw decoded response object.

    ``representation`` and ``to`` must be one of the documented conversion
    pairs; any other pair is rejected before a session or request is created.
    ``value`` must be a UTF-8 string and may be empty: the 6.6 reference
    publishes no non-empty constraint. ``expand`` is an optional UTF-8 string;
    when supplied, even as an empty string, it is sent as the single fixed
    ``expand`` query parameter with its documented empty default preserved.
    No other query keys or URL parts accept caller input.

    The single request is ``POST`` on
    ``{base_url}/rest/api/contentbody/convert/{to}`` with the shared bearer
    session, the shared 5 s connect and 30 s read timeouts, redirects disabled,
    the shared read-only status policy, and the shared 8 MiB decoded-JSON cap.
    A redirect, HTTP 206, authentication or authorization failure, oversize
    body, malformed or non-UTF-8 JSON, or any other non-2xx status raises a
    generic [AtlaWireError][atlawire.http.AtlaWireError].

    The JSON body contains exactly ``value`` and ``representation``. Before
    anything is transmitted, only the caller-supplied ``value`` and ``expand``
    are checked for the session bearer token and its common percent/base64
    spellings, including a spelling hidden behind one URL re-encoding. Fixed
    protocol text is not credential-derived and is not inspected: the route
    names ``convert``, ``storage``, ``view`` and the other allowlisted
    representations, the JSON keys ``value`` and ``representation``, the query
    key ``expand``, and the text Requests generates by normalizing the URL or
    serializing the body are protocol text, not caller credentials. An echo in
    caller text is refused so the credential never enters the request. The
    configured base URL is trusted configuration rather than caller content and
    is not scanned. The returned object is checked again for the same
    spellings. Diagnostics are trusted generic text: the public wrapper
    re-raises them outside the handler with no chained cause, but does not scan
    them for the token, so an ordinary word such as ``JSON``, ``Error`` or
    ``403`` used as the token never blanks an error. Serialization can spell an
    ASCII token through a Unicode escape when caller text is a single non-ASCII
    code point; that wire spelling is data, not a credential echo. A token
    literally present in caller ``value`` or ``expand`` is still refused before
    transmission, and a server response that echoes the token or an encoding is
    still rejected, both with fixed generic messages.

    The response is required to be a JSON object whose ``value`` and
    ``representation`` are strings, but the returned ``representation`` is not
    required to equal ``to`` or the request representation: the 6.6 example
    itself returns ``storage`` for a conversion to ``view``. Every unknown
    field of a decoded object is preserved unchanged. The response object and
    the session are closed on every path. This adapter imposes no request-size
    cap on ``value`` or ``expand``; the caller already owns those strings, and
    only the response is bounded by the shared transport. Diagnostics never
    contain the URL, path, body, query, returned values or credential.
    """
    message = ""
    try:
        return _convert_content_body(
            base_url,
            value,
            representation=representation,
            to=to,
            token=token,
            expand=expand,
            allow_http_loopback=allow_http_loopback,
        )
    except AtlaWireError as exc:
        message = str(exc)
    # Re-raised outside the handler so the original exception is neither a
    # cause nor a context; the message itself is trusted generic text.
    raise AtlaWireError(message) from None


def _convert_content_body(
    base_url: str,
    value: str,
    *,
    representation: str,
    to: str,
    token: str,
    expand: str | None,
    allow_http_loopback: bool,
) -> dict[str, object]:
    _check_pair(representation, to)
    _check_text(value, _INVALID_VALUE)
    if expand is not None:
        _check_text(expand, _INVALID_EXPAND)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _conversion_url(base, to, expand)
    body = {"value": value, "representation": representation}
    with bearer_session(token) as session:
        # Only caller-supplied text is inspected: the fixed route, keys,
        # representations and serializer output are not credential-derived.
        _reject_caller_echo(value, expand, token=token)
        result = post_json_object(session, url, body=body)
    reject_credential_echo(result, tokens=(token,))
    if not isinstance(result, dict):
        raise AtlaWireError(_INVALID_RESPONSE)
    _check_response(result)
    return result


def _check_pair(representation: object, to: object) -> None:
    """Accept exactly the source/destination matrix published for 6.6."""
    if not isinstance(representation, str) or not isinstance(to, str):
        raise AtlaWireError(_INVALID_PAIR)
    targets = _ALLOWED_TARGETS.get(representation)
    if targets is None or to not in targets:
        raise AtlaWireError(_INVALID_PAIR)


def _check_text(value: object, message: str) -> None:
    """Require a string that can be encoded as strict UTF-8.

    A lone surrogate is syntactically a Python string but cannot be encoded as
    UTF-8, so it is rejected rather than deferred to an internal encoding
    failure after the session exists.
    """
    if not isinstance(value, str):
        raise AtlaWireError(message)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(message) from None


def _conversion_url(base: str, to: str, expand: str | None) -> str:
    """Build the fixed route and the one optional query parameter.

    ``to`` is already allowlisted and ``expand`` is percent-encoded through
    ``urlencode``, so caller text cannot introduce another query key, path
    segment, fragment or authority.
    """
    url = f"{base}{_CONVERT_PATH}/{to}"
    if expand is None:
        return url
    return f"{url}?{urlencode({'expand': expand})}"


def _reject_caller_echo(value: str, expand: str | None, *, token: str) -> None:
    """Refuse a request whose caller-supplied text has the token.

    The shared guard is reused for its established literal, percent and base64
    spellings, but its message describes a response. Only ``value`` and
    ``expand`` are inspected. Fixed protocol text such as the route, JSON keys,
    representations and Requests' serialization output is protocol text rather
    than caller credentials, so treating a coincidence there as an echo would
    reject ordinary conversions for short or common tokens.
    """
    texts: list[object] = [value]
    if expand is not None:
        texts.append(expand)
    try:
        reject_credential_echo(texts, tokens=(token,))
    except AtlaWireError:
        raise AtlaWireError(_REQUEST_ECHO) from None


def _check_response(result: dict[str, object]) -> None:
    """Require the two documented string fields without constraining values."""
    value = result.get("value")
    representation = result.get("representation")
    if not isinstance(value, str) or not isinstance(representation, str):
        raise AtlaWireError(_INVALID_RESPONSE)

"""Shared JSON transport for self-hosted Atlassian reads."""

import math
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

import requests


class AtlaWireError(Exception):
    """An operation failed with a message safe for CLI diagnostics."""


def normalize_base_url(value: str, *, allow_http_loopback: bool) -> str:
    invalid = "Use an HTTPS base URL without credentials, query, or fragment."
    if re.search(r"[\s\\\x00-\x1f\x7f?#]", value):
        raise AtlaWireError(invalid)
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
    except ValueError:
        raise AtlaWireError(invalid) from None
    if not host or "@" in url.netloc or "%" in url.netloc or port == 0:
        raise AtlaWireError(invalid)
    if url.scheme != "https" and not (
        allow_http_loopback and url.scheme == "http" and host in {"127.0.0.1", "::1"}
    ):
        raise AtlaWireError(invalid)
    return value.rstrip("/")


def bearer_session(token: str) -> requests.Session:
    """Create a session that the caller must close."""
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
        raise AtlaWireError("Missing or invalid bearer token.")
    session = requests.Session()
    # Do not let ambient netrc settings replace the explicit Authorization header.
    session.trust_env = False
    session.headers.update(
        {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    return session


def _reject_constant(_: str) -> float:
    raise ValueError("Non-JSON numeric constant.")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number outside the supported range.")
    return number


def get_json_object(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> dict[str, object]:
    try:
        with session.get(
            url, params=params, timeout=(5, 30), allow_redirects=False
        ) as response:
            status = response.status_code
            if 300 <= status < 400:
                raise AtlaWireError(
                    f"HTTP {status}: redirect refused; check the base URL."
                )
            if status == 401:
                raise AtlaWireError("HTTP 401: authentication rejected.")
            if status == 403:
                raise AtlaWireError("HTTP 403: access denied.")
            if not 200 <= status < 300:
                raise AtlaWireError(f"HTTP {status}: request failed.")
            try:
                data: object = response.json(
                    parse_constant=_reject_constant, parse_float=_finite_float
                )
            except ValueError, RecursionError:
                raise AtlaWireError("Expected a valid JSON response.") from None
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    if not isinstance(data, dict):
        raise AtlaWireError("Expected a JSON object.")
    return data

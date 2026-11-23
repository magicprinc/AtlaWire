"""Contract for the one structured error every consumer can branch on.

Each category is driven through a real public entry point: the shared HTTP
transport, the SDK adapter, the operation registry and the credential resolver.
Every test asserts the category, whether ``http_status`` is present, and that a
synthetic sentinel placed in the provider response body or in the raw arguments
never reaches ``str(exc)`` or the formatted traceback.
"""

import time
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Self

import pytest
import requests

from atlawire import http, operations, sdk
from atlawire.credentials import CREDENTIALS_ENV, resolve_saved_credentials
from atlawire.federated import ProductTarget, federated_search
from atlawire.http import AtlaWireError
from atlawire.operations import OperationShapeError, read_operation
from atlawire.pr_review import collect_pr_review
from atlawire.sdk import SdkRequestError, get_json
from tests._loopback import send_bytes, send_json, serving

BASE = "https://atlassian.example.invalid"
TOKEN = "synthetic-contract-token"
OPERATION_ID = "jira.issue.votes"
ARG_SENTINEL = "SYNTHETIC-ARG-SENTINEL-7f3c"
BODY_SENTINEL = "SYNTHETIC-BODY-SENTINEL-7f3c"


def assert_not_leaked(exc: BaseException) -> None:
    """Neither the message nor the formatted traceback may repeat a sentinel."""
    message = str(exc)
    formatted = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    for sentinel in (ARG_SENTINEL, BODY_SENTINEL):
        assert sentinel not in message
        assert sentinel not in formatted


def refuse_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if a pre-request error path reaches the transport."""

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(operations, "bearer_session", refuse)
    monkeypatch.setattr(operations, "sdk_request_json_with_status", refuse)


def test_transport_failure_and_timeout_are_category_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A response whose body is interrupted after the status line still read
    # provider bytes, so the sentinel really was on the wire.
    partial = b'{"synthetic":"SYNTHETIC-BODY-SENTINEL-7f3c"'

    class Interrupted(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(partial) + 64))
            self.end_headers()
            self.wfile.write(partial)
            self.wfile.flush()
            self.close_connection = True

    with serving(Interrupted) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                origin,
                "/rest/api/2/myself",
                token=TOKEN,
                params={"synthetic": ARG_SENTINEL},
                allow_http_loopback=True,
            )

    interrupted = caught.value
    assert interrupted.category == "transport"
    assert interrupted.http_status is None
    assert interrupted.status == 200
    assert interrupted.product == "jira"
    assert interrupted.method == "GET"
    assert interrupted.path == "/rest/api/2/myself"
    assert_not_leaked(interrupted)

    def timeout(*args: object, **kwargs: object) -> requests.Response:
        raise requests.Timeout("synthetic timeout detail")

    monkeypatch.setattr(sdk, "_send", timeout)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    with pytest.raises(SdkRequestError) as timed_out:
        get_json(
            "jira",
            origin,
            "/rest/api/2/myself",
            token=TOKEN,
            params={"synthetic": ARG_SENTINEL},
            allow_http_loopback=True,
        )

    timed = timed_out.value
    assert timed.category == "transport"
    assert timed.http_status is None
    assert timed.status is None
    assert_not_leaked(timed)


def test_http_403_is_category_http_with_the_real_status() -> None:
    class Denied(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(
                self,
                403,
                ('{"message":"' + BODY_SENTINEL + '"}').encode(),
                content_type="application/json",
            )

    with serving(Denied) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                origin,
                "/rest/api/2/myself",
                token=TOKEN,
                params={"synthetic": ARG_SENTINEL},
                allow_http_loopback=True,
            )

    error = caught.value
    assert error.category == "http"
    assert error.http_status == 403
    assert error.product == "jira"
    assert error.method == "GET"
    assert error.path == "/rest/api/2/myself"
    # The excerpt stays available on the attribute, never in the message.
    assert error.body is not None and BODY_SENTINEL in error.body
    assert_not_leaked(error)


def test_a_bad_argument_is_category_validation_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse_transport(monkeypatch)
    with pytest.raises(AtlaWireError) as caught:
        read_operation(
            OPERATION_ID, BASE, token=TOKEN, arguments={"issueIdOrKey": ARG_SENTINEL}
        )

    error = caught.value
    assert not isinstance(error, SdkRequestError | OperationShapeError)
    assert error.category == "validation"
    assert error.product == "jira"
    assert error.operation == OPERATION_ID
    assert error.http_status is None
    assert_not_leaked(error)


def test_an_unknown_operation_is_unknown_operation_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse_transport(monkeypatch)
    with pytest.raises(AtlaWireError) as caught:
        read_operation(ARG_SENTINEL, BASE, token=TOKEN, arguments={})

    error = caught.value
    assert error.category == "unknown_operation"
    assert error.http_status is None
    assert_not_leaked(error)


def test_missing_credentials_is_category_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CREDENTIALS_ENV, str(tmp_path / "absent.json"))
    with pytest.raises(AtlaWireError) as caught:
        resolve_saved_credentials(
            "jira", supplied_base_url=ARG_SENTINEL, allow_http_loopback=False
        )

    error = caught.value
    assert error.category == "credentials"
    assert error.product == "jira"
    assert error.http_status is None
    assert_not_leaked(error)


def test_an_unstructured_response_is_category_upstream() -> None:
    class Unstructured(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_json(self, 200, {"synthetic": BODY_SENTINEL})

    with serving(Unstructured) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(OperationShapeError) as caught:
            read_operation(
                OPERATION_ID,
                origin,
                token=ARG_SENTINEL,
                arguments={"issueIdOrKey": "ABC-1"},
                allow_http_loopback=True,
            )

    error = caught.value
    assert isinstance(error, AtlaWireError)
    assert error.category == "upstream"
    assert error.product == "jira"
    assert error.operation == OPERATION_ID
    assert error.http_status is None
    assert_not_leaked(error)


def test_invalid_jira_credentials_are_reported_as_the_jira_product() -> None:
    # A valid Bitbucket token and an invalid Jira token must blame Jira, the
    # pair that was actually rejected, not the already-validated Bitbucket one.
    with pytest.raises(AtlaWireError) as caught:
        collect_pr_review(
            BASE,
            "PROJ/repository",
            1,
            token=TOKEN,
            jira_base_url="https://jira.example.invalid",
            jira_token=f"{ARG_SENTINEL} invalid",
        )

    error = caught.value
    assert error.category == "credentials"
    assert error.product == "jira"
    assert error.http_status is None
    assert_not_leaked(error)


def test_error_path_never_carries_a_dynamic_secret_segment() -> None:
    # No trusted route template exists at the shared transport layer, so the
    # optional path must stay None instead of echoing a dynamic URL segment.
    url = f"https://atlassian.example.invalid/rest/api/{ARG_SENTINEL}/resource"

    class TimeoutSession:
        def get(self, *args: object, **kwargs: object) -> object:
            raise requests.Timeout("synthetic timeout detail")

    with pytest.raises(AtlaWireError) as caught:
        http.get_json_object(TimeoutSession(), url, params={})

    timeout_error = caught.value
    assert timeout_error.category == "transport"
    assert timeout_error.http_status is None
    assert timeout_error.method == "GET"
    assert timeout_error.path is None
    assert_not_leaked(timeout_error)

    class ForbiddenResponse:
        def __init__(self) -> None:
            self.status_code = 403
            self.headers: dict[str, str] = {}

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    class DeniedSession:
        def get(self, *args: object, **kwargs: object) -> ForbiddenResponse:
            return ForbiddenResponse()

    with pytest.raises(AtlaWireError) as caught_denied:
        http.get_json_object(DeniedSession(), url, params={})

    denied = caught_denied.value
    assert denied.category == "http"
    assert denied.http_status == 403
    assert denied.method == "GET"
    assert denied.path is None
    assert_not_leaked(denied)


@pytest.mark.parametrize(
    ("method", "body", "params"),
    [
        ("GET", {"synthetic": 1}, None),
        ("POST", None, None),
        ("POST", {"synthetic": 1}, None),
        ("GET", None, {"synthetic": object()}),
    ],
)
def test_sdk_pre_request_validation_never_echoes_a_path_secret(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    body: dict[str, object] | None,
    params: dict[str, object] | None,
) -> None:
    # Every pre-request validation branch of the public SDK entry point must
    # fail without a request and without echoing the dynamic path segment.
    def refuse(*args: object, **kwargs: object) -> requests.Response:
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(sdk, "_send", refuse)
    path = f"/rest/api/2/issue/{ARG_SENTINEL}"
    with pytest.raises(AtlaWireError) as caught:
        sdk.request_json_with_status(
            "jira",
            BASE,
            path,
            method=method,
            token=TOKEN,
            params=params,
            body=body,
        )

    error = caught.value
    assert error.category == "validation"
    assert error.product == "jira"
    assert error.http_status is None
    assert error.path is None
    assert_not_leaked(error)


@pytest.mark.parametrize(
    "scenario",
    [
        "bad-method",
        "bad-path",
        "get-with-body",
        "post-missing-body",
        "post-not-read-only",
        "download-existing-destination",
        "download-bad-limit",
        "download-bad-path",
    ],
)
def test_unknown_product_is_never_echoed_in_new_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scenario: str
) -> None:
    # A caller-supplied product string must not reach the new .product field
    # before _raw_client_for validates it against the fixed client map.
    product = f"{ARG_SENTINEL}-product"
    path = "/rest/api/2/issue/ABC-1"

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("no client or request may be created")

    monkeypatch.setattr(sdk, "_raw_client_for", refuse)
    existing = tmp_path / "existing.bin"
    existing.write_bytes(b"x")
    destination = tmp_path / "out.bin"
    with pytest.raises(AtlaWireError) as caught:
        if scenario == "bad-method":
            sdk.request_json_with_status(
                product, BASE, path, method="DELETE", token=TOKEN
            )
        elif scenario == "bad-path":
            sdk.request_json_with_status(
                product, BASE, "not-a-rest-path", method="GET", token=TOKEN
            )
        elif scenario == "get-with-body":
            sdk.request_json_with_status(
                product, BASE, path, method="GET", token=TOKEN, body={"x": 1}
            )
        elif scenario == "post-missing-body":
            sdk.request_json_with_status(
                product, BASE, "/rest/api/2/search", method="POST", token=TOKEN
            )
        elif scenario == "post-not-read-only":
            sdk.request_json_with_status(
                product, BASE, path, method="POST", token=TOKEN, body={"x": 1}
            )
        elif scenario == "download-existing-destination":
            sdk.download_to_file(
                product, BASE, path, token=TOKEN, destination=existing
            )
        elif scenario == "download-bad-limit":
            sdk.download_to_file(
                product, BASE, path, token=TOKEN, destination=destination, max_bytes=0
            )
        else:
            sdk.download_to_file(
                product, BASE, "not-a-rest-path", token=TOKEN, destination=destination
            )

    error = caught.value
    assert error.category == "validation"
    assert error.product is None
    assert_not_leaked(error)


@pytest.mark.parametrize(
    ("slot", "label", "target", "category", "message"),
    [
        (
            "confluence",
            "Confluence",
            ProductTarget("", "tok"),
            "validation",
            "The Confluence base URL is invalid.",
        ),
        (
            "jira",
            "Jira",
            ProductTarget("http://jira.example.test", "tok"),
            "validation",
            "The Jira base URL is invalid.",
        ),
        (
            "bitbucket",
            "Bitbucket",
            ProductTarget("https://bb.example.test", "bad token"),
            "credentials",
            "The Bitbucket token is missing or invalid.",
        ),
    ],
)
def test_federated_invalid_target_metadata_uses_canonical_slot(
    monkeypatch: pytest.MonkeyPatch,
    slot: str,
    label: str,
    target: ProductTarget,
    category: str,
    message: str,
) -> None:
    # federated_search is public and raises for an invalid supplied pair; the
    # structured product must be the canonical slot while the text and the
    # title-case display label stay exactly as before. No read may start.
    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("no federated read may start")

    monkeypatch.setattr("atlawire.federated._collect", refuse)
    pairs: dict[str, ProductTarget | None] = {
        "confluence": None,
        "jira": None,
        "bitbucket": None,
    }
    pairs[slot] = target
    with pytest.raises(AtlaWireError) as caught:
        federated_search(("term",), **pairs)

    error = caught.value
    assert error.product == slot
    assert error.product != label
    assert error.category == category
    assert str(error) == message
    assert error.http_status is None
    assert_not_leaked(error)

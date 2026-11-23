"""Installed-CLI contracts shared by the canonical read and federated commands.

Every case runs the installed console script against loopback origins, so the
assertions cover the request that was actually sent and the exit status chosen.
Each product keeps its own origin, context prefix and synthetic token, which
makes cross-product traffic and token reuse observable.
"""

import hashlib
import json
import subprocess
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

CONTEXTS = {"bitbucket": "/bitbucket", "confluence": "/confluence", "jira": "/jira"}
TOKENS = {
    "bitbucket": "synthetic-contract-bitbucket-5c1",
    "confluence": "synthetic-contract-confluence-5c2",
    "jira": "synthetic-contract-jira-5c3",
}
PRODUCTS = tuple(CONTEXTS)
SEARCH_PATHS = {
    "confluence": "/confluence/rest/api/search",
    "jira": "/jira/rest/api/2/search",
    "bitbucket": "/bitbucket/rest/search/latest/search",
}
JIRA_PROJECT_PATH = "/jira/rest/api/2/project/DEMO"
AVATAR_PATH = "/jira/rest/api/2/avatar/user/system"
PROJECT_PARAMS = '{"projectIdOrKey":"DEMO"}'
PROJECT_PAYLOAD = {"key": "DEMO", "name": "Demo project"}
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(24))
OCTET_STREAM = "application/octet-stream"
JIRA_PROJECT_READ = ("GET", JIRA_PROJECT_PATH, {}, f"Bearer {TOKENS['jira']}", None)
JIRA_AVATAR_READ = ("GET", AVATAR_PATH, {}, f"Bearer {TOKENS['jira']}", None)

Record = tuple[str, str, dict[str, list[str]], str | None, dict[str, object] | None]
Responder = Callable[
    [str, dict[str, list[str]], dict[str, object] | None], tuple[int, object]
]


def product_handler(
    seen: list[Record], routes: Mapping[str, Responder]
) -> type[BaseHTTPRequestHandler]:
    """Serve one product origin, recording every request including unknown paths."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def _serve(self) -> None:
            method, path, params, authorization = request_record(self)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
            parsed = json.loads(raw) if raw else None
            body = parsed if isinstance(parsed, dict) else None
            seen.append((method, path, params, authorization, body))
            responder = routes.get(path)
            if responder is None:
                send_json(self, 404, {"unexpected": path})
                return
            status, payload = responder(method, params, body)
            if isinstance(payload, bytes):
                send_bytes(self, status, payload, content_type=OCTET_STREAM)
            else:
                send_json(self, status, payload)

        def do_GET(self) -> None:
            self._serve()

        def do_POST(self) -> None:
            self._serve()

    return Handler


@contextmanager
def product_origins(
    seen: Mapping[str, list[Record]],
    routes: Mapping[str, Mapping[str, Responder]] | None = None,
) -> Iterator[dict[str, str]]:
    """Start one loopback origin per product so cross-product calls are visible."""
    planned = routes or {}
    with ExitStack() as stack:
        origins: dict[str, str] = {}
        for product in PRODUCTS:
            handler = product_handler(seen[product], planned.get(product, {}))
            server = stack.enter_context(serving(handler))
            origins[product] = f"http://127.0.0.1:{server.server_port}"
        yield origins


def request_log() -> dict[str, list[Record]]:
    return {product: [] for product in PRODUCTS}


def blank_environment(missing_credentials: Path) -> dict[str, str]:
    """Blank every ambient pair so inherited variables cannot leak into a case."""
    environment = {"BBK_CREDENTIALS": str(missing_credentials)}
    for product in PRODUCTS:
        environment[f"ATLAWIRE_{product.upper()}_URL"] = ""
        environment[f"ATLAWIRE_{product.upper()}_TOKEN"] = ""
    return environment


def configure(environment: dict[str, str], product: str, origin: str) -> None:
    environment[f"ATLAWIRE_{product.upper()}_URL"] = f"{origin}{CONTEXTS[product]}/"
    environment[f"ATLAWIRE_{product.upper()}_TOKEN"] = TOKENS[product]


def canonical_args(operation: str, params: str, *extra: str) -> list[str]:
    """The canonical environment-credential read invocation."""
    tail = ["--token-from-env", "--allow-http-loopback"]
    return ["read", operation, "--params", params, *extra, *tail]


def run_jira_read(
    tmp_path: Path,
    args: Sequence[str],
    routes: Mapping[str, Responder],
    *,
    mutate: Callable[[dict[str, str]], None] | None = None,
    explicit_base_url: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, list[Record]]]:
    """Run one canonical read against a jira route and keep the request log."""
    seen = request_log()
    with product_origins(seen, {"jira": routes}) as origins:
        environment = blank_environment(tmp_path / "fixture-missing.json")
        configure(environment, "jira", origins["jira"])
        if mutate is not None:
            mutate(environment)
        final = list(args)
        if explicit_base_url:
            final += ["--base-url", f"{origins['jira']}{CONTEXTS['jira']}/"]
        result = run_installed(final, environment)
    return result, seen


def page_fixture(term: str) -> dict[str, object]:
    content = {"id": "201", "type": "page", "title": f"Page {term}"}
    return {"content": {**content, "space": {"key": "ENG"}}}


def issue_fixture(term: str) -> dict[str, object]:
    fields = {
        "summary": f"Match for {term}",
        "updated": "2026-11-20T10:00:00.000+0000",
    }
    return {"key": f"{term.upper()}-1", "fields": fields}


def code_fixture(term: str) -> dict[str, object]:
    return {
        "repository": {"project": {"key": "P"}, "slug": "widgets"},
        "file": f"src/{term}.py",
        "hitCount": 1,
        "hitContexts": [[{"line": 1, "text": f"<em>{term}</em>"}]],
    }


def quoted_term(query: str) -> str:
    clause = query.split(" ORDER BY ")[0]
    prefix = 'text ~ "'
    assert clause.startswith(prefix) and clause.endswith('"'), clause
    return clause[len(prefix) : -1]


def term_of(
    product: str, params: dict[str, list[str]], body: dict[str, object] | None
) -> str:
    if product == "bitbucket":
        assert body is not None
        query = body["query"]
        assert isinstance(query, str)
        return query
    return quoted_term(params["cql" if product == "confluence" else "jql"][0])


def recorded_terms(records: Sequence[Record], product: str) -> list[str]:
    return [term_of(product, params, body) for _, _, params, _, body in records]


def search_responder(
    product: str, failures: frozenset[str] = frozenset()
) -> Responder:
    """Answer one product's search route, or fail the named terms with HTTP 500."""

    def respond(
        method: str, params: dict[str, list[str]], body: dict[str, object] | None
    ) -> tuple[int, object]:
        term = term_of(product, params, body)
        if term in failures:
            return 500, {"message": "upstream failed"}
        if product == "confluence":
            start = int(params["start"][0])
            limit = int(params["limit"][0])
            page = {"start": start, "limit": limit, "totalSize": 1}
            rows = [page_fixture(term)] if start == 0 else []
            return 200, {**page, "size": len(rows), "results": rows}
        if product == "jira":
            return 200, {
                "startAt": 0,
                "maxResults": 20,
                "total": 1,
                "issues": [issue_fixture(term)],
            }
        return 200, {"code": {"values": [code_fixture(term)], "isLastPage": True}}

    return respond


def json_responder(payload: object) -> Responder:
    def respond(
        method: str, params: dict[str, list[str]], body: dict[str, object] | None
    ) -> tuple[int, object]:
        return 200, payload

    return respond


def federated_routes(
    failures: frozenset[str] = frozenset()
) -> dict[str, dict[str, Responder]]:
    return {
        product: {SEARCH_PATHS[product]: search_responder(product, failures)}
        for product in PRODUCTS
    }


def run_find(
    environment: Mapping[str, str], *terms: str
) -> subprocess.CompletedProcess[str]:
    return run_installed(
        ["find", *terms, "--json", "--allow-http-loopback", "--token-from-env"],
        environment,
    )


def run_configured_find(
    tmp_path: Path,
    products: Sequence[str],
    *terms: str,
    failures: frozenset[str] = frozenset(),
) -> tuple[subprocess.CompletedProcess[str], dict[str, list[Record]]]:
    """Run find against the named products and keep every product's requests."""
    seen = request_log()
    with product_origins(seen, federated_routes(failures)) as origins:
        environment = blank_environment(tmp_path / "fixture-missing.json")
        for product in products:
            configure(environment, product, origins[product])
        result = run_find(environment, *terms)
    return result, seen


def single_json(stdout: str) -> dict[str, object]:
    """Parse stdout as exactly one JSON document, rejecting extra output."""
    lines = stdout.strip().splitlines()
    assert len(lines) == 1, stdout
    return json.loads(lines[0])


def test_read_uses_the_product_environment_pair_without_a_base_url(
    tmp_path: Path,
) -> None:
    # Rejects a resolver that still demands --base-url or the saved BBK file.
    result, seen = run_jira_read(
        tmp_path,
        canonical_args("jira.project.get", PROJECT_PARAMS),
        {JIRA_PROJECT_PATH: json_responder(PROJECT_PAYLOAD)},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ok": True,
        "product": "jira",
        "data": PROJECT_PAYLOAD,
    }
    assert seen["jira"] == [JIRA_PROJECT_READ]
    assert seen["confluence"] == [] and seen["bitbucket"] == []


def test_read_explicit_base_url_wins_over_the_environment_url(tmp_path: Path) -> None:
    # Rejects a resolver that always prefers ATLAWIRE_JIRA_URL.
    wrong = {"ATLAWIRE_JIRA_URL": "http://127.0.0.1:9/wrong-jira/"}
    result, seen = run_jira_read(
        tmp_path,
        canonical_args("jira.project.get", PROJECT_PARAMS),
        {JIRA_PROJECT_PATH: json_responder(PROJECT_PAYLOAD)},
        mutate=lambda environment: environment.update(wrong),
        explicit_base_url=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"] == PROJECT_PAYLOAD
    assert seen["jira"] == [JIRA_PROJECT_READ]


def test_read_without_the_product_url_is_a_credentials_error(tmp_path: Path) -> None:
    # Rejects a resolver that defaults a missing URL or reads the saved file.
    result, seen = run_jira_read(
        tmp_path,
        canonical_args("jira.project.get", PROJECT_PARAMS),
        {JIRA_PROJECT_PATH: json_responder(PROJECT_PAYLOAD)},
        mutate=lambda environment: environment.update({"ATLAWIRE_JIRA_URL": ""}),
    )

    assert result.returncode == 2
    envelope = single_json(result.stdout)
    assert envelope["ok"] is False
    assert envelope["product"] == "jira"
    assert envelope["error"]["code"] == "credentials_error"
    assert "ATLAWIRE_JIRA_URL" in envelope["error"]["message"]
    assert all(records == [] for records in seen.values())


def test_find_never_contacts_a_half_configured_product_origin(tmp_path: Path) -> None:
    # Rejects borrowing another token or treating a half pair as configured.
    seen = request_log()
    with product_origins(seen, federated_routes()) as origins:
        environment = blank_environment(tmp_path / "fixture-missing.json")
        configure(environment, "confluence", origins["confluence"])
        environment["ATLAWIRE_JIRA_URL"] = f"{origins['jira']}{CONTEXTS['jira']}/"
        environment["ATLAWIRE_BITBUCKET_TOKEN"] = TOKENS["bitbucket"]
        result = run_find(environment, "ported")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert set(payload["errors"]) == {"jira", "bitbucket"}
    assert payload["confluence"]
    assert seen["jira"] == [] and seen["bitbucket"] == []
    assert all(r[3] == f"Bearer {TOKENS['confluence']}" for r in seen["confluence"])
    assert TOKENS["jira"] not in result.stdout
    assert TOKENS["bitbucket"] not in result.stdout


def test_find_with_one_configured_product_reports_the_rest(tmp_path: Path) -> None:
    # Rejects dropping a partial answer or calling a missing product fatal.
    result, seen = run_configured_find(tmp_path, ("jira",), "ported")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["jira"] and payload["jira"][0]["key"] == "PORTED-1"
    assert payload["jira"][0]["terms"] == ["ported"]
    assert payload["counts"] == {"confluence": 0, "jira": 1, "bitbucket": 0}
    assert set(payload["errors"]) == {"confluence", "bitbucket"}
    assert payload["complete"] is False
    assert seen["confluence"] == [] and seen["bitbucket"] == []
    record = seen["jira"][0]
    assert record[:2] == ("GET", SEARCH_PATHS["jira"])
    assert record[3] == f"Bearer {TOKENS['jira']}"
    assert record[2]["jql"] == ['text ~ "ported" ORDER BY created DESC']


def test_find_partial_term_failures_still_return_data(tmp_path: Path) -> None:
    # Rejects the regression where one failed term hides completed reads.
    result, seen = run_configured_find(
        tmp_path, PRODUCTS, "alpha", "beta", failures=frozenset({"alpha"})
    )

    assert result.returncode == 0, result.stderr
    assert "failed for every product" not in result.stderr
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert set(payload["errors"]) == set(PRODUCTS)
    assert payload["confluence"] and payload["jira"] and payload["bitbucket"]
    assert recorded_terms(seen["confluence"], "confluence") == [
        "alpha",
        "beta",
        "beta",
    ]
    assert recorded_terms(seen["jira"], "jira") == ["alpha", "beta"]
    assert recorded_terms(seen["bitbucket"], "bitbucket") == ["alpha", "beta"]


def test_find_total_failure_is_an_error_without_partial_data(tmp_path: Path) -> None:
    # Rejects an empty payload with exit 0 after every product/term failed.
    result, seen = run_configured_find(
        tmp_path, PRODUCTS, "alpha", "beta", failures=frozenset({"alpha", "beta"})
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "failed for every product" in result.stderr
    assert "Traceback" not in result.stderr
    for product in PRODUCTS:
        assert recorded_terms(seen[product], product) == ["alpha", "beta"]
        assert TOKENS[product] not in result.stderr


@pytest.mark.parametrize(
    "argv",
    [
        ["--catalog", "--describe", "jira.project.get"],
        ["--describe", "jira.project.get", "--catalog"],
    ],
    ids=["catalog-first", "describe-first"],
)
def test_conflicting_discovery_flags_are_one_validation_error(
    tmp_path: Path, argv: list[str]
) -> None:
    # Rejects running an action or reading credentials before the conflict check.
    seen = request_log()
    with product_origins(seen):
        environment = blank_environment(tmp_path / "fixture-missing.json")
        result = run_installed(argv, environment)

    assert result.returncode == 2
    envelope = single_json(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert "alone" in envelope["error"]["message"]
    assert "commands" not in envelope and "operations" not in envelope
    assert all(records == [] for records in seen.values())


def test_read_of_a_json_operation_with_out_is_a_validation_error(
    tmp_path: Path,
) -> None:
    # Rejects resolving credentials or writing before the response-kind check.
    destination = tmp_path / "project.json"
    result, seen = run_jira_read(
        tmp_path,
        canonical_args(
            "jira.project.get", PROJECT_PARAMS, "--out", str(destination)
        ),
        {JIRA_PROJECT_PATH: json_responder(PROJECT_PAYLOAD)},
    )

    assert result.returncode == 2
    envelope = single_json(result.stdout)
    assert envelope["error"]["code"] == "validation_error"
    assert "--out" in envelope["error"]["message"]
    assert not destination.exists()
    assert all(records == [] for records in seen.values())


def test_read_binary_operation_with_out_writes_bytes_and_a_receipt(
    tmp_path: Path,
) -> None:
    # Positive control: the same --out path must still publish a binary read.
    destination = tmp_path / "avatar.png"
    out = str(destination)
    result, seen = run_jira_read(
        tmp_path,
        canonical_args("jira.avatar.system", '{"type":"user"}', "--out", out),
        {AVATAR_PATH: json_responder(PNG)},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"] == {
        "path": str(destination),
        "bytes": len(PNG),
        "sha256": hashlib.sha256(PNG).hexdigest(),
        "content_type": "application/octet-stream",
    }
    assert destination.read_bytes() == PNG
    assert seen["jira"] == [JIRA_AVATAR_READ]


def test_discovery_flags_alone_stay_offline(tmp_path: Path) -> None:
    # Rejects a conflict guard that breaks a lone --catalog or --describe.
    seen = request_log()
    environment = blank_environment(tmp_path / "fixture-missing.json")
    with product_origins(seen):
        catalog = run_installed(["--catalog"], environment)
        described = run_installed(["--describe", "jira.project.get"], environment)

    assert catalog.returncode == 0, catalog.stderr
    catalog_payload = json.loads(catalog.stdout)
    assert catalog_payload["commands"]
    operations = {entry["id"] for entry in catalog_payload["operations"]}
    assert "jira.project.get" in operations
    assert described.returncode == 0, described.stderr
    described_payload = json.loads(described.stdout)
    assert described_payload["id"] == "jira.project.get"
    assert described_payload["command"] == ["atlawire", "read", "jira.project.get"]
    assert all(records == [] for records in seen.values())

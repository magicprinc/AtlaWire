"""Unit checks for federated read-only search across the three products."""

import json
from collections.abc import Sequence
from typing import cast

import pytest

from atlawire import federated
from atlawire.federated import ProductTarget, federated_search
from atlawire.http import AtlaWireError

CONFLUENCE = ProductTarget("https://confluence.example.test", "fixture-confluence")
JIRA = ProductTarget("https://jira.example.test", "fixture-jira")
BITBUCKET = ProductTarget("https://bitbucket.example.test", "fixture-bitbucket")

Call = tuple[str, str, str, str, int]
Rows = dict[str, list[dict[str, object]]]


def cql_term(query: str) -> str:
    """Recover the term from the exact CQL clause the module must build."""
    prefix = 'text ~ "'
    assert query.startswith(prefix)
    assert query.endswith('"')
    return query[len(prefix) : -1]


def jql_term(query: str) -> str:
    """Recover the term from the exact ordered JQL clause."""
    suffix = " ORDER BY created DESC"
    assert query.endswith(suffix)
    return cql_term(query[: -len(suffix)])


def page(
    page_id: object,
    *,
    title: str = "Page",
    space: str = "ENG",
    page_type: str = "page",
    url: str | None = None,
) -> dict[str, object]:
    return {
        "id": page_id,
        "title": title,
        "space": space,
        "type": page_type,
        "url": url,
    }


def issue(
    key: str,
    *,
    summary: str = "Summary",
    status: str = "Open",
    issue_type: str = "Task",
) -> dict[str, object]:
    return {
        "key": key,
        "status": status,
        "type": issue_type,
        "priority": "Major",
        "assignee": "Ann",
        "updated": "2026-11-20",
        "summary": summary,
    }


def code(
    *,
    project: str = "P",
    repository: str = "r",
    path: str = "a.py",
    hit_count: int | None = 1,
    evidence: str = "highlight",
) -> dict[str, object]:
    return {
        "project": project,
        "repository": repository,
        "file": path,
        "hitCount": hit_count,
        "matchEvidence": evidence,
    }


def install_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pages: Rows | None = None,
    issues: Rows | None = None,
    files: Rows | None = None,
    fail: str | None = None,
    paging: list[bool] | None = None,
) -> list[Call]:
    """Replace the three adapters with recorders and term-keyed fixtures."""
    calls: list[Call] = []

    def confluence_search(
        base_url: str,
        query: str,
        *,
        token: str,
        limit: int,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        calls.append(("Confluence", base_url, query, token, limit))
        if fail == "Confluence":
            raise AtlaWireError("HTTP 503: request failed.")
        return list((pages or {}).get(cql_term(query), []))

    def jira_search(
        base_url: str,
        query: str,
        *,
        token: str,
        limit: int,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        calls.append(("Jira", base_url, query, token, limit))
        if fail == "Jira":
            raise AtlaWireError("HTTP 503: request failed.")
        return list((issues or {}).get(jql_term(query), []))

    def bitbucket_search(
        base_url: str,
        query: str,
        *,
        token: str,
        limit: int,
        every_page: bool = False,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        calls.append(("Bitbucket", base_url, query, token, limit))
        if paging is not None:
            paging.append(every_page)
        if fail == "Bitbucket":
            raise AtlaWireError("HTTP 503: request failed.")
        return list((files or {}).get(query, []))

    monkeypatch.setattr(federated, "search_cql", confluence_search)
    monkeypatch.setattr(federated, "search_issues", jira_search)
    monkeypatch.setattr(federated, "search_code", bitbucket_search)
    return calls


def product_rows(result: dict[str, object], product: str) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], result[product])


def counts(result: dict[str, object]) -> dict[str, int]:
    return cast(dict[str, int], result["counts"])


def limitations(result: dict[str, object]) -> list[str]:
    return cast(list[str], result["limitations"])


def search(terms: Sequence[str], *, limit: int = 20) -> dict[str, object]:
    return federated_search(
        terms,
        confluence=CONFLUENCE,
        jira=JIRA,
        bitbucket=BITBUCKET,
        limit=limit,
    )


def test_two_terms_merge_duplicates_in_first_seen_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_search(
        monkeypatch,
        pages={
            "ported numbers": [
                page("102", title="Two"),
                page("101", title="One"),
            ],
            "ported": [
                page("103", title="Three"),
                page("101", title="Changed duplicate"),
            ],
        },
        issues={
            "ported numbers": [issue("FED-2"), issue("FED-1", summary="First")],
            "ported": [issue("FED-1", summary="Changed duplicate"), issue("FED-3")],
        },
        files={
            "ported numbers": [
                code(path="src/a.py", hit_count=2),
                code(path="src/b.py", hit_count=None, evidence="context-only"),
            ],
            "ported": [
                code(repository="R", path="src/a.py", hit_count=7),
                code(path="src/c.py"),
            ],
        },
    )

    result = search(["ported numbers", "ported"])

    assert calls == [
        (
            "Confluence",
            CONFLUENCE.base_url,
            'text ~ "ported numbers"',
            CONFLUENCE.token,
            20,
        ),
        (
            "Jira",
            JIRA.base_url,
            'text ~ "ported numbers" ORDER BY created DESC',
            JIRA.token,
            20,
        ),
        ("Bitbucket", BITBUCKET.base_url, "ported numbers", BITBUCKET.token, 20),
        ("Confluence", CONFLUENCE.base_url, 'text ~ "ported"', CONFLUENCE.token, 20),
        (
            "Jira",
            JIRA.base_url,
            'text ~ "ported" ORDER BY created DESC',
            JIRA.token,
            20,
        ),
        ("Bitbucket", BITBUCKET.base_url, "ported", BITBUCKET.token, 20),
    ]
    assert result["terms"] == ["ported numbers", "ported"]

    pages = product_rows(result, "confluence")
    assert [row["id"] for row in pages] == ["102", "101", "103"]
    assert pages[1]["title"] == "One"
    assert pages[1]["terms"] == ["ported numbers", "ported"]
    assert pages[0]["terms"] == ["ported numbers"]

    issues = product_rows(result, "jira")
    assert [row["key"] for row in issues] == ["FED-2", "FED-1", "FED-3"]
    assert issues[1]["summary"] == "First"
    assert issues[1]["terms"] == ["ported numbers", "ported"]

    files = product_rows(result, "bitbucket")
    assert [(row["project"], row["repository"], row["file"]) for row in files] == [
        ("P", "r", "src/a.py"),
        ("P", "r", "src/b.py"),
        ("P", "r", "src/c.py"),
    ]
    assert files[0]["hitCount"] == 7
    assert files[0]["terms"] == ["ported numbers", "ported"]
    assert files[1]["hitCount"] is None
    assert files[1]["matchEvidence"] == "context-only"
    assert counts(result) == {"confluence": 3, "jira": 3, "bitbucket": 3}


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("context-only", "highlight", "highlight"),
        ("none", "highlight", "highlight"),
        ("highlight", "context-only", "highlight"),
        ("none", "context-only", "context-only"),
        ("none", "none", "none"),
    ],
    ids=[
        "context-then-highlight",
        "none-then-highlight",
        "highlight-then-context",
        "none-then-context",
        "none-then-none",
    ],
)
def test_file_evidence_keeps_the_strongest_match(
    monkeypatch: pytest.MonkeyPatch,
    first: str,
    second: str,
    expected: str,
) -> None:
    install_search(
        monkeypatch,
        files={
            "first": [code(path="src/a.py", evidence=first)],
            "second": [code(path="src/a.py", evidence=second)],
        },
    )

    result = search(["first", "second"])

    files = product_rows(result, "bitbucket")
    assert len(files) == 1
    assert files[0]["matchEvidence"] == expected
    assert files[0]["terms"] == ["first", "second"]


def test_bitbucket_paging_is_requested_for_every_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paging: list[bool] = []
    install_search(monkeypatch, paging=paging)

    search(["ported numbers", "ported"])

    assert paging == [True, True]


def test_bitbucket_cursor_failure_after_a_term_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Call] = []

    def empty_search(
        base_url: str,
        query: str,
        *,
        token: str,
        limit: int,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        return []

    def bitbucket_search(
        base_url: str,
        query: str,
        *,
        token: str,
        limit: int,
        every_page: bool = False,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        calls.append(("Bitbucket", base_url, query, token, limit))
        if query == "second":
            raise AtlaWireError("Invalid or non-advancing Bitbucket search nextStart.")
        return [code(path="src/a.py", evidence="highlight")]

    monkeypatch.setattr(federated, "search_cql", empty_search)
    monkeypatch.setattr(federated, "search_issues", empty_search)
    monkeypatch.setattr(federated, "search_code", bitbucket_search)

    with pytest.raises(AtlaWireError) as caught:
        search(["first", "second"])

    message = str(caught.value)
    assert "Bitbucket" in message
    assert "nextStart" in message
    assert "no partial result" in message
    assert "src/a.py" not in message
    assert [call[2] for call in calls] == ["first", "second"]


def test_unicode_terms_are_quoted_verbatim_for_each_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_search(
        monkeypatch,
        pages={"МВНО": [page("16", title="МВНО")], "café": []},
        issues={"МВНО": [issue("FED-9")], "café": []},
        files={"МВНО": [code(path="docs/мвно.md")], "café": []},
    )

    result = search(["МВНО", "café"])

    assert calls[0][2] == 'text ~ "МВНО"'
    assert calls[1][2] == 'text ~ "МВНО" ORDER BY created DESC'
    assert calls[2][2] == "МВНО"
    assert calls[3][2] == 'text ~ "café"'
    assert result["terms"] == ["МВНО", "café"]
    assert product_rows(result, "confluence")[0]["title"] == "МВНО"
    assert "МВНО" in json.dumps(result, ensure_ascii=False)


UNSAFE_TERMS = [
    ("quote", 'ported" OR key = FED-1'),
    ("backslash", "ported\\numbers"),
    ("newline", "ported\nnumbers"),
    ("bidi", "ported\u202enumbers"),
    ("surrogate", "ported\ud800numbers"),
]


@pytest.mark.parametrize(
    "term",
    [term for _, term in UNSAFE_TERMS],
    ids=[name for name, _ in UNSAFE_TERMS],
)
def test_unsafe_term_syntax_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, term: str
) -> None:
    calls = install_search(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        search([term])

    assert "plain text" in str(caught.value)
    assert "FED-1" not in str(caught.value)
    assert calls == []


@pytest.mark.parametrize(
    "terms",
    [[], ["   "], [""], [7], "ported", {"ported"}],
    ids=["empty", "blank", "empty-text", "not-text", "bare-string", "set"],
)
def test_missing_or_malformed_terms_are_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, terms: object
) -> None:
    calls = install_search(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        federated_search(
            cast(Sequence[str], terms),
            confluence=CONFLUENCE,
            jira=JIRA,
            bitbucket=BITBUCKET,
        )

    assert "search term" in str(caught.value)
    assert calls == []


@pytest.mark.parametrize("product", ["Confluence", "Jira", "Bitbucket"])
def test_any_product_failure_publishes_nothing_and_stops_later_calls(
    monkeypatch: pytest.MonkeyPatch, product: str
) -> None:
    calls = install_search(monkeypatch, fail=product)

    with pytest.raises(AtlaWireError) as caught:
        search(["ported numbers", "ported"])

    first = (
        "Confluence",
        CONFLUENCE.base_url,
        'text ~ "ported numbers"',
        CONFLUENCE.token,
        20,
    )
    second = (
        "Jira",
        JIRA.base_url,
        'text ~ "ported numbers" ORDER BY created DESC',
        JIRA.token,
        20,
    )
    third = ("Bitbucket", BITBUCKET.base_url, "ported numbers", BITBUCKET.token, 20)
    expected = {
        "Confluence": [first],
        "Jira": [first, second],
        "Bitbucket": [first, second, third],
    }[product]
    assert calls == expected

    message = str(caught.value)
    assert product in message
    assert "no partial result was published" in message
    for detail in (
        CONFLUENCE.token,
        JIRA.token,
        BITBUCKET.token,
        CONFLUENCE.base_url,
        "ported numbers",
    ):
        assert detail not in message


def test_each_product_receives_only_its_own_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_search(monkeypatch)
    confluence = ProductTarget("https://confluence.example.test:8443/", "cf-token")
    jira = ProductTarget("https://jira.example.test/jira/", "jira-token")
    bitbucket = ProductTarget("https://bitbucket.example.test/scm/", "bb-token")

    result = federated_search(
        ["ported"],
        confluence=confluence,
        jira=jira,
        bitbucket=bitbucket,
    )

    assert calls == [
        (
            "Confluence",
            "https://confluence.example.test:8443",
            'text ~ "ported"',
            "cf-token",
            20,
        ),
        (
            "Jira",
            "https://jira.example.test/jira",
            'text ~ "ported" ORDER BY created DESC',
            "jira-token",
            20,
        ),
        ("Bitbucket", "https://bitbucket.example.test/scm", "ported", "bb-token", 20),
    ]
    payload = json.dumps(result)
    for token in ("cf-token", "jira-token", "bb-token"):
        assert token not in payload
    assert confluence.token not in repr(confluence)


BAD_TARGETS = [
    cast(ProductTarget, None),
    ProductTarget("", "fixture-token"),
    ProductTarget("http://confluence.example.test", "fixture-token"),
    ProductTarget("https://confluence.example.test", ""),
    ProductTarget("https://confluence.example.test", "bad token"),
    ProductTarget("https://confluence.example.test?cql=x", "fixture-token"),
    ProductTarget("https://user@confluence.example.test", "fixture-token"),
]


@pytest.mark.parametrize("slot", ["confluence", "jira", "bitbucket"])
@pytest.mark.parametrize(
    "target",
    BAD_TARGETS,
    ids=[
        "wrong-type",
        "empty-url",
        "plain-http",
        "empty-token",
        "token-with-space",
        "url-with-query",
        "url-with-userinfo",
    ],
)
def test_invalid_target_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, slot: str, target: ProductTarget
) -> None:
    calls = install_search(monkeypatch)

    with pytest.raises(AtlaWireError):
        federated_search(
            ["ported"],
            confluence=target if slot == "confluence" else CONFLUENCE,
            jira=target if slot == "jira" else JIRA,
            bitbucket=target if slot == "bitbucket" else BITBUCKET,
        )

    assert calls == []


def test_limit_is_forwarded_to_every_product_and_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_search(monkeypatch)

    result = search(["ported numbers", "ported"], limit=3)

    assert [call[4] for call in calls] == [3, 3, 3, 3, 3, 3]
    assert result["limits"] == {"per_term_per_product": 3}


@pytest.mark.parametrize(
    "limit",
    [0, 1000, True, 1.5, "20"],
    ids=["zero", "too-large", "boolean", "float", "text"],
)
def test_invalid_limit_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch, limit: object
) -> None:
    calls = install_search(monkeypatch)

    with pytest.raises(AtlaWireError):
        search(["ported"], limit=cast(int, limit))

    assert calls == []


def test_empty_results_keep_zero_counts_and_coverage_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = install_search(monkeypatch)

    result = search(["nothing matches"])

    assert len(calls) == 3
    assert product_rows(result, "confluence") == []
    assert product_rows(result, "jira") == []
    assert product_rows(result, "bitbucket") == []
    assert counts(result) == {"confluence": 0, "jira": 0, "bitbucket": 0}
    assert "errors" not in result
    warning = " ".join(limitations(result))
    assert "per-term limit" in warning
    assert "may be omitted" in warning
    assert "Bitbucket" in warning and "indexed" in warning
    assert "may be missing" in warning
    json.dumps(result)


def test_exact_repeated_term_is_searched_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_search(
        monkeypatch,
        pages={"ported": [page("7", title="Ported")]},
    )

    result = search(["ported", "ported"])

    assert len(calls) == 3
    assert result["terms"] == ["ported"]
    assert product_rows(result, "confluence")[0]["terms"] == ["ported"]


@pytest.mark.parametrize("page_id", [None, True, ""], ids=["none", "boolean", "empty"])
def test_page_without_stable_id_fails_closed(
    monkeypatch: pytest.MonkeyPatch, page_id: object
) -> None:
    install_search(monkeypatch, pages={"ported": [page(page_id)]})

    with pytest.raises(AtlaWireError) as caught:
        search(["ported"])

    assert "stable ID" in str(caught.value)


def test_issue_without_stable_key_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_search(monkeypatch, issues={"ported": [issue("")]})

    with pytest.raises(AtlaWireError) as caught:
        search(["ported"])

    assert "stable key" in str(caught.value)


@pytest.mark.parametrize("path", ["", None], ids=["empty", "missing"])
def test_file_without_stable_path_fails_closed(
    monkeypatch: pytest.MonkeyPatch, path: object
) -> None:
    install_search(
        monkeypatch,
        files={"ported": [code(path=cast(str, path))]},
    )

    with pytest.raises(AtlaWireError) as caught:
        search(["ported"])

    assert "without a path" in str(caught.value)

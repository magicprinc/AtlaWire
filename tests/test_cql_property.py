import json
from urllib.parse import parse_qs, urlsplit

import requests
import responses
from hypothesis import given, settings
from hypothesis import strategies as st

from atlawire import confluence

BASE = "https://wiki.example.invalid/wiki"
SEARCH_PATH = "/wiki/rest/api/search"
SEARCH_URL = f"https://wiki.example.invalid{SEARCH_PATH}"
QUERY = "type = page AND space = DEMO"


def content_id(index: int) -> str:
    return str(1000 + index)


def api_row(index: int) -> dict[str, object]:
    return {
        "content": {
            "id": content_id(index),
            "type": "page",
            "title": f"Page {index}",
            "space": {"key": "DEMO"},
        },
        "excerpt": f"Excerpt {index}",
        "_links": {"webui": f"/display/DEMO/Page-{index}"},
    }


def expected_row(index: int) -> dict[str, object]:
    return {
        "id": content_id(index),
        "space": "DEMO",
        "type": "page",
        "title": f"Page {index}",
        "url": f"/display/DEMO/Page-{index}",
    }


def expected_starts(row_count: int, caps: list[int], user_limit: int) -> list[int]:
    """Request offsets a count-based reader should visit, derived from the model."""
    if user_limit == 0:
        return []
    starts: list[int] = []
    offset = 0
    while True:
        starts.append(offset)
        if offset >= row_count:
            return starts
        cap = caps[(len(starts) - 1) % len(caps)]
        offset += min(cap, user_limit - offset, row_count - offset)
        if offset >= user_limit:
            return starts


@settings(max_examples=40, deadline=None)
@given(
    row_count=st.integers(min_value=0, max_value=6),
    user_limit=st.integers(min_value=0, max_value=6),
    caps=st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=3),
    include_hint=st.booleans(),
)
def test_cql_pagination_matches_a_slice_model(
    row_count: int, user_limit: int, caps: list[int], include_hint: bool
) -> None:
    rows = [api_row(index) for index in range(row_count)]
    calls: list[tuple[str, int, int, str]] = []

    def callback(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = urlsplit(request.url or "")
        query = parse_qs(url.query)
        start = int(query["start"][0])
        requested = int(query["limit"][0])
        cap = caps[len(calls) % len(caps)]
        calls.append((url.path, start, requested, query["cql"][0]))
        taken = rows[start : start + min(cap, requested)]
        body: dict[str, object] = {
            "start": start,
            "size": len(taken),
            "results": taken,
            "totalSize": len(rows),
        }
        if include_hint and taken and len(taken) < requested:
            body["_links"] = {"next": f"/rest/api/search?start={start + len(taken)}"}
        return 200, {"Content-Type": "application/json"}, json.dumps(body)

    # A fresh mock per example keeps Hypothesis iterations independent. The
    # mock still blocks any request outside the searched endpoint.
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.add_callback(responses.GET, SEARCH_URL, callback=callback)
        result_rows = confluence.search_cql(
            BASE, QUERY, token="fixture-only", limit=user_limit
        )

    assert result_rows == [
        expected_row(index) for index in range(min(user_limit, row_count))
    ]
    assert len({row["id"] for row in result_rows}) == len(result_rows)
    starts = expected_starts(row_count, caps, user_limit)
    assert [start for _, start, _, _ in calls] == starts
    # Exactly one request per start means no request at zero and no extra
    # request after reaching the user limit.
    assert len(calls) == len(starts)
    for path, start, requested, cql in calls:
        assert path == SEARCH_PATH
        assert cql == QUERY
        assert requested == user_limit - start

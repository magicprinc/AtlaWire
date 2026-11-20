"""Read operations for self-hosted Bitbucket."""

import re
from collections.abc import Callable
from typing import TypedDict

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)

_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_PULL_REQUEST_ID_MAX = 2**63 - 1


class Repository(TypedDict):
    slug: str
    name: str | None
    state: str | None
    public: bool | None


class Project(TypedDict):
    key: str
    name: str | None
    public: bool | None
    description: str | None
    url: str | None


def list_projects(
    base_url: str,
    *,
    token: str,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Project]:
    """List visible projects in server order or raise without a partial list."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    url = f"{base}/rest/api/1.0/projects"
    with bearer_session(token) as session:
        return _read_pages(session, url, max_pages, project=_project)


def list_repositories(
    base_url: str,
    project: str,
    *,
    token: str,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Repository]:
    """List repositories in server order or raise without returning a partial list."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if not _PROJECT_KEY.fullmatch(project):
        raise AtlaWireError("Expected a Bitbucket project key or ~user project.")
    if not 1 <= max_pages <= 1000:
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    url = f"{base}/rest/api/1.0/projects/{project}/repos"
    with bearer_session(token) as session:
        return _read_pages(session, url, max_pages, project=_repository)


def get_pull_request(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one pull request exactly as the server sent it.

    ``repo`` is ``PROJECT/slug``. ``pr_id`` accepts a canonical positive decimal
    string or ``int``; the request carries its canonical decimal form. The result
    is the decoded server object, so unknown and nested fields are preserved, and
    links in it are never followed.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    identifier = _pull_request_id(pr_id)
    url = (
        f"{base}/rest/api/1.0/projects/{project}/repos/{slug}"
        f"/pull-requests/{identifier}"
    )
    with bearer_session(token) as session:
        value = get_json_object(session, url, params={})
    _validate_pull_request(value, identifier)
    return value


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``PROJECT/slug`` into two safe path segments."""
    project, separator, slug = repo.partition("/")
    if (
        not separator
        or "/" in slug
        or not _PROJECT_KEY.fullmatch(project)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError("Expected a repository as PROJECT/slug.")
    return project, slug


def _pull_request_id(value: str | int) -> int:
    """Return a canonical positive signed 64-bit ID or reject before I/O."""
    invalid = "Expected a pull request ID as a positive signed 64-bit integer."
    if isinstance(value, bool):
        raise AtlaWireError(invalid)
    if isinstance(value, int):
        identifier = value
    elif isinstance(value, str):
        # Length is checked before conversion so huge digit strings cannot stall
        # or hit the interpreter's integer-string conversion limit.
        if len(value) > 19 or not re.fullmatch(r"[1-9][0-9]*", value):
            raise AtlaWireError(invalid)
        identifier = int(value)
    else:
        raise AtlaWireError(invalid)
    if not 1 <= identifier <= _PULL_REQUEST_ID_MAX:
        raise AtlaWireError(invalid)
    return identifier


def _validate_pull_request(value: dict[str, object], pr_id: int) -> None:
    """Require the identity requested and the fields this slice promises."""
    identifier = value.get("id")
    title = value.get("title")
    state = value.get("state")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or identifier != pr_id
        or not isinstance(title, str)
        or not isinstance(state, str)
    ):
        raise AtlaWireError("Invalid pull request identity or fields.")


def _read_pages[RowT](
    session: requests.Session,
    url: str,
    max_pages: int,
    *,
    project: Callable[[object], RowT],
) -> list[RowT]:
    start = 0
    rows: list[RowT] = []
    for _ in range(max_pages):
        page = get_json_object(session, url, params={"start": start, "limit": 100})
        values = page.get("values")
        if not isinstance(values, list):
            raise AtlaWireError("Expected a Bitbucket values array.")
        last = page.get("isLastPage")
        if not isinstance(last, bool):
            raise AtlaWireError("Expected a Bitbucket isLastPage boolean.")
        rows.extend(project(row) for row in values)
        if last:
            return rows
        next_start = page.get("nextPageStart")
        if (
            not isinstance(next_start, int)
            or isinstance(next_start, bool)
            or next_start <= start
        ):
            raise AtlaWireError("Invalid or non-advancing Bitbucket nextPageStart.")
        start = next_start
    raise AtlaWireError("Bitbucket page limit reached; increase --max-pages.")


def _project(value: object) -> Project:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket project object.")
    key, name, description, public = (
        value.get(field) for field in ("key", "name", "description", "public")
    )
    if (
        not isinstance(key, str)
        or not key
        or (name is not None and not isinstance(name, str))
        or (description is not None and not isinstance(description, str))
        or (public is not None and not isinstance(public, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket project.")
    return Project(
        key=key,
        name=name,
        public=public,
        description=description,
        url=_self_url(value.get("links")),
    )


def _self_url(links: object) -> str | None:
    """Return the first self href verbatim, or ``None`` when it is absent."""
    if links is None:
        return None
    if not isinstance(links, dict):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    self_links = links.get("self")
    if self_links is None:
        return None
    if not isinstance(self_links, list):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    if not self_links:
        return None
    first = self_links[0]
    if not isinstance(first, dict):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    href = first.get("href")
    if href is None:
        return None
    if not isinstance(href, str):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    return href


def _repository(value: object) -> Repository:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket repository object.")
    slug, name, state, public = (
        value.get(key) for key in ("slug", "name", "state", "public")
    )
    if (
        not isinstance(slug, str)
        or not slug
        or (name is not None and not isinstance(name, str))
        or (state is not None and not isinstance(state, str))
        or (public is not None and not isinstance(public, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    return Repository(slug=slug, name=name, state=state, public=public)

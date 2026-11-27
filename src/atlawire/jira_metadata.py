"""Read-only Jira 8.22 issue metadata used to prepare a change.

The three fixed reads expose only the screens' field metadata:

* ``GET /rest/api/2/issue/{key}/editmeta`` for the edit screen;
* ``GET /rest/api/2/issue/createmeta`` for every project the caller may
  create in, with field metadata only when ``expand=projects.issuetypes.fields``
  is requested;
* ``GET /rest/api/2/issue/{key}/transitions?expand=transitions.fields`` for the
  transitions currently offered, optionally narrowed to one documented
  ``transitionId``.

None of these calls creates, edits, or transitions an issue: each is a plain
GET on a fixed route derived from the configured base URL and one validated
issue key or project key. This module never follows a returned link and never
lets a pasted browse URL choose the destination host. The complete JSON
document is validated before it is returned; every unknown member, ``null``,
and nested value is preserved unchanged.

Jira Server/Data Center 8.22 documents the legacy ``createmeta`` shape as one
``projects`` array without a pagination envelope (the endpoint is marked
deprecated there but remains available). A later server with a different
createmeta shape fails the documented-shape check instead of being projected.
"""

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)

# Jira project keys are uppercase letters, digits and underscore only. The grammar
# is imported so this module cannot drift into accepting a Bitbucket key shape.
from atlawire.identifiers import JIRA_PROJECT_KEY as _PROJECT_KEY
from atlawire.jira import _issue_key

_API = "rest/api/2"
_CREATE_META_EXPAND = "projects.issuetypes.fields"
_TRANSITION_EXPAND = "transitions.fields"

__all__ = ["get_create_meta", "get_edit_meta", "get_transition_fields"]

_JsonObject = dict[str, object]


def get_edit_meta(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> _JsonObject:
    """Return the edit-screen metadata of one issue exactly as sent.

    Only the validated issue key is taken from ``key_or_url``; the request
    always goes to the configured ``base_url``. The 8.22 response maps field
    IDs to field metadata, and every entry must be an object. Any other shape
    rejects the whole document, so no partial metadata is returned. Unknown
    top-level members and nested values are preserved.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/{_API}/issue/{key}/editmeta", params={}
        )
    _check_field_map(document.get("fields"), "edit metadata")
    return document


def get_create_meta(
    base_url: str,
    *,
    token: str,
    project: str | None = None,
    allow_http_loopback: bool = False,
) -> _JsonObject:
    """Return the create-screen metadata exactly as sent.

    ``project`` is an optional exact uppercase project key and is sent as the
    documented single ``projectKeys`` filter; it never becomes part of the
    path. The fixed ``expand`` value is what makes Jira include each issue
    type's field metadata. The legacy 8.22 ``projects`` array and each present
    ``issuetypes`` array and ``fields`` map are validated as documented objects
    before anything is returned; every issue type must also carry the
    documented non-empty string ``id``. Absent optional members stay absent.
    """
    _check_project(project)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    params = {"expand": _CREATE_META_EXPAND}
    if project is not None:
        params["projectKeys"] = project
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/{_API}/issue/createmeta", params=params
        )
    projects = document.get("projects")
    if not isinstance(projects, list):
        raise AtlaWireError("Expected a Jira create metadata projects array.")
    for value in projects:
        _check_create_project(value)
    return document


def get_transition_fields(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    transition_id: str | None = None,
    allow_http_loopback: bool = False,
) -> _JsonObject:
    """Return the offered transitions and their screen fields exactly as sent.

    Only the validated issue key is taken from ``key_or_url``. The fixed
    ``expand=transitions.fields`` is always requested; an optional
    ``transition_id`` is sent as the documented opaque ``transitionId`` value
    and is never placed in the path. Requests performs the query encoding.
    Each transition and each present ``fields`` map must have the documented
    object shape, and every transition must carry the documented non-empty
    string ``id``, so a malformed late entry rejects the whole document instead
    of publishing part of it. Reading this endpoint never executes the
    transition.
    """
    key = _issue_key(key_or_url)
    _check_transition_id(transition_id)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    params = {"expand": _TRANSITION_EXPAND}
    if transition_id is not None:
        params["transitionId"] = transition_id
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/{_API}/issue/{key}/transitions", params=params
        )
    transitions = document.get("transitions")
    if not isinstance(transitions, list):
        raise AtlaWireError("Expected a Jira transitions array.")
    for value in transitions:
        _check_transition(value)
    return document


def _check_project(project: object) -> None:
    """Reject an unusable project key before any session or request exists."""
    if project is None:
        return
    if not isinstance(project, str) or _PROJECT_KEY.fullmatch(project) is None:
        raise AtlaWireError("Expected an uppercase Jira project key.")


def _check_transition_id(transition_id: object) -> None:
    """Reject an empty, non-UTF-8, or control-bearing transition ID.

    Jira 8.22 documents ``transitionId`` as an opaque string, so no numeric
    grammar or length is assumed. Only values that cannot be one UTF-8 query
    value are rejected; Requests encodes the accepted text, and the value is
    never interpolated into the URL or echoed in a diagnostic.
    """
    if transition_id is None:
        return
    if not isinstance(transition_id, str) or not transition_id:
        raise AtlaWireError("Expected a non-empty Jira transition ID.")
    try:
        transition_id.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(
            "Expected the Jira transition ID as valid UTF-8 text."
        ) from None
    if any(_is_control(char) for char in transition_id):
        raise AtlaWireError("Expected a control-free Jira transition ID.")


def _is_control(char: str) -> bool:
    """Return whether one character is a C0, DEL, or C1 control."""
    code = ord(char)
    return code < 0x20 or 0x7F <= code <= 0x9F


def _check_field_map(value: object, label: str) -> None:
    """Validate one documented field-ID-to-metadata map without projecting it."""
    if not isinstance(value, dict):
        raise AtlaWireError(f"Expected a Jira {label} fields object.")
    for field in value.values():
        if not isinstance(field, dict):
            raise AtlaWireError(f"Expected Jira {label} field objects.")


def _check_create_project(value: object) -> None:
    """Validate one create-metadata project and its optional issue types."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira create metadata project objects.")
    if "issuetypes" not in value:
        return
    issue_types = value["issuetypes"]
    if not isinstance(issue_types, list):
        raise AtlaWireError("Expected a Jira create metadata issuetypes array.")
    for issue_type in issue_types:
        _check_create_issue_type(issue_type)


def _check_create_issue_type(value: object) -> None:
    """Validate one create-metadata issue type, its ID, and optional fields."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira create metadata issue type objects.")
    if "fields" in value:
        _check_field_map(value["fields"], "create metadata issue type")
    if not _has_documented_id(value):
        raise AtlaWireError("Expected Jira create metadata issue type objects.")


def _check_transition(value: object) -> None:
    """Validate one transition, its ID, and its optional screen fields."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira transition objects.")
    if "fields" in value:
        _check_field_map(value["fields"], "transition")
    if not _has_documented_id(value):
        raise AtlaWireError("Expected Jira transition objects.")


def _has_documented_id(value: _JsonObject) -> bool:
    """Return whether an object carries the documented non-empty string ``id``.

    Jira 8.22 documents every create-metadata issue type and every transition
    as an object with a string ``id``. Other members are not inspected, so
    ``subtask`` and plugin values stay untouched.
    """
    issue_id = value.get("id")
    return isinstance(issue_id, str) and bool(issue_id)

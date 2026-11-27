"""Call every registered operation live and record what came back.

The tester fills each declared path argument from a discovered live identifier,
calls the operation through the public reader, and classifies the outcome. It
records the payload's shape only — never its content — and every failure keeps
the sanitized category and HTTP status so a report can be acted on.

Run:
    python checks/live_tester_operations.py [--limit N] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atlawire.credentials import load_saved_credentials  # noqa: E402
from atlawire.http import AtlaWireError  # noqa: E402
from atlawire.operations import list_operations, read_operation  # noqa: E402
from live_tester_discovery import discover  # noqa: E402

# A property key is caller-chosen, so an arbitrary literal is a valid probe:
# the documented answer for an absent property is a 404, not a misuse.
PROPERTY_PROBE = "atlawire.live.test"


def identifier_pool() -> dict[str, object]:
    return discover()


def argument_value(
    product: str, path: str, name: str, pool: dict[str, object]
) -> tuple[object | None, str]:
    """Return (value, source) for one declared path argument, or (None, reason)."""

    if name == "projectKey":
        return pool.get("bitbucket_project_key"), "discovered project"
    if name == "repositorySlug":
        return pool.get("bitbucket_repository_slug"), "discovered repository"
    if name == "commitId":
        return pool.get("bitbucket_commit_id"), "discovered commit"
    if name == "pullRequestId":
        return pool.get("bitbucket_pull_request_id"), "discovered pull request"
    if name == "spaceKey":
        return pool.get("confluence_space_key"), "discovered space"
    if name == "issueIdOrKey":
        return pool.get("jira_issue_key"), "discovered issue"
    if name == "issueTypeId":
        return pool.get("jira_issue_type_id"), "discovered issue type"
    if name == "propertyKey":
        return PROPERTY_PROBE, "arbitrary probe key"
    if name == "projectKeyOrId":
        if product == "jira":
            return pool.get("jira_project_key"), "discovered Jira project"
        return pool.get("bitbucket_project_key"), "discovered Bitbucket project"
    if name == "userSlug":
        return pool.get("bitbucket_user_slug"), "discovered user"
    if name == "groupName":
        return None, "no group is known on this deployment"
    if name == "path":
        return pool.get("bitbucket_file_path"), "discovered file path"
    if name == "projectIdOrKey":
        if product == "jira":
            return pool.get("jira_project_key"), "discovered Jira project"
        return pool.get("bitbucket_project_key"), "discovered Bitbucket project"
    if name == "version":
        if product == "jira":
            return pool.get("jira_version_id"), "discovered version"
        return "1", "arbitrary version probe"
    if name == "type":
        if product == "confluence":
            return pool.get("confluence_content_type"), "discovered content type"
        return pool.get("jira_issue_type_id"), "discovered issue type"
    if name == "commentId":
        if product == "jira":
            return pool.get("jira_comment_id"), "discovered comment"
        return pool.get("confluence_comment_id"), "discovered comment"
    if name == "key":
        if "/property/" in path:
            return PROPERTY_PROBE, "arbitrary probe key"
        if "/issue/" in path or product == "jira":
            return pool.get("jira_issue_key"), "discovered issue"
        return pool.get("bitbucket_branch"), "discovered branch"
    if name == "id":
        # The generic name is resolved by route shape; the first matching rule
        # wins and the source records why.
        if "/attachment/" in path:
            if product == "jira":
                return pool.get("jira_attachment_id"), "route: Jira attachment"
            return pool.get("confluence_attachment_id"), "route: attachment"
        if "pull-requests" in path or "/pullRequest" in path:
            return pool.get("bitbucket_pull_request_id"), "route: pull request"
        if product == "confluence":
            if "comment" in path:
                return pool.get("confluence_comment_id"), "route: confluence comment"
            if "attachment" in path:
                return pool.get("confluence_attachment_id"), "route: attachment"
            return pool.get("confluence_page_id"), "route: confluence content"
        if product == "jira":
            if "worklog" in path:
                return pool.get("jira_worklog_id"), "route: worklog"
            if "comment" in path:
                return pool.get("jira_comment_id"), "route: comment"
            return pool.get("jira_issue_key"), "route: issue"
        if "commit" in path:
            return pool.get("bitbucket_commit_id"), "route: commit"
        return pool.get("bitbucket_pull_request_id"), "route: default"
    return None, f"unmapped argument name {name!r}"


def shape(value: object) -> dict[str, object]:
    """Describe a payload without keeping its content."""
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": len(value),
            "top": sorted(value)[:12],
            "empty": not value,
        }
    if isinstance(value, list):
        first = value[0] if value else None
        return {
            "type": "array",
            "items": len(value),
            "empty": not value,
            "item_type": type(first).__name__ if value else None,
            "item_keys": sorted(first)[:12] if isinstance(first, dict) else None,
        }
    if value is None:
        return {"type": "null", "empty": True}
    return {"type": type(value).__name__, "empty": value == ""}


def required_parameter(detail: str | None) -> str | None:
    """Return the parameter name a server said is required, when it named one.

    The phrasings observed on this deployment are listed in the report builder.
    A name that is also a common word is still a name: excluding ``path`` once
    hid the real defect on ``bitbucket.repository.raw``, so only pure grammar
    words are skipped here.
    """
    if not detail:
        return None
    import re as _re

    patterns = (
        r'The "?(?P<name>\w+)"? (?:query )?parameter is required',
        r"The parameter ['\"](?P<name>\w+)['\"] is required",
        r"^(?P<name>\w+) query parameter is required",
        r"Required field ['\"](?P<name>\w+)['\"]",
        r"(?P<name>\w+): '\w+' is required",
    )
    for pattern in patterns:
        match = _re.search(pattern, detail)
        if match:
            return match.group("name")
    return None


def run(limit: int | None, out: Path) -> int:
    pool = identifier_pool()
    operations = list_operations()
    if limit:
        operations = operations[:limit]

    results = []
    for number, operation in enumerate(operations, 1):
        arguments = {}
        blocked = None
        sources = {}
        for argument in operation.get("arguments") or []:
            name = argument["name"]
            value, source = argument_value(
                operation["product"], operation["path"], name, pool
            )
            if value in (None, ""):
                blocked = f"{name}: {source}"
                break
            arguments[name] = str(value)
            sources[name] = source

        record = {
            "id": operation["id"],
            "product": operation["product"],
            "path": operation["path"],
            "scope": operation.get("scope"),
            "arguments": arguments,
            "argument_sources": sources,
            "query_declared": len(operation.get("query") or []),
        }

        if blocked is not None:
            record.update(outcome="blocked", reason=blocked)
            results.append(record)
            print(f"[{number:3}/{len(operations)}] BLOCKED {operation['id']} — {blocked}")
            continue

        saved = load_saved_credentials(
            operation["product"], allow_http_loopback=False
        )
        try:
            payload = read_operation(
                operation["id"],
                saved.base_url,
                token=saved.token,
                arguments=arguments,
                allow_admin=operation.get("scope") == "admin",
            )
        except AtlaWireError as exc:
            detail = (exc.detail or "")[:400] or None
            missing = required_parameter(detail)
            record.update(
                outcome="failed",
                category=exc.category,
                status=exc.http_status,
                detail=detail[:200] if detail else None,
            )
            if missing and not record.get("query_declared"):
                # A registered route that cannot be called because the registry
                # does not declare a parameter the server requires.
                record["registry_gap"] = (
                    f"server requires query parameter {missing!r}; "
                    "the registry declares none"
                )
            elif missing:
                record["registry_gap"] = (
                    f"server requires query parameter {missing!r}; "
                    f"declared: {[f['name'] for f in operation.get('query') or []]}"
                )
            print(
                f"[{number:3}/{len(operations)}] FAIL {operation['id']} — "
                f"{exc.category} {exc.http_status}"
                + (f" | needs {missing}" if missing else "")
            )
        else:
            described = shape(payload)
            record.update(outcome="ok", shape=described)
            mark = "EMPTY" if described.get("empty") else "OK"
            print(f"[{number:3}/{len(operations)}] {mark:5} {operation['id']}")
        results.append(record)

    summary = Counter(record["outcome"] for record in results)
    document = {
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "operations": len(results),
        "summary": dict(summary),
        "identifiers": pool,
        "results": results,
    }
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nsummary: {dict(summary)}")
    print("written:", out)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("checks/live_tester_operations.json"),
    )
    options = parser.parse_args()
    raise SystemExit(run(options.limit, options.out))

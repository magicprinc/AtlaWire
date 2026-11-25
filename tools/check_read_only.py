"""Prove that no declared operation can change server state.

The registry is the promise that an agent can explore without harming anything.
A GET is not proof of a read - Jira documents `GET /issue/{key}/subtask/move`,
which changes state - so every declared operation is checked twice:

1. **Method.** Only GET, plus three audited semantic POSTs whose body carries a
   query document rather than a change.
2. **Documented purpose.** The first word of the documentation states what the
   call does. `Returns`, `Get`, `Retrieves`, `Searches` are reads; `Delete`,
   `Move`, `Create`, `Update` are not. Reading only the opener avoids flagging
   nouns later in a sentence ("links", "grants", "transitions").

Anything that fails must be removed from the registry or added to one of the two
tables below with a reason, so the exception is auditable rather than remembered.

    python -B tools/check_read_only.py
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import wadl_surface as wadl

from atlawire import operations

# The only non-GET methods allowed, each with the reason it cannot change state.
AUDITED_POSTS = {
    "confluence.content.convert": "storage-to-view conversion; writes nothing",
    "jira.search.post": "JQL search carried in a body; writes nothing",
    "jira.worklog.list": "worklogs for a set of issues; writes nothing",
}

# Imperative openers that state a change as the purpose of the call.
MUTATING_OPENER = re.compile(
    r"^(delete|deletes|remove|removes|create|creates|add|adds|update|updates|"
    r"set|sets|change|changes|move|moves|edit|edits|grant|grants|revoke|revokes|"
    r"assign|assigns|unassign|transition|transitions|attach|attaches|detach|"
    r"link|links|unlink|unlinks|merge|merges|decline|declines|approve|approves|"
    r"reopen|reopens|archive|archives|restore|restores|purge|purges|upload|"
    r"uploads|replace|replaces|rename|renames|copy|copies|enable|enables|"
    r"disable|disables|activate|activates|deactivate|reindex|reindexes|"
    r"reset|resets|invalidate|regenerate|trigger|triggers|publish|publishes|"
    r"migrate|migrates|execute|executes|run|runs)\b",
    re.IGNORECASE,
)

# Routes whose documented opener reads as a change but which only return data.
DOCUMENTED_EXCEPTIONS = {
    "bitbucket.projects.projectkey.repos.repositoryslug.pull-requests.pullrequestid.merge": (
        "GET /merge answers whether the pull request can be merged; it does not merge"
    ),
    "jira.reindex": "GET /reindex returns the reindex status; it starts nothing",
    "jira.reindex.progress": "returns reindex progress",
    "jira.reindex.request.bulk": "returns the progress of bulk reindex requests",
    "jira.reindex.request.requestid": "returns the progress of one reindex request",
    "jira.user.anonymization": "GET validates the anonymization; the POST performs it",
    "jira.user.anonymization.rerun": (
        "GET validates the anonymization re-run; the POST performs it"
    ),
    "jira.worklog.deleted": "returns ids of worklogs deleted since a time",
    "jira.worklog.updated": "returns ids of worklogs updated since a time",
    "confluence.user.watch.content.contentid": (
        "GET /watch/... reports whether the user watches the content"
    ),
    "confluence.user.watch.space.spacekey": (
        "reports whether the user watches the space"
    ),
    "bitbucket.repository.archive": "streams a repository archive; writes nothing",
    "bitbucket.projects.projectkey.repos.repositoryslug.pull-requests.pullrequestid": (
        "the prose mentions a possible state of the pull request being read"
    ),
}


def _first_word(doc: str) -> str:
    cleaned = doc.strip().lstrip("_*`# ")
    match = re.match(r"^[A-Za-z]+", cleaned)
    return match.group(0) if match else ""


def _documented_methods() -> dict[tuple[str, str, str], str]:
    docs: dict[tuple[str, str, str], str] = {}
    for product in wadl.PRODUCTS:
        _, methods = wadl.load(product)
        for method in methods:
            if method.verb == "GET":
                docs[(product, method.verb, wadl.normalize(method.route))] = method.doc
    return docs


def audit() -> list[str]:
    """Return one line per operation that is not provably a read."""
    problems: list[str] = []
    docs = _documented_methods()
    for described in operations.list_operations():
        operation_id = str(described["id"])
        method = str(described["method"])
        if method == "POST":
            if operation_id not in AUDITED_POSTS:
                problems.append(f"{operation_id}: POST without an audited reason")
            continue
        if method != "GET":
            problems.append(f"{operation_id}: method {method} is not a read")
            continue
        if operation_id in DOCUMENTED_EXCEPTIONS:
            continue
        product = str(described["product"])
        relative = str(described["path"]).removeprefix(wadl.REST_PREFIX[product])
        doc = ""
        for variant in wadl.route_variants(relative):
            doc = docs.get((product, "GET", variant), "")
            if doc:
                break
        word = _first_word(doc)
        if word and MUTATING_OPENER.match(word):
            problems.append(f"{operation_id}: documentation opens with '{word}'")
    return problems


def main() -> int:
    described = operations.list_operations()
    methods = Counter(str(item["method"]) for item in described)
    admin = sum(1 for item in described if item["scope"] == "admin")
    problems = audit()

    print(
        f"declared operations: {len(described)} ({admin} admin, {len(described) - admin} read)"
    )
    print(f"methods: {dict(sorted(methods.items()))}")
    print(
        f"non-GET operations: {len(AUDITED_POSTS)} audited, {len(methods) - 1} method kind(s)"
    )
    for operation_id, reason in sorted(AUDITED_POSTS.items()):
        print(f"   POST {operation_id}: {reason}")
    if problems:
        print(f"\nnot provably read-only: {len(problems)}")
        for line in problems:
            print(f"   {line}")
        return 1
    print("\nRESULT: every declared operation only reads")
    return 0


if __name__ == "__main__":
    sys.exit(main())

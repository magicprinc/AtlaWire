"""Walk every CLI command as a client would, with arguments its own help accepts.

The point is not to prove the tool works: it is to record every command that
cannot be used, with the exact invocation and the exact failure. Arguments come
from the command's own catalog entry, values come from discovered identifiers.

Run:
    python checks/live_tester_cli_full.py [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_tester_discovery import discover  # noqa: E402

PYTHON = sys.executable


def value_for(product: str, name: str, pool: dict[str, object]):
    """Return a plausible value for one positional argument, or None."""
    bitbucket_repo = (
        f"{pool.get('bitbucket_project_key')}/{pool.get('bitbucket_repository_slug')}"
    )
    table = {
        "product": product,
        "path": "/rest/api/2/myself" if product == "jira" else "/rest/api/1.0/projects",
        "method": "GET",
        "repo": bitbucket_repo,
        "project": str(pool.get("bitbucket_project_key")),
        "project_key": str(pool.get("bitbucket_project_key")),
        "slug": str(pool.get("bitbucket_repository_slug")),
        "name": str(pool.get("bitbucket_branch") or pool.get("jira_user")),
        "path": str(pool.get("bitbucket_file_path")),
        "sha": str(pool.get("bitbucket_commit_id")),
        "commit_id": str(pool.get("bitbucket_commit_id")),
        "comment_id": str(pool.get("jira_comment_id")),
        "pr_id": str(pool.get("bitbucket_pull_request_id")),
        "repo_or_url": bitbucket_repo,
        "attachment_id": str(pool.get("confluence_attachment_id") or "1"),
        "key_or_url": str(pool.get("jira_issue_key")),
        "query": "order by created DESC",
        "terms": "README",
        "pattern": "README",
        "page_id_or_url": str(pool.get("confluence_page_id")),
        "space_key": str(pool.get("confluence_space_key")),
        "link_id": "1",
        "property_key": "atlawire.probe",
        "worklog_id": str(pool.get("jira_worklog_id") or "1"),
        "version": "1",
        "until": str(pool.get("bitbucket_commit_id")),
        "operation_id": "",
        "action": "",
    }
    value = table.get(name)
    return None if value in (None, "", "None") else value


def catalog() -> dict[str, dict]:
    completed = subprocess.run(
        [PYTHON, "-B", "-m", "atlawire", "--catalog"],
        capture_output=True, text=True, encoding="utf-8-sig", check=False,
    )
    return json.loads(completed.stdout)["commands"]


def product_of(name: str) -> str:
    if name.startswith(("issue", "jira", "jql", "transitions", "titles")):
        return "jira"
    if name.startswith(("page", "space", "children", "cql", "convert")):
        return "confluence"
    return "bitbucket"


# Arguments that change the meaning of a command and are safe to add.
SAFE_ADDITIONS = {
    "read": ["--params", "{}"],
    "read-operation": ["--params", "{}"],
    "pr": ["--json"],
    "api-get": [],
    "api-request": [],
}

SKIP = {"login", "selftest"}  # interactive prompt / not a product read


def run(argv: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(  # noqa: S603 - fixed argv, resolved interpreter
        [PYTHON, "-B", "-m", "atlawire", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def main(out: Path) -> int:
    pool = discover()
    commands = catalog()
    results = []

    for name in sorted(commands):
        record = {"command": name}
        if name in SKIP:
            record.update(outcome="skipped", reason="interactive or self-check")
            results.append(record)
            continue

        body = commands[name]
        params = body.get("params") or []
        positionals = [
            p["opts"][0] for p in params
            if p.get("opts") and not p["opts"][0].startswith("--")
        ]
        required = [p["opts"][0] for p in params if p.get("required") and p.get("opts")]
        product = product_of(name)

        argv = [name]
        missing = None
        for positional in positionals:
            if positional in required or positional in {
                "repo", "project", "project_key", "slug", "key_or_url", "page_id_or_url"
            }:
                value = value_for(product, positional, pool)
                if value is None:
                    missing = positional
                    break
                argv.append(value)
        if missing:
            record.update(outcome="blocked", reason=f"no identifier for {missing}")
            results.append(record)
            continue

        argv.extend(SAFE_ADDITIONS.get(name, []))

        code, stdout, stderr = run(argv)
        record.update(argv=argv, exit=code)
        record["stdout_kind"] = (
            "json" if stdout.strip().startswith(("{", "["))
            else "empty" if not stdout.strip() else "text"
        )
        if code == 0:
            record["outcome"] = "ok"
        else:
            message = (stderr or stdout).strip().splitlines()
            record["outcome"] = "failed"
            record["error"] = message[0][:200] if message else "(no message)"
            record["error_all"] = " / ".join(m[:160] for m in message[:3])
        results.append(record)
        print(f"{record['outcome']:8} {name:24} exit={code}")

    summary = Counter(record["outcome"] for record in results)
    document = {
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "commands": len(results),
        "summary": dict(summary),
        "results": results,
    }
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\nsummary: {dict(summary)}")
    print("written:", out)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("checks/live_tester_cli_full.json"))
    options = parser.parse_args()
    raise SystemExit(main(options.out))

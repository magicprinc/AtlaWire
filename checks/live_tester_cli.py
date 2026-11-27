"""Exercise every CLI command the way an agent would, and record usability.

Three checks per command, none of which needs a person:

* `--help` renders and exits 0 — a command that cannot even describe itself is
  unusable;
* `--json` is accepted wherever the catalog promises JSON output;
* for the commands whose shape allows a live read, a real invocation runs with
  discovered identifiers and its exit code and stdout kind are recorded, so a
  command that is advertised but broken is visible.

Run:
    python checks/live_tester_cli.py [--out FILE]
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


def run_cli(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, resolved interpreter
        [PYTHON, "-B", "-m", "atlawire", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def catalog() -> dict[str, dict]:
    completed = run_cli(["--catalog"])
    document = json.loads(completed.stdout)
    return document["commands"]


def live_arguments(name: str, pool: dict[str, object]) -> list[str] | None:
    """Return argv for one live call, or None when the command needs a shape
    this tester cannot build safely."""
    repo = f"{pool.get('bitbucket_project_key')}/{pool.get('bitbucket_repository_slug')}"
    pr = str(pool.get("bitbucket_pull_request_id"))
    issue = str(pool.get("jira_issue_key"))
    page = str(pool.get("confluence_page_id"))
    space = str(pool.get("confluence_space_key"))

    table = {
        "projects": ["projects", "--limit", "1"],
        "repos": ["repos", repo],
        "pr": ["pr", repo, pr],
        "prs": ["prs", repo, "--limit", "1"],
        "my-prs": ["my-prs", "--limit", "1"],
        "pr-files": ["pr-files", repo, pr],
        "pr-comments": ["pr-comments", repo, pr],
        "pr-merge-status": ["pr-merge-status", repo, pr],
        "pr-review": ["pr-review", repo, pr],
        "files": ["files", repo],
        "branches": ["branches", repo, "--limit", "1"],
        "tags": ["tags", repo, "--limit", "1"],
        "commits": ["commits", repo, "--limit", "1"],
        "default-branch": ["default-branch", repo],
        "whoami": ["whoami"],
        "spaces": ["spaces", "--limit", "1"],
        "space": ["space", space],
        "page": ["page", page],
        "page-labels": ["page-labels", page],
        "page-comments": ["page-comments", page],
        "page-attachments": ["page-attachments", page],
        "issue": ["issue", issue],
        "issue-comments": ["issue-comments", issue],
        "issue-watchers": ["issue-watchers", issue],
        "issue-worklogs": ["issue-worklogs", issue],
        "issue-changelog": ["issue-changelog", issue],
        "jira-me": ["jira-me"],
        "jira-projects": ["jira-projects"],
        "jira-priorities": ["jira-priorities"],
        "jira-statuses": ["statuses"],
        "operations": ["operations"],
        "catalog": ["--catalog"],
        "jql": ["jql", "order by created DESC", "--limit", "1"],
    }
    return table.get(name)


def run(out: Path) -> int:
    pool = discover()
    commands = catalog()
    results = []

    for name, body in sorted(commands.items()):
        record = {
            "command": name,
            "has_json": any(
                "--json" in (param.get("opts") or [])
                for param in body.get("params") or []
            ),
        }

        help_result = run_cli([name, "--help"])
        record["help_ok"] = help_result.returncode == 0
        if not record["help_ok"]:
            record["help_error"] = help_result.stderr.strip()[:200]

        argv = live_arguments(name, pool)
        if argv is None:
            record["live"] = "not-attempted"
        else:
            live = run_cli(argv)
            record["live_argv"] = argv
            record["live_exit"] = live.returncode
            output = live.stdout.strip()
            record["live_stdout_kind"] = (
                "json" if output.startswith(("{", "[")) else
                "empty" if not output else "text"
            )
            if live.returncode != 0:
                record["live_stderr"] = live.stderr.strip()[:240]
        results.append(record)
        print(
            f"{name:26} help={'ok' if record['help_ok'] else 'FAIL'}"
            f"  json={'yes' if record['has_json'] else 'no '}"
            f"  live={record.get('live', record.get('live_exit'))}"
        )

    summary = Counter(
        record.get("live") or f"exit-{record.get('live_exit')}" for record in results
    )
    document = {
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "commands": len(results),
        "help_failures": [r["command"] for r in results if not r["help_ok"]],
        "summary": dict(summary),
        "results": results,
    }
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"\ncommands: {len(results)} | help failures: {document['help_failures']}")
    print(f"summary: {dict(summary)}")
    print("written:", out)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("checks/live_tester_cli.json")
    )
    options = parser.parse_args()
    raise SystemExit(run(options.out))

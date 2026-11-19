# AtlaWire

**Every endpoint. Every era. One CLI.**

**Complete API access to Atlassian Jira, Confluence & Bitbucket for AI agents. Supports self-hosted and legacy versions.**

AtlaWire is an agent-first command-line interface for working with corporate Atlassian installations. It provides one consistent interface to Jira, Confluence, and Bitbucket—including older **Server** and **Data Center** deployments that many agent integrations overlook.

> **Project status:** Early design / README draft. The command examples below describe the proposed CLI and are **not yet verified against a released implementation**. Compatibility and coverage claims will be validated by automated tests and a documented version matrix.

## Why AtlaWire?

AI coding agents need more than a handful of hard-coded Jira or Confluence operations. They need dependable access to the full functionality exposed by the organization's installed versions, without requiring an MCP server or a cloud service.

- **One CLI, three products:** Jira, Confluence, and Bitbucket.
- **Self-hosted first:** Designed for private corporate networks, VPNs, and on-premises Server / Data Center installations.
- **Legacy-aware:** Product-specific API versions and authentication differences, rather than assuming the newest Cloud API.
- **Broad API reach:** Human-friendly commands backed by [`atlassian-python-api`](https://github.com/atlassian-api/atlassian-python-api), plus a generic REST passthrough for endpoints without a dedicated wrapper.
- **Agent-ready:** Machine-readable JSON, stable command names, predictable exit codes, non-interactive operation, and controlled pagination.
- **Lightweight integration:** Invoke it from a shell, CI job, or any coding-agent harness; no persistent background service required.

## Scope

| Product | Target capabilities |
| --- | --- |
| **Jira** | Issues, JQL, projects, users, workflows, comments, attachments, agile boards/sprints, administration, and other version-available APIs |
| **Confluence** | Spaces, pages, content search, labels, comments, attachments, permissions, and other version-available APIs |
| **Bitbucket** | Projects, repositories, branches, commits, pull requests, diffs, comments, permissions, and other version-available APIs |
| **Raw REST** | GET / POST / PUT / PATCH / DELETE against a configured Atlassian instance, subject to permissions and that server's supported API |

**What “complete API access” means:** The generic REST command is intended to reach documented endpoints even when there is no purpose-built CLI command or upstream Python wrapper. It does **not** mean that every endpoint exists on every Atlassian version, or that all endpoints have dedicated typed commands. Server permissions and product/version-specific APIs still apply. The supported-version matrix will be published as testing progresses.

## Quick start (proposed)

**Requirements:** [Python 3.15](https://www.python.org/downloads/) and [uv](https://github.com/astral-sh/uv).

After cloning the repository:

```shell
uv python install 3.15
uv sync --python 3.15
uv run atlawire --help
```

Once the package is published, the intended standalone installation is:

```shell
uv tool install --python 3.15 atlawire
```

### Configure an instance

```shell
atlawire profile add corp \
  --jira-url https://jira.example.internal \
  --confluence-url https://confluence.example.internal \
  --bitbucket-url https://bitbucket.example.internal

# Prompt securely for the product credential (no secret in command history).
atlawire auth set --profile corp --product jira
atlawire auth set --profile corp --product confluence
atlawire auth set --profile corp --product bitbucket
```

Configuration supports named profiles for multiple corporate environments. Credentials must not be stored in plaintext configuration files or passed as normal positional CLI arguments. The intended storage mechanism is the operating system's credential store or an explicitly configured environment/secret provider.

Authentication must account for product versions: Server/Data Center personal access tokens where available, and supported alternatives for older installations. Atlassian Cloud is **not** the primary target of the initial release.

### Example commands

```shell
# Jira: retrieve an issue
atlawire --profile corp jira issue get APP-123 --json

# Jira: query issues
atlawire --profile corp jira issue search \
  --jql 'project = APP ORDER BY updated DESC' --limit 50 --json

# Confluence: retrieve a page
atlawire --profile corp confluence page get 123456 --json

# Bitbucket: list repositories in a project
atlawire --profile corp bitbucket repo list --project APP --json

# Call an endpoint without a dedicated command
atlawire --profile corp api request jira GET \
  /rest/api/2/issue/APP-123 --json

# Explicitly authorize a mutating REST operation
atlawire --profile corp api request jira POST \
  /rest/api/2/issue --data @issue.json --write --json
```

All commands are **illustrative design targets**. Actual names and flags will be finalized together with the implementation.

## Designed for AI agents

AtlaWire should treat scripting and automation as first-class use cases:

- **JSON-first output:** Valid JSON on stdout; diagnostics on stderr. No banners, prompts, color codes, or progress bars in machine-readable output.
- **Stable errors:** Documented exit codes and structured error payloads for authentication, authorization, network, rate-limit, validation, and server failures.
- **Discoverability:** Helpful `--help` output, operation listing, and examples that an agent can inspect without guessing endpoint names.
- **Bounded responses:** Explicit `--limit`, `--page-size`, and opt-in `--all` pagination; streaming output for large result sets where feasible.
- **Safe writes:** Read-only by default for generic API access; mutating requests require `--write`. Destructive convenience commands require explicit confirmation or an automation-specific approval flag.
- **Reliable HTTP:** Configurable timeouts, proxy and certificate handling, rate-limit awareness, and retries restricted to operations that are safe to retry.
- **Secure by default:** TLS verification enabled; sensitive headers and tokens redacted; outgoing REST paths constrained to the configured instance to avoid credential leakage.
- **No fabricated results:** Unsupported endpoints and server-version mismatches produce explicit failures, never silent success or guessed data.

The goal is to make the CLI usable directly by agents such as OpenCode, Codex, and other shell-capable harnesses, without tying the project to any particular agent protocol.

## Implementation

- **Language:** [Python 3.15](https://www.python.org/)
- **Atlassian integration:** [`atlassian-python-api`](https://github.com/atlassian-api/atlassian-python-api)
- **CLI:** [Click](https://github.com/pallets/click) (proposed)
- **Package / dependency management:** [uv](https://github.com/astral-sh/uv), `pyproject.toml`, and a committed `uv.lock`
- **Architecture:** CLI → operation registry / service layer → Atlassian Python API → authenticated raw REST fallback

Atlassian's Server/Data Center and Cloud API families differ. Version-specific behavior should be isolated behind adapters and covered by explicit compatibility tests, not scattered throughout command implementations.

## Testing and quality engineering

**Correctness takes priority over the number of tests.** The test suite must challenge behavior at the CLI boundary, HTTP boundary, and version-adapter boundary rather than only mocking internal application methods.

| Layer | Tools | Required checks |
| --- | --- | --- |
| Formatting and linting | [Ruff](https://github.com/astral-sh/ruff) | Consistent formatting; strict rules for bugs, imports, complexity, security-related patterns |
| Static types | [Pyright](https://github.com/microsoft/pyright), [mypy](https://github.com/python/mypy) | Strict type checking, particularly on JSON decoding, adapters, and command contracts |
| Unit and CLI tests | [pytest](https://github.com/pytest-dev/pytest) | Argument validation, stdout/stderr separation, exit codes, configuration, permissions, and failures |
| Property-based tests | [Hypothesis](https://github.com/HypothesisWorks/hypothesis) | Pagination invariants, serialization, URL/path handling, encodings, and malformed input |
| HTTP and contract tests | [responses](https://github.com/getsentry/responses) | Mock actual Requests HTTP traffic: authentication, API variations, 401/403/404/429/5xx, timeouts, and retries |
| Coverage | [coverage.py](https://github.com/nedbat/coveragepy), [pytest-cov](https://github.com/pytest-dev/pytest-cov) | Statement + branch coverage; inspect missing branches, not only aggregate percentages |
| Mutation testing | [mutmut](https://github.com/boxed/mutmut) | Ensure tests detect deliberately introduced faults in core logic |
| Parallel / bounded tests | [pytest-xdist](https://github.com/pytest-dev/pytest-xdist), [pytest-timeout](https://github.com/pytest-dev/pytest-timeout) | Detect order coupling, prevent hanging tests |
| Security / dependencies | [Bandit](https://github.com/PyCQA/bandit), [pip-audit](https://github.com/pypa/pip-audit), [Gitleaks](https://github.com/gitleaks/gitleaks) | Risky code patterns, known vulnerable dependencies, and leaked secrets |

### Testing requirements

1. **Unit tests:** Each command and adapter must cover successful execution, invalid input, empty results, malformed responses, and error translation.
2. **CLI contract tests:** Verify parsable JSON, schema stability, stderr/stdout isolation, exit codes, non-interactive execution, and secret redaction.
3. **Fault-injection tests:** Simulate disconnects, slow servers, invalid TLS certificates, expired credentials, `429 Retry-After`, partial pagination, and transient server errors. Prove non-idempotent writes are not retried blindly.
4. **Property-based tests:** Exercise edge cases such as Unicode, escaping, missing fields, unexpected JSON types, malformed URLs, and repeated page tokens.
5. **Cross-version contract tests:** Maintain fixtures and (where available) live integration environments for supported Jira, Confluence, and Bitbucket Server/Data Center versions. Never infer compatibility from a single modern API response.
6. **Optional live integration suite:** Run against explicitly configured test instances using least-privilege credentials; **never** modify production data or require private infrastructure for ordinary CI.
7. **Mutation tests:** Run regularly on security-sensitive and failure-handling code to measure whether assertions actually catch regressions.

**Proposed initial quality gates** (adjust using a measured baseline):

- Zero failing automated tests, Ruff errors, or strict type-checking errors.
- At least **95% combined coverage** with branch measurement on the core application package; all critical error paths tested explicitly.
- At least **85% mutation score** for selected security, retry, pagination, and command-contract modules.
- No unreviewed high-severity security findings or dependency vulnerabilities.
- CI on **Windows and Linux**, with Python **3.15** as the primary runtime.

### Developer checks (proposed)

```shell
uv sync --python 3.15 --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src/atlawire
uv run pyright
uv run pytest -q --cov=atlawire --cov-branch \
  --cov-report=term-missing --cov-report=xml --cov-fail-under=95
uv run bandit -r src/atlawire
uv run pip-audit
```

Mutation testing:

```shell
uv run mutmut run
uv run mutmut results
```

**Windows note:** `mutmut` 3 requires a fork-capable OS. Run mutation tests in **WSL or Linux CI**, not native Windows. Routine linting, typing, coverage, and pytest tests should run natively on Windows.

The commands above depend on development dependencies and tool configuration being added to `pyproject.toml` as the implementation takes shape.

## Roadmap

- [ ] Core CLI, profiles, credential handling, and structured error model
- [ ] Jira, Confluence, and Bitbucket commands built on `atlassian-python-api`
- [ ] Authenticated generic REST passthrough with safety checks
- [ ] CLI operation discovery, bounded pagination, and stable JSON output
- [ ] Realistic cross-version API fixtures and compatibility matrix
- [ ] Windows/Linux CI with linting, strict typing, coverage, and security gates
- [ ] Mutation testing and opt-in live integration environments
- [ ] Packaging, releases, documentation, and agent integration examples

## License

To be determined before public release.

## Acknowledgments

AtlaWire uses the community-maintained [Atlassian Python API](https://github.com/atlassian-api/atlassian-python-api), distributed under the Apache-2.0 license. AtlaWire is an independent project and is not affiliated with or endorsed by Atlassian.

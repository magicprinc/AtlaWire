# Verification receipt

Generated: 2026-11-27, against commit `c587237`, one live self-hosted deployment.

This file records what was executed, on which versions, with which exit codes.
It answers one question: *was this build actually checked, and how?* A green test
run on a stale baseline is not evidence, so the commit and the environment are
pinned here.

## Environment

| | |
| --- | --- |
| Python | 3.15.2 (`C:\Python315\python.exe`) |
| atlawire | 0.9.10, installed from this checkout |
| click | 8.5.1 |
| requests | 2.34.2 |
| markdownify | 1.2.4 |
| Platform | Windows 10.0.19045 |
| Dependency count | 46 packages in `uv.lock` |

## Checks executed

Every command below was run in the repository root and its exit code recorded.

| Check | Command | Exit | Result |
| --- | --- | --- | --- |
| Syntax, every module | `python -m compileall -q src tests checks tools` | 0 | clean |
| Import, every module | import all 27 `atlawire.*` modules | 0 | 0 failures |
| Full test suite | `python -B -m pytest -p no:cacheprovider -q` | 0 | **1192 passed, 2 skipped** |
| Lint | `python -m ruff check src tests checks tools` | 0 | All checks passed |
| Security lint | `python -m ruff check --select S src` | 0 | All checks passed |
| Format | `python -m ruff format --check src tests checks tools` | 0 | 142 files |
| Types | `python -m pyright src` | 0 | 0 errors, 0 warnings |
| Dependency CVEs | `python -m pip_audit` | 0 | No known vulnerabilities |
| Lockfile | `python -m uv lock --check --offline` | 0 | 46 packages resolved |
| REST inventory | `python -B tools/build_rest_inventory.py --check` | 0 | two-way check passed; 252 rows, 199 required, 53 excluded, 317 runtime |
| Query surface | `python -B tools/build_query_surface.py --check` | 0 | 94 operations |
| Admin surface | `python -B tools/build_admin_surface.py --check` | 0 | 117 operations, 5 deferred |
| API surface | `python -B tools/check_api_surface.py --check` | 0 | matches the baseline |
| Read-only audit | `python -B tools/check_read_only.py` | 0 | every declared operation only reads |
| Wheel build | `python -m pip wheel . --no-deps -w dist` | 0 | `atlawire-0.9.10-py3-none-any.whl`, sha256 `313fad05…` |
| Installed wheel | install into `target/0.9.10`, run `atlawire.exe` | 0 | 317 operations; `read`/`api-get` failures exit 2 with a JSON envelope |

### The two skips

`tests/test_spec_login_command.py::test_the_saved_file_is_owner_only` and
`tests/test_spec_review_fixes.py::test_a_new_credentials_directory_is_created_private`
skip on Windows: both assert POSIX mode bits (`0o600`/`0o700`), which Windows does
not express. The same contract is enforced by the code (`os.chmod` is best-effort
and the profile ACL is the real boundary), and each skip is declared in the test
itself rather than silently disabled.

### pip-audit's two skipped names

`pip-audit` reports `atlawire` and `devinoai` as "not found on PyPI". Neither is
published anywhere; they cannot be audited by a registry lookup. Every third-party
dependency they pull is audited, and the run reports no known vulnerabilities.

## Live checks

These ran against the configured deployment with a read-only personal access
token. They prove deployed behaviour, not unit behaviour.

| Check | Result |
| --- | --- |
| `jira-me` | identity returned |
| `issue INC-1753 --json` | document with `expand`, `fields`, `id`, `key`, `self` |
| `spaces --limit 1 --json` | one row |
| `repos AB --limit 1` | one row |
| `titles INC-1753 PLAT-4328` | both summaries returned |
| `issue-url INC-1753` | browser URL |
| `commit-comments --path .gitignore` | exit 0 |
| `--token-from-env` path | token accepted, request reached the transport |
| Raw file download | 461 bytes, sha256 `6602b9ee…` |
| Avatar binary read | 3 098 bytes, `image/png` |

The full tester sweep (`checks/live_tester_*.py`) is the broader evidence: 317
registered operations, 472 declared query fields, 92 CLI commands, the public
Python API, and 73 BBK functions. Its output lives in `checks/live_tester_*.json`
and its findings in `checks/TEST-FINDINGS.md`.

## What this receipt does not prove

- **One deployment.** Another host, another version, or another permission set may
  behave differently. The report separates what failed from what could not be
  reached.
- **A clean-wheel install.** The installed tree at `target/0.9.10` is built from
  this wheel into a target directory; the console entry point is exercised, but a
  fresh machine install is not.
- **Administrative surfaces.** The token is read-only by design; the 62
  administrative refusals are the boundary working, not a coverage result.
- **Absence of defects.** Green checks are evidence, not proof. The next tester
  pass exists for exactly this reason.

## Reproduce

```bash
python -m compileall -q src tests checks tools
python -B -m pytest -p no:cacheprovider -q
python -m ruff check src tests checks
python -m ruff format --check src tests checks
python -m pyright src
python -m pip_audit
python -m uv lock --check --offline
python -B tools/build_rest_inventory.py --check
python -B tools/build_query_surface.py --check
python -B tools/build_admin_surface.py --check
python -B tools/check_api_surface.py --check
python -B tools/check_read_only.py
```

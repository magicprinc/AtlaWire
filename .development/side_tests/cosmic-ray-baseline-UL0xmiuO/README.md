# Cosmic Ray baseline candidate

Upstream: https://github.com/sixty-north/cosmic-ray  
Base commit: `6c490ce16443d0c6c11edd6e6d36c34b153c8607`

## Contents

- `production.patch`: changes only `src/cosmic_ray/cli.py`.
- `test_baseline_outcomes.py` and `test_baseline_worker_results.py`: place in
  `tests/e2e/` in a matching upstream checkout.

Apply the patch with `git apply production.patch` from that checkout, using the
actual path to the patch. Copy the tests without overwriting existing work.
Inspect the checkout and patch before applying them.

**Exclude `docs/make.bat` completely.** The original Windows clone showed an
unrelated line-ending difference in that file immediately after checkout; it is
not part of this candidate.

## Verification already performed

Windows, Python 3.15.2, pytest 9.2.0, Ruff 0.17.5. The following command is
shown with the isolated temporary directory redacted; it used a sanitized
environment, existing dependencies, and disabled pytest plugin autoload:

```text
python -m pytest -p no:cacheprovider --basetemp=<isolated-temp> tests/e2e/test_baseline_outcomes.py tests/e2e/test_baseline_worker_results.py -q --tb=short
```

- Current candidate: exit 0; 18 passed, 0 failed, 0 skipped.
- Earlier test revision against a controlled faulty variant restoring the
  original success condition: exit 1; 8 failed, 8 passed. The same command used
  `--tb=no` and a separate temporary directory. The candidate condition was
  restored afterward.
- The current startup-timeout regression was run with the fixture's cleanup
  deliberately removed: exit 1, one failure at the cleanup assertion. The
  cleanup was restored before the 18-test run.
- The following existing baseline E2E selections: exit 0; 5 passed.

```text
python -m pytest --basetemp=<isolated-temp> tests/e2e/test_e2e.py::test_baseline_with_explicit_session_file tests/e2e/test_e2e.py::test_baseline_with_temp_session_file tests/e2e/test_e2e.py::test_baseline_with_pytest_filter -q --tb=short
```

That run disabled the cache provider via `PYTEST_ADDOPTS`.

- `ruff check src/cosmic_ray/cli.py tests/e2e/test_baseline_outcomes.py tests/e2e/test_baseline_worker_results.py`: exit 0.
- `ruff format --check src/cosmic_ray/cli.py tests/e2e/test_baseline_outcomes.py tests/e2e/test_baseline_worker_results.py`: exit 0.
- `git diff --check`: exit 0; this does not inspect untracked tests.

## Open items

- A fresh independent review of the strengthened tests has not been performed.
- The full upstream suite and other supported Python/platform versions have not
  been verified.
- HTTP tests use the native handler in an in-process loopback-only server, not a
  separately launched worker process.
- Timeout checks confirm that the test child's loopback listener is no longer
  accepting connections, and the probe rejects a live listener. They do not
  independently inspect the child PID or prove process termination under every
  OS or unrelated loopback interference.
- The fixture uses bounded thread joins; a non-cooperative startup or cleanup
  coroutine could still leave a daemon thread after the assertion fails.
- Upstream contribution guidance requires the appropriate CLA before submission;
  that decision and action are pending with the owner.
- No commit, fork, push, or pull request has been made.

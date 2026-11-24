"""End-to-end import checks for the installed package surface."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python(code):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_package_root_imports_without_the_facade():
    result = _python(
        "import atlawire;"
        "assert hasattr(atlawire, 'AtlaWireError');"
        "assert not hasattr(atlawire, 'AtlaWire');"
        "print(atlawire.__version__)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_every_declared_export_resolves_in_a_fresh_interpreter():
    result = _python(
        "import atlawire;"
        "[getattr(atlawire, name) for name in atlawire.__all__];"
        "print(len(atlawire.__all__))"
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 0

import importlib
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from atlawire import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{SOURCE_ROOT}{os.pathsep}{existing}" if existing else str(SOURCE_ROOT)
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "atlawire", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_module_help_exits_cleanly() -> None:
    result = run_module("--help")

    assert result.returncode == 0, result.stderr
    assert "Usage: python -m atlawire" in result.stdout
    assert "--version" in result.stdout
    assert result.stderr == ""


def test_module_version_prints_version_to_stdout() -> None:
    result = run_module("--version")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"atlawire, version {__version__}"
    assert result.stderr == ""


def test_declared_console_script_target_is_callable() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    target = pyproject["project"]["scripts"]["atlawire"]
    module_name, _, attribute = target.partition(":")

    assert callable(getattr(importlib.import_module(module_name), attribute))


def test_console_script_version() -> None:
    script = shutil.which("atlawire")
    if script is None:
        pytest.skip("atlawire console script is not installed")

    result = subprocess.run(
        [script, "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"atlawire, version {__version__}"

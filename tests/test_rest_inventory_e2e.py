"""End-to-end checks for the inventory generator's command line."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "build_rest_inventory.py"
INVENTORY = ROOT / ".development" / "rest-inventory.json"


def _run(args):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-B", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
    )


def test_check_mode_reports_the_committed_inventory_current():
    result = _run([str(GENERATOR), "--check"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "inventory current" in result.stdout
    assert "two-way check passed" in result.stdout


def test_generator_writes_the_exact_committed_bytes(tmp_path):
    output = tmp_path / "rest-inventory.json"
    written = _run([str(GENERATOR), "--output", str(output)])

    assert written.returncode == 0, written.stderr
    assert output.read_text(encoding="utf-8") == INVENTORY.read_text(encoding="utf-8")

    checked = _run([str(GENERATOR), "--check", "--output", str(output)])
    assert checked.returncode == 0, checked.stdout


def test_check_fails_on_a_drifted_inventory(tmp_path):
    output = tmp_path / "rest-inventory.json"
    output.write_text('{"totals": {}}\n', encoding="utf-8")

    result = _run([str(GENERATOR), "--check", "--output", str(output)])

    assert result.returncode == 1
    assert "inventory outdated" in result.stdout


def test_check_fails_when_the_inventory_is_missing(tmp_path):
    missing = tmp_path / "absent.json"

    result = _run([str(GENERATOR), "--check", "--output", str(missing)])

    assert result.returncode == 1
    assert "inventory missing" in result.stdout

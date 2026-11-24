"""End-to-end checks for the manifest generator and the advertised registry."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "build_read_manifest.py"
MANIFEST = ROOT / "src" / "atlawire" / "manifest.json"


def _run(args, *, env=None):
    merged = dict(os.environ)
    merged["PYTHONPATH"] = str(ROOT / "src")
    merged.update(env or {})
    return subprocess.run(
        [sys.executable, "-B", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=merged,
        timeout=120,
    )


def test_generator_check_mode_reports_the_committed_manifest_current():
    result = _run([str(GENERATOR), "--check"])

    assert result.returncode == 0, result.stderr
    assert "manifest current" in result.stdout


def test_generator_writes_the_exact_committed_bytes(tmp_path):
    output = tmp_path / "manifest.json"
    written = _run([str(GENERATOR), "--output", str(output)])
    assert written.returncode == 0, written.stderr

    assert output.read_text(encoding="utf-8") == MANIFEST.read_text(encoding="utf-8")

    checked = _run([str(GENERATOR), "--check", "--output", str(output)])
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_generator_check_fails_on_a_drifted_manifest(tmp_path):
    output = tmp_path / "manifest.json"
    output.write_text('{"operations": []}\n', encoding="utf-8")

    result = _run([str(GENERATOR), "--check", "--output", str(output)])

    assert result.returncode == 1
    assert "manifest outdated" in result.stdout


def test_cli_operations_matches_the_packaged_manifest():
    result = _run(["-m", "atlawire", "operations"])
    assert result.returncode == 0, result.stderr

    operations = json.loads(result.stdout)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_routes = {
        (entry["product"], entry["method"], entry["path"])
        for entry in manifest["operations"]
    }
    registry_routes = {
        (entry["product"], entry["method"], entry["path"]) for entry in operations
    }

    assert len(operations) == 202
    assert manifest_routes - registry_routes == set()

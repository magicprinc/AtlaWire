"""A `--check` mode must verify without touching the tree.

Two generators regressed here: the API-surface fetcher wrote its artifacts and
then returned 0 for every `--check`, and the document splitter created
directories before deciding whether it was only verifying. A verification run
that mutates the reviewed artifact is not a verification.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fetch_module():
    return _load("fetch_api_surface")


def test_fetch_check_reports_drift_and_writes_nothing(tmp_path, monkeypatch):
    fetch = _fetch_module()
    target = tmp_path / "jira" / "source" / "application.wadl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"<application>old</application>")

    payloads = {target: b"<application>new</application>"}
    record = {
        "fetched_at": "2026-01-01T00:00:00Z",
        "schema": "atlawire-api-surface-source/v1",
        "products": {
            "jira": {
                "wadl_path": "/rest/api/2/application.wadl",
                "artifact": "jira/source/application.wadl",
                "bytes": len(payloads[target]),
                "sha256": fetch._digest(payloads[target]),
                "server_version": "8.22.2",
                "host_redacted": True,
            }
        },
    }
    monkeypatch.setattr(fetch, "collect", lambda: (record, payloads))
    monkeypatch.setattr(fetch, "OUTPUT", tmp_path)

    code = fetch.main(["--live", "--check"])

    assert code == 1
    assert target.read_bytes() == b"<application>old</application>"


def test_fetch_check_passes_when_the_artifact_matches(tmp_path, monkeypatch):
    fetch = _fetch_module()
    target = tmp_path / "jira" / "source" / "application.wadl"
    target.parent.mkdir(parents=True)
    payload = b"<application>same</application>"
    target.write_bytes(payload)

    record = {
        "fetched_at": "2026-01-01T00:00:00Z",
        "schema": "atlawire-api-surface-source/v1",
        "products": {
            "jira": {
                "wadl_path": "/rest/api/2/application.wadl",
                "artifact": "jira/source/application.wadl",
                "bytes": len(payload),
                "sha256": fetch._digest(payload),
                "server_version": "8.22.2",
                "host_redacted": True,
            }
        },
    }
    monkeypatch.setattr(fetch, "collect", lambda: (record, {target: payload}))
    monkeypatch.setattr(fetch, "OUTPUT", tmp_path)
    record_path = tmp_path / "api-surface-source.json"
    record_path.write_text(fetch.render_record(record), encoding="utf-8")

    assert fetch.main(["--live", "--check"]) == 0


def test_fetch_records_an_unreported_version_as_empty_not_by_requesting_the_wadl():
    fetch = _fetch_module()

    assert "confluence" not in fetch.VERSION_PATH


def test_document_splitter_does_not_create_directories_while_checking(
    tmp_path, monkeypatch
):
    builder = _load("build_api_surface_docs")
    monkeypatch.setattr(builder, "BASE", tmp_path)
    (tmp_path / "api-surface-source.json").write_text(
        json.dumps(
            {
                "fetched_at": "2026-01-01T00:00:00Z",
                "products": {
                    product: {
                        "server_version": "1.0",
                        "artifact": "x",
                        "sha256": "0" * 64,
                    }
                    for product in ("jira", "confluence", "bitbucket")
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(builder, "_groups", lambda product: {})

    builder.build(check_only=True)

    assert not (tmp_path / "jira" / "api").exists()

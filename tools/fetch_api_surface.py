"""Fetch each server's own WADL, which is the exact API surface it serves.

The vendor documentation site no longer serves the pinned versions (Confluence
6.6 now redirects to 22.x), and a downloaded page describes a release, not the
deployment. Every Atlassian product instead publishes a machine-readable WADL at
a fixed read-only path, generated from the running code: routes, methods, query
parameters with types and defaults, and prose for most methods.

This tool only reads. It never prints or stores a token, and it replaces the
internal host with ``example.com`` so the artifact can be reviewed or committed.

    python -B tools/fetch_api_surface.py --live
    python -B tools/fetch_api_surface.py --live --check
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".development"

WADL_PATH = {
    "jira": "/rest/api/2/application.wadl",
    "confluence": "/rest/api/application.wadl",
    "bitbucket": "/rest/api/1.0/application.wadl",
}
# A cheap read that states the running release, so the artifact is tied to a
# version instead of to "whatever was installed that day".
VERSION_PATH = {
    "jira": "/rest/api/2/serverInfo",
    "confluence": "/rest/api/application.wadl",
    "bitbucket": "/rest/api/1.0/application-properties",
}


def _credentials(product: str):
    from atlawire.credentials import load_saved_credentials

    return load_saved_credentials(product, allow_http_loopback=False)


def _get(url: str, token: str, accept: str) -> requests.Response:
    return requests.get(
        url,
        headers={"Accept": accept, "Authorization": f"Bearer {token}"},
        timeout=(5, 120),
        allow_redirects=False,
    )


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _host_needles(base_url: str) -> tuple[bytes, ...]:
    """Return every byte spelling of this deployment's host to replace.

    ``base_url`` may carry a port, and a WADL can mention the host in prose or
    with different case, so the set covers the host with and without the port,
    the whole authority, and both cases. Longest first, so a needle that includes
    the port is replaced before the bare host.
    """
    from urllib.parse import urlsplit

    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if not host:
        raise SystemExit("the configured base URL has no host")
    authority = parts.netloc.lower()
    spellings = {host, authority}
    if parts.port:
        spellings.add(f"{host}:{parts.port}")
    raw: set[str] = set()
    for spelling in spellings:
        raw.update({spelling, spelling.upper()})
    return tuple(item.encode() for item in sorted(raw, key=len, reverse=True) if item)


def fetch() -> dict[str, object]:
    """Download every WADL, redact the host, and return the provenance record."""
    record: dict[str, object] = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": "atlawire-api-surface-source/v1",
        "products": {},
    }
    products: dict[str, object] = {}
    for product, path in WADL_PATH.items():
        saved = _credentials(product)
        base = saved.base_url.rstrip("/")

        needles = _host_needles(saved.base_url)
        response = _get(base + path, saved.token, "application/xml")
        if response.status_code != 200:
            raise SystemExit(
                f"{product}: WADL request failed with HTTP {response.status_code}"
            )
        raw = response.content
        if b"<application" not in raw and b"application" not in raw[:200]:
            raise SystemExit(f"{product}: response is not a WADL document")

        # Redact before anything touches the disk: the artifact must be safe to
        # review and to commit. A WADL may spell the host with a port, in prose,
        # or in mixed case, so every form is replaced and the result is checked.
        redacted = raw
        for needle in needles:
            redacted = redacted.replace(needle, b"example.com")
        residual = [needle for needle in needles if needle in redacted]
        if residual:
            raise SystemExit(
                f"{product}: refusing to write a WADL that still names the host"
            )
        target = OUTPUT / product / "source" / "application.wadl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(redacted)

        version = ""
        try:
            probe = _get(base + VERSION_PATH[product], saved.token, "application/json")
            if probe.status_code == 200:
                version = str(probe.json().get("version", ""))[:40]
        except ValueError, KeyError, requests.RequestException:
            version = ""

        products[product] = {
            "wadl_path": path,
            "artifact": str(target.relative_to(ROOT)).replace("\\", "/"),
            "bytes": len(redacted),
            "sha256": _digest(redacted),
            "server_version": version,
            "host_redacted": True,
        }
        print(
            f"{product:10} {len(redacted):>9,} B  sha256 {_digest(redacted)[:16]}  version={version or '?'}"
        )
    record["products"] = products
    return record


def write_record(record: dict[str, object]) -> Path:
    target = OUTPUT / "api-surface-source.json"
    target.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="required: contact the servers"
    )
    parser.add_argument(
        "--check", action="store_true", help="compare with the stored record"
    )
    args = parser.parse_args(argv)
    if not args.live:
        print("Refusing: pass --live to contact the configured servers.")
        return 2

    record = fetch()
    target = write_record(record)
    print(f"record: {target.relative_to(ROOT)}")
    if args.check:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

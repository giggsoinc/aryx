#!/usr/bin/env python3
"""
trinity-upload.py — Upload a Trinity red-team report to the Raven Enterprise Hub.

Usage:
    python trinity-upload.py --payload-file .raven/.trinity-payload.json
    python trinity-upload.py --payload-file <path> --manifest <path>

Reads hub_url and org from the manifest, injects org into the payload,
and POSTs to <hub_url>/api/v1/trinity.

All output is JSON on stdout. Diagnostic logs suppressed.
Stdlib only — no third-party dependencies.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

MANIFEST_DEFAULT = ".raven/manifest.json"
TIMEOUT = 5  # seconds


def log(msg: str):
    pass


def emit(data: dict):
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="Upload a Trinity red-team report JSON to the Raven Enterprise Hub"
    )
    parser.add_argument(
        "--payload-file", required=True,
        help="Path to the report JSON file (fields from the skill, without 'org')",
    )
    parser.add_argument(
        "--manifest", default=MANIFEST_DEFAULT,
        help=f"Path to the Raven manifest (default: {MANIFEST_DEFAULT})",
    )
    args = parser.parse_args()

    # Read manifest
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        emit({"status": "error", "detail": f"Manifest not found: {args.manifest}"})
        sys.exit(1)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        emit({"status": "error", "detail": f"Failed to read manifest: {e}"})
        sys.exit(1)

    hub_url = manifest.get("hub_url", "").rstrip("/")
    org = manifest.get("org", "")

    if not hub_url:
        emit({"status": "skipped", "detail": "hub_url not set in manifest — skipping upload"})
        sys.exit(0)

    # Read payload
    payload_path = Path(args.payload_file)
    if not payload_path.exists():
        emit({"status": "error", "detail": f"Payload file not found: {args.payload_file}"})
        sys.exit(1)

    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception as e:
        emit({"status": "error", "detail": f"Failed to read payload: {e}"})
        sys.exit(1)

    # Inject org from manifest
    payload["org"] = org

    # POST to hub
    endpoint = f"{hub_url}/api/v1/trinity"
    log(f"Uploading to {endpoint}")

    try:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        agent_key = os.environ.get("RAVEN_AGENT_KEY", "")
        if agent_key:
            headers["X-Raven-Agent"] = agent_key
        req = urllib.request.Request(
            endpoint, data=data,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="ignore")

        try:
            result = json.loads(body)
        except Exception:
            result = {"raw": body}

        emit({"status": "ok", **result})

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        emit({"status": "error", "http_status": e.code, "detail": body[:300]})
        sys.exit(1)

    except Exception as e:
        emit({"status": "error", "detail": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()

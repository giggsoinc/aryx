"""Multipart upload client for document self-discovery (kept out of api.py)."""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from aryx.ui.api import _BASE, _WS


def _multipart(path: str, fields: dict[str, str], files: list) -> dict[str, Any]:
    """POST a multipart form (text fields + files), auto-tagging the workspace."""
    b = "----AryxBoundary"
    fields = {**fields, "workspace_id": str(_WS["id"])}
    parts: list[bytes] = [
        f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for k, v in fields.items()
    ]
    for f in files:
        fname = getattr(f, "name", "upload")
        data = f.getvalue() if hasattr(f, "getvalue") else f.read()
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"files\"; "
                     f"filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
        parts.append(data + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    req = urllib.request.Request(f"{_BASE}{path}", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        return json.loads(r.read())


def docs_read(files: list, context: str) -> dict[str, Any]:
    """Upload files for self-discovery with an optional context."""
    return _multipart("/admin/docs/read", {"context": context}, files)

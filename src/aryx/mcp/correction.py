"""MCP correction dispatch — Slice 6.

Thin shim over /admin/workspaces/{id}/corrections (apply) and its /chat
sibling (propose). See tools_correction.py for why these stay two calls.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "60"))


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def dispatch(name: str, a: dict) -> Any:
    """Route a correction_* MCP call to its backing REST endpoint."""
    wid = int(a["workspace_id"])
    if name == "correction_propose":
        return _post(f"/admin/workspaces/{wid}/corrections/chat", {
            "text": a["text"],
            "selected_entity_id": int(a.get("selected_entity_id") or 0),
        })
    if name == "correction_apply":
        return _post(f"/admin/workspaces/{wid}/corrections", {
            "kind": a["kind"],
            "entity_id": int(a.get("entity_id") or 0),
            "target_id": int(a.get("target_id") or 0),
            "name": a.get("name", ""),
            "type_name": a.get("type_name", ""),
        })
    return {"error": f"unknown correction tool: {name}"}

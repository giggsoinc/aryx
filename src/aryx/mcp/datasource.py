"""MCP datasource dispatch — Slice 2: quiz / add / list / test / delete.

Mirrors mcp/onboard.py — thin REST shim over /admin/datasources. Secrets
travel as request params on datasource_add only; responses never contain
plaintext, only secret_mask. The agent reads ``quiz`` to know what to ask
the user, posts add(...) once collected, then test(...) to confirm.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "60"))


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{_API_URL}{path}", timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _delete(path: str) -> Any:
    req = urllib.request.Request(f"{_API_URL}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.loads(r.read().decode())


def dispatch(name: str, a: dict) -> Any:
    """Route a datasource_* MCP call to the REST API."""
    if name == "datasource_quiz":
        kind = a.get("kind", "")
        if not kind:
            return _get("/admin/datasources/kinds")
        return _get(f"/admin/datasources/quiz?kind={kind}")
    if name == "datasource_add":
        return _post("/admin/datasources", {
            "name": a["name"], "kind": a["kind"],
            "config": a.get("config") or {},
            "secret": a.get("secret", ""),
            "workspace_id": int(a["workspace_id"])})
    if name == "datasource_list":
        wid = int(a["workspace_id"])
        return _get(f"/admin/datasources?workspace_id={wid}")
    if name == "datasource_test":
        return _post(f"/admin/datasources/{int(a['datasource_id'])}/test", {})
    if name == "datasource_delete":
        return _delete(f"/admin/datasources/{int(a['datasource_id'])}")
    return {"error": f"unknown datasource tool: {name}"}

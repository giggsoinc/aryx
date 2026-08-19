"""MCP chart (ask-to-visualize) dispatch — Slice 7.

Thin shim over /andie-planner/delta/draft and /delta/confirm. Both take
workspace_id as a query param on the backend, not a body field.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from aryx.mcp.api_headers import json_headers

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "120"))


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers=json_headers())
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode())


def dispatch(name: str, a: dict) -> Any:
    """Route a chart_* MCP call to its backing REST endpoint."""
    wid = int(a["workspace_id"])
    if name == "chart_draft":
        return _post(f"/andie-planner/delta/draft?workspace_id={wid}", {
            "dataset_id": a["dataset_id"],
            "request_text": a["request_text"],
            "tier": a.get("tier", "frontier"),
        })
    if name == "chart_confirm":
        return _post(f"/andie-planner/delta/confirm?workspace_id={wid}", {
            "dataset_id": a["dataset_id"],
            "new_kpi": a.get("new_kpi"),
            "new_analysis": a.get("new_analysis"),
            "new_visualization": a.get("new_visualization"),
        })
    return {"error": f"unknown chart tool: {name}"}

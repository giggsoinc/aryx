"""MCP dashboard-link dispatch — Slice 5.

Pure URL construction, no REST call: nothing in the API returns a
dashboard link today (the page is a workspace-keyed Next.js route), so
this mirrors that route directly instead of inventing a backend endpoint
for a one-line string.
"""
from __future__ import annotations

import os
from typing import Any

_WEB_URL = os.environ.get("ARYX_WEB_URL", "http://localhost:3000").rstrip("/")


def dispatch(name: str, a: dict) -> Any:
    """Route a dashboard_* MCP call."""
    if name == "dashboard_link":
        wid = int(a["workspace_id"])
        return {"workspace_id": wid,
                "url": f"{_WEB_URL}/dashboard?workspace_id={wid}"}
    return {"error": f"unknown dashboard tool: {name}"}

"""MCP HITL ingest dispatch — Slice 3.

Four tools: ingest_questions / ingest_answer / ingest_status / entities_preview.
Thin shim over /admin/ingest-questions + /graph + /admin/jobs.
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


def dispatch(name: str, a: dict) -> Any:
    """Route an ingest_* MCP call to its backing REST endpoint."""
    if name == "ingest_questions":
        wid = int(a["workspace_id"])
        status = a.get("status", "pending")
        limit = int(a.get("limit", 25))
        return _get(f"/admin/ingest-questions?workspace_id={wid}"
                    f"&status={status}&limit={limit}")
    if name == "ingest_answer":
        return _post(f"/admin/ingest-questions/{int(a['question_id'])}/answer",
                     {"answer": a["answer"],
                      "answered_by": a.get("answered_by", "mcp-agent")})
    if name == "ingest_status":
        wid = int(a["workspace_id"])
        job_id = a.get("job_id", "")
        stats = _get(f"/admin/ingest-questions/stats?workspace_id={wid}"
                     f"&job_id={job_id}")
        out = {"workspace_id": wid, "question_counts": stats}
        if job_id:
            try:
                out["job"] = _get(f"/admin/jobs/{job_id}?workspace_id={wid}")
            except Exception as exc:  # noqa: BLE001
                out["job_error"] = str(exc)
        return out
    if name == "entities_preview":
        wid = int(a["workspace_id"])
        limit = int(a.get("limit", 20))
        graph = _get(f"/graph?workspace_id={wid}") or {}
        return {
            "entities": (graph.get("entities") or [])[:limit],
            "relationships": (graph.get("relationships") or [])[:limit * 3],
            "entity_total": len(graph.get("entities") or []),
            "relationship_total": len(graph.get("relationships") or []),
        }
    return {"error": f"unknown ingest tool: {name}"}

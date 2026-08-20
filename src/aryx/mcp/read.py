"""MCP `list` and `ask` dispatch — the original read tools.

Split out of server.py to keep it under the 150-line style cap. `list`
enriches each workspace with graph stats; `ask` is a thin shim over /ask.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from aryx.mcp.api_headers import api_headers, json_headers

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "50"))
_DEFAULT_WS = int(os.environ.get("ARYX_MCP_DEFAULT_WORKSPACE", "1"))


def _ws(args: dict[str, Any]) -> int:
    """Resolve workspace_id from args or env default."""
    return int(args.get("workspace_id") or _DEFAULT_WS)


def _get(path: str) -> Any:
    with urllib.request.urlopen(
            urllib.request.Request(f"{_API_URL}{path}", headers=api_headers()),
            timeout=20) as resp:
        return json.loads(resp.read().decode())


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers=json_headers())
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _norm(items: list, key: str) -> list[dict]:
    out: list[dict] = []
    for t in items or []:
        if isinstance(t, dict):
            out.append({"name": t.get("name") or t.get("type") or "",
                        "count": int(t.get(key) or t.get("count") or 0)})
        else:
            out.append({"name": str(t), "count": 0})
    return [t for t in out if t["name"]]


def _axiom_summary(workspace_id: int) -> tuple[int, dict]:
    try:
        doc = _get(f"/ontology/axioms?workspace_id={workspace_id}") or {}
    except Exception:  # noqa: BLE001 — axioms advisory in MCP card
        return 0, {}
    axioms = doc.get("axioms") or []
    kinds: dict[str, int] = {}
    for ax in axioms:
        if k := str(ax.get("kind") or ""):
            kinds[k] = kinds.get(k, 0) + 1
    return len(axioms), kinds


def _enrich_workspace(ws: dict) -> dict:
    """Add entity/relationship counts + type breakdown for one workspace."""
    wid = int(ws.get("id", 1))
    try:
        types_doc = _get(f"/ontology/types?workspace_id={wid}") or {}
    except Exception as exc:  # noqa: BLE001
        return {
            "id": wid, "name": ws.get("name", ""),
            "description": ws.get("description", ""),
            "brief": ws.get("brief", {}),
            "entity_count": 0, "relationship_count": 0,
            "entity_types": [], "relationship_types": [],
            "axiom_count": 0, "axiom_kinds": {},
            "stats_error": str(exc),
        }
    axiom_count, axiom_kinds = _axiom_summary(wid)
    ents = _norm(types_doc.get("types") or types_doc.get("entity_types"),
                 "instance_count")
    rels = _norm(types_doc.get("relationships")
                 or types_doc.get("relationship_types"), "count")
    return {
        "id": wid,
        "name": ws.get("name", ""),
        "description": ws.get("description", ""),
        "brief": ws.get("brief", {}),
        "entity_count": int(types_doc.get("entity_count")
                            or sum(t["count"] for t in ents)),
        "relationship_count": sum(t["count"] for t in rels),
        "entity_types": ents,
        "relationship_types": rels,
        "axiom_count": axiom_count,
        "axiom_kinds": axiom_kinds,
    }


def list_workspaces() -> list[dict]:
    """The `list` tool: every workspace, enriched with graph stats."""
    workspaces = _get("/admin/workspaces?workspace_id=1") or []
    return [_enrich_workspace(ws) for ws in workspaces]


def ask(a: dict) -> Any:
    """The `ask` tool: a thin shim over POST /ask."""
    return _post("/ask", {
        "question": a["question"],
        "history": a.get("history") or [],
        "workspace_id": _ws(a),
    })

"""MCP onboarding dispatch — Slice 1: workspace + brief tools.

Wraps existing REST endpoints (/admin/workspaces, /admin/workspaces/{id}/...
including the draft-brief endpoint shipped earlier) so any MCP-host agent
can run the full onboarding quiz: pick a workspace, then drive the user
through the brief one question at a time.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "180"))

_BRIEF_PROMPTS = {
    "domain": ("Domain of interest — one short phrase describing the "
               "subject area (e.g. 'Customer support for radio equipment')."),
    "aim": ("Aim — one or two sentences on the outcome this graph should "
            "enable (e.g. 'Match tickets to the right expert agent')."),
    "objectives": ("Objectives — 3–6 concrete goals, one per line."),
    "scope": ("Scope — what's IN and what's OUT (two short blocks)."),
    "roles": ("Participant roles — 2–5 stakeholder roles, one per line."),
}


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{_API_URL}{path}", timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _post(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _patch(path: str, body: dict) -> Any:
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _depth(brief: dict) -> str:
    """Readiness label from the number of populated fields."""
    keys = ("domain", "aim", "objectives", "scope", "roles")
    n = sum(1 for k in keys if (brief.get(k) or ""))
    return ("Generic NER", "Grounded", "Grounded", "Sharp",
            "Expert", "Expert")[min(n, 5)]


def _next_question(brief: dict) -> str | None:
    """Return the prompt for the first empty field, or None when complete."""
    for key in ("domain", "aim", "objectives", "scope", "roles"):
        if not (brief.get(key) or ""):
            return f"{key}: {_BRIEF_PROMPTS[key]}"
    return None


def _brief_of(workspace_id: int) -> dict:
    """Fetch the saved brief for a workspace."""
    for ws in _get("/admin/workspaces?workspace_id=1") or []:
        if int(ws.get("id", 0)) == int(workspace_id):
            return ws.get("brief") or {}
    return {}


def dispatch(name: str, a: dict) -> Any:
    """Route an onboarding tool call (workspace_*, brief_*)."""
    if name == "workspace_list":
        return _get("/admin/workspaces?workspace_id=1") or []
    if name == "workspace_create":
        return _post("/admin/workspaces", {
            "name": a["name"],
            "description": a.get("description", ""),
            "context": a.get("context", ""),
        })
    if name == "workspace_select":
        ws = [w for w in (_get("/admin/workspaces?workspace_id=1") or [])
              if int(w.get("id", 0)) == int(a["workspace_id"])]
        if not ws:
            return {"error": f"workspace {a['workspace_id']} not found"}
        return {"selected": ws[0]}
    if name == "brief_get":
        b = _brief_of(int(a["workspace_id"]))
        return {"brief": b, "next_question": _next_question(b),
                "depth": _depth(b)}
    if name == "brief_draft":
        wid = int(a["workspace_id"])
        return _post(f"/admin/workspaces/{wid}/draft-brief", {
            "seed": a.get("seed", ""), "doc_text": a.get("doc_text", ""),
            "workspace_id": wid})
    if name == "brief_set":
        wid = int(a["workspace_id"])
        brief = dict(_brief_of(wid))
        field, value = a["field"], a["value"]
        if field in ("objectives", "roles") and isinstance(value, str):
            value = [ln.strip() for ln in value.splitlines() if ln.strip()]
        brief[field] = value
        _patch(f"/admin/workspaces/{wid}/brief", brief)
        return {"brief": brief, "next_question": _next_question(brief),
                "depth": _depth(brief)}
    if name == "brief_save":
        wid = int(a["workspace_id"])
        brief = a.get("brief") or _brief_of(wid)
        _patch(f"/admin/workspaces/{wid}/brief", brief)
        return {"saved": True, "depth": _depth(brief),
                "next_question": _next_question(brief)}
    return {"error": f"unknown onboarding tool: {name}"}

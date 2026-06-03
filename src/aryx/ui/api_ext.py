"""UI client extensions — rules, versions, ask history, MCP tokens, REST source.

Split out of api.py to keep that module under the 150-line budget.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from aryx.ui import api


def list_rules() -> list[dict[str, Any]]:
    """All inference rules in the active workspace."""
    return api._get("/rules")


def upsert_rule(name: str, when: dict, then: dict,
                enabled: bool = True) -> dict[str, Any]:
    """Create or replace a rule."""
    return api._post("/rules", {
        "name": name, "when": when, "then": then, "enabled": enabled,
    })


def delete_rule(name: str) -> dict[str, Any]:
    """Delete a rule by name."""
    req = urllib.request.Request(
        f"{api._BASE}/rules/{name}?workspace_id={api.current_workspace()}",
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def evaluate_rules() -> dict[str, Any]:
    """Run all enabled rules against the workspace; return fire counts."""
    return api._post("/rules/evaluate", {}, timeout=120)


def list_versions(limit: int = 25) -> list[dict[str, Any]]:
    """Recent ontology version snapshots."""
    return api._get(f"/ontology-versions?limit={limit}")


def snapshot_version(label: str) -> dict[str, Any]:
    """Create a new ontology version snapshot."""
    return api._post("/ontology-versions", {"label": label})


def change_log(limit: int = 50) -> list[dict[str, Any]]:
    """Recent ontology change-log rows."""
    return api._get(f"/ontology-versions/changes?limit={limit}")


def ask_history(limit: int = 50) -> list[dict[str, Any]]:
    """Persisted Ask history for the current workspace."""
    return api._get(f"/ask/history?limit={limit}")


def list_mcp_tokens() -> list[dict[str, Any]]:
    """All MCP tokens (no raw secret, only prefix)."""
    base = api._BASE
    with urllib.request.urlopen(  # noqa: S310
        f"{base}/admin/mcp/tokens", timeout=15
    ) as r:
        return json.loads(r.read())


def issue_mcp_token(label: str) -> dict[str, Any]:
    """Issue a new bearer token; raw token visible ONCE in the response."""
    data = json.dumps({"label": label}).encode()
    req = urllib.request.Request(
        f"{api._BASE}/admin/mcp/tokens", data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())


def revoke_mcp_token(token_id: int) -> dict[str, Any]:
    """Revoke a token by id."""
    req = urllib.request.Request(
        f"{api._BASE}/admin/mcp/tokens/{int(token_id)}", method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
        return json.loads(r.read())

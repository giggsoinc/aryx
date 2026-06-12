"""MCP `act` dispatch (G13): agent-initiated, always-pending executions."""
from __future__ import annotations

import os
from typing import Any


def _ws(a: dict[str, Any]) -> int:
    """Workspace id from args or the server default."""
    return int(a.get("workspace_id")
               or os.environ.get("ARYX_MCP_DEFAULT_WORKSPACE", "1"))


def _act(a: dict) -> Any:
    """Create an ALWAYS-pending action execution (agent-initiated = HITL).

    MCP-initiated mutations never auto-apply regardless of the action's
    approval flag — every agent request faces a human in v1 (DECISIONS.md).
    """
    from aryx.actions.engine import validate_params
    from aryx.config import get_settings
    from aryx.store.action_store import ActionStore
    store = ActionStore(get_settings().rdb_dsn, _ws(a))
    action = store.by_name(a["action"])
    if action is None:
        return {"error": f"action '{a['action']}' not found"}
    if not action["enabled"]:
        return {"error": f"action '{a['action']}' is disabled"}
    problems = validate_params(action["definition"], a.get("params") or {})
    if problems:
        return {"error": str(problems)}
    execution_id = store.request_execution(
        action["id"], int(a["entity_id"]), a.get("params") or {},
        "pending", "mcp-agent")
    return {"execution_id": execution_id, "status": "pending",
            "note": "agent-initiated actions always await human approval"}

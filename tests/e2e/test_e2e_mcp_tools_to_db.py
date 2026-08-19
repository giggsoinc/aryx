"""Chain 4: MCP tools reach real Postgres/FalkorDB correctly — three tools
not otherwise exercised by chains 5/6 (ingest, correction) or chain 3
(ask-to-visualize): `list` (real graph-stat enrichment), `dashboard_link`
(pure, no DB), and `act` (the pending-approval mutation gate — the one
place an MCP tool can request a mutation, and it must never auto-apply).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_list_enriches_workspaces_from_real_stores(workspace) -> None:
    """The `list` tool's enrichment reads real Postgres/FalkorDB, not a mock."""
    from aryx.mcp.read import list_workspaces
    workspaces = list_workspaces()
    found = next(w for w in workspaces if w["id"] == workspace["id"])
    # A brand-new workspace: real reads, real (empty) counts — not mocked zeros.
    assert found["entity_count"] == 0
    assert found["relationship_count"] == 0
    assert "stats_error" not in found


def test_dashboard_link_needs_no_db_at_all(workspace) -> None:
    """Sanity check: dashboard_link is pure URL construction, no store call."""
    from aryx.mcp.dashboard import dispatch
    result = dispatch("dashboard_link", {"workspace_id": workspace["id"]})
    assert result["url"].endswith(f"/dashboard?workspace_id={workspace['id']}")


def test_act_always_creates_a_pending_execution_never_auto_applies(e2e_dsn, workspace) -> None:
    """The trust-posture guarantee from aryx.mcp.act's own docstring:
    agent-initiated mutations always face human approval, regardless of
    the action's own approval flag."""
    from aryx.store.action_store import ActionStore
    wid = workspace["id"]
    store = ActionStore(e2e_dsn, wid)
    action_id = store.create(
        {"name": "e2e_noop", "params": {}, "enabled": True, "effects": []},
        created_by="e2e-test")

    from aryx.mcp.act import _act
    result = _act({"action": "e2e_noop", "entity_id": 1, "workspace_id": wid})
    assert result["status"] == "pending"
    assert "execution_id" in result

    execution = store.execution(result["execution_id"])
    assert execution is not None
    assert execution["status"] == "pending", (
        "an agent-initiated action must never auto-apply, even for a "
        "no-op action with no side effects")

"""Rules + inference API — CRUD over rules + run the evaluator on demand."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.reasoning import evaluate_workspace
from aryx.store.rule_store import RuleStore
from aryx.store.version_store import VersionStore

logger = logging.getLogger(__name__)


class RuleRequest(BaseModel):
    """One inference rule: when-clause + then-clause + enabled flag."""

    workspace_id: int = 1
    name: str
    when: dict
    then: dict
    enabled: bool = True


def rules_router() -> APIRouter:
    """Build the /rules router for the FastAPI app."""
    router = APIRouter(prefix="/rules")

    @router.get("")
    def list_rules(workspace_id: int = 1) -> list[dict[str, Any]]:
        """Return all rules in the workspace, oldest first."""
        store = RuleStore(get_settings().rdb_dsn)
        try:
            return store.list_(workspace_id)
        finally:
            store.close()

    @router.post("")
    def upsert_rule(req: RuleRequest) -> dict[str, Any]:
        """Create or replace a rule by (workspace, name); log the change."""
        store = RuleStore(get_settings().rdb_dsn)
        vs = VersionStore(get_settings().rdb_dsn)
        try:
            existing = next((r for r in store.list_(req.workspace_id)
                             if r["name"] == req.name), None)
            row = store.upsert(req.workspace_id, req.name, req.when,
                               req.then, req.enabled)
            vs.log_change(req.workspace_id, "user", "upsert_rule", "rule",
                          req.name, existing, {"when": req.when,
                                                "then": req.then,
                                                "enabled": req.enabled})
            return row
        finally:
            store.close()
            vs.close()

    @router.patch("/{name}/enabled")
    def toggle(workspace_id: int, name: str, enabled: bool) -> dict[str, Any]:
        """Flip a rule's enabled flag (query-param body)."""
        store = RuleStore(get_settings().rdb_dsn)
        try:
            return store.set_enabled(workspace_id, name, enabled)
        finally:
            store.close()

    @router.delete("/{name}")
    def delete(workspace_id: int, name: str) -> dict[str, Any]:
        """Delete a rule by name."""
        store = RuleStore(get_settings().rdb_dsn)
        vs = VersionStore(get_settings().rdb_dsn)
        try:
            rid = store.delete(workspace_id, name)
            if not rid:
                raise HTTPException(404, f"rule not found: {name}")
            vs.log_change(workspace_id, "user", "delete_rule", "rule",
                          name, None, None)
            return {"status": "deleted", "id": rid}
        finally:
            store.close()
            vs.close()

    @router.post("/evaluate")
    def evaluate(workspace_id: int = 1) -> dict[str, Any]:
        """Run every enabled rule over the workspace; return fire counts."""
        try:
            return evaluate_workspace(workspace_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"evaluation failed: {exc}") from exc

    return router

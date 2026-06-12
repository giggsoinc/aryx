"""Actions API (G13): definition CRUD, execute, decide pending, stats.

Mirrors G10's adjudication decide-endpoint shape verbatim — a steward
learns one approval workflow. Execution flow: guard check -> param
validation -> pending (approval=required) or immediate apply (auto).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.actions.engine import (apply_effects, check_guard,
                                 validate_definition, validate_params)
from aryx.config import get_settings
from aryx.store.action_store import ActionStore

logger = logging.getLogger(__name__)


class ExecuteRequest(BaseModel):
    """One action execution request."""

    entity_id: int
    params: dict[str, Any] = {}
    requested_by: str = "api"


class DecideRequest(BaseModel):
    """Human verdict on one pending execution (same shape as G10)."""

    approve: bool
    decided_by: str


def _store(workspace_id: int) -> ActionStore:
    """Build a workspace-scoped action store."""
    return ActionStore(get_settings().rdb_dsn, workspace_id)


def _apply(store: ActionStore, execution_id: int, entity_id: int,
           definition: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Apply effects Postgres-first and persist the audit log."""
    try:
        log = apply_effects(store, entity_id, definition["effects"], params)
        store.record_applied(execution_id, "applied", log)
        return {"execution_id": execution_id, "status": "applied",
                "effect_log": log}
    except Exception as exc:  # noqa: BLE001 — failure must be audited
        store.record_applied(execution_id, "failed", [{"error": str(exc)}])
        raise HTTPException(500, f"effects failed: {exc}") from exc


def actions_router() -> APIRouter:
    """Routes for action definitions + executions."""
    router = APIRouter(prefix="/actions")

    @router.get("")
    def list_actions(workspace_id: int = 1) -> list[dict[str, Any]]:
        """Current (non-superseded) action definitions."""
        return _store(workspace_id).list_()

    @router.post("")
    def create_action(definition: dict[str, Any], workspace_id: int = 1,
                      created_by: str = "api") -> dict[str, Any]:
        """Register a new definition version (append; prior superseded)."""
        problems = validate_definition(definition)
        if problems:
            raise HTTPException(422, f"invalid definition: {problems}")
        action_id = _store(workspace_id).create(definition, created_by)
        return {"id": action_id, "name": definition["name"]}

    @router.post("/{name}/execute")
    def execute(name: str, req: ExecuteRequest,
                workspace_id: int = 1) -> dict[str, Any]:
        """Run guard + params; queue (required) or apply (auto)."""
        store = _store(workspace_id)
        action = store.by_name(name)
        if action is None:
            raise HTTPException(404, f"action '{name}' not found")
        if not action["enabled"]:
            raise HTTPException(409, f"action '{name}' is disabled")
        definition = action["definition"]
        problems = validate_params(definition, req.params)
        if problems:
            raise HTTPException(422, str(problems))
        guard = definition.get("guard")
        if guard:
            row = store._one("select_entity_attributes",
                             (req.entity_id, workspace_id))
            if row is None:
                raise HTTPException(404, "entity not found")
            entity = {"attributes": row[0], "type": row[1]}
            if not check_guard(entity, guard):
                raise HTTPException(409, "guard condition not met")
        if definition.get("approval", "required") == "auto":
            execution_id = store.request_execution(
                action["id"], req.entity_id, req.params, "approved",
                req.requested_by)
            return _apply(store, execution_id, req.entity_id,
                          definition, req.params)
        execution_id = store.request_execution(
            action["id"], req.entity_id, req.params, "pending",
            req.requested_by)
        return {"execution_id": execution_id, "status": "pending"}

    @router.get("/executions")
    def executions(workspace_id: int = 1, status: str = "pending",
                   limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """One page of executions (default: pending approvals)."""
        return _store(workspace_id).executions(status, min(limit, 200), offset)

    @router.post("/executions/{execution_id}/decide")
    def decide(execution_id: int, req: DecideRequest,
               workspace_id: int = 1) -> dict[str, Any]:
        """Approve (apply effects) or reject one pending execution."""
        store = _store(workspace_id)
        try:
            row = store.decide(execution_id, req.approve, req.decided_by)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not req.approve:
            return {"execution_id": execution_id, "status": "rejected"}
        execution = store.execution(execution_id)
        return _apply(store, execution_id, row["entity_id"],
                      execution["definition"], row["params"] or {})

    return router

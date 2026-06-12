"""Persistence for action definitions + executions (G13).
Definitions version by append (superseded_by pointer) — history reconstructable.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

def _dumps(value: object) -> str:
    """JSON-encode, stringifying non-native types."""
    return json.dumps(value, default=str)

class ActionStore:
    """CRUD over actions + executions + the Postgres-first effect targets."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def _one(self, query: str, args: tuple) -> tuple | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load(query), args)
                return cur.fetchone()

    def create(self, definition: dict[str, Any], created_by: str) -> int:
        """Append a definition version; supersede prior rows of that name."""
        name = definition["name"]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_action"),
                            (self._ws, name, Json(definition, dumps=_dumps),
                             definition.get("enabled", True), created_by))
                action_id = int(cur.fetchone()[0])
                cur.execute(load("supersede_action"),
                            (action_id, self._ws, name, action_id))
        return action_id

    def list_(self) -> list[dict[str, Any]]:
        """Current (non-superseded) definitions."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_actions"), (self._ws,))
                rows = cur.fetchall()
        keys = ("id", "name", "definition", "enabled",
                "created_by", "created_at")
        return [dict(zip(keys, r)) for r in rows]

    def by_name(self, name: str) -> dict[str, Any] | None:
        """Latest definition for a name, or None."""
        row = self._one("select_action_by_name", (self._ws, name))
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "definition": row[2],
                "enabled": row[3]}

    def request_execution(self, action_id: int, entity_id: int,
                          params: dict[str, Any], status: str, requested_by: str) -> int:
        """Insert one execution row (pending or approved)."""
        row = self._one("insert_action_execution",
                        (self._ws, action_id, entity_id,
                         Json(params, dumps=_dumps), status, requested_by))
        return int(row[0]) if row else 0

    def executions(self, status: str = "pending", limit: int = 50,
                   offset: int = 0) -> list[dict]:
        """One page of executions with the given status."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_action_executions"),
                            (self._ws, status, limit, offset))
                rows = cur.fetchall()
        keys = ("id", "action", "entity_id", "params", "status",
                "requested_by", "decided_by", "decided_at", "applied_at",
                "effect_log", "created_at")
        return [dict(zip(keys, r)) for r in rows]

    def execution(self, execution_id: int) -> dict[str, Any] | None:
        """One execution row joined with its action definition."""
        row = self._one("select_action_execution_by_id", (execution_id,))
        if row is None:
            return None
        keys = ("id", "workspace_id", "action_id", "entity_id",
                "params", "status", "definition", "enabled")
        return dict(zip(keys, row))

    def decide(self, execution_id: int, approve: bool, decided_by: str) -> dict[str, Any]:
        """Flip a pending execution; ValueError when not pending."""
        status = "approved" if approve else "rejected"
        row = self._one("decide_action_execution",
                        (status, decided_by, execution_id))
        if row is None:
            raise ValueError(f"execution {execution_id} not pending")
        return {"id": row[0], "action_id": row[1], "entity_id": row[2],
                "params": row[3], "status": row[4]}

    def record_applied(self, execution_id: int, status: str,
                       effect_log: list[dict]) -> None:
        """Persist the effect log after application (or failure)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("apply_action_execution"),
                            (status, Json(effect_log, dumps=_dumps),
                             execution_id))

    def get_attribute(self, entity_id: int, key: str) -> Any:
        """Current value of one entity attribute (for before/after log)."""
        row = self._one("select_entity_attributes", (entity_id, self._ws))
        return (row[0] or {}).get(key) if row else None

    def set_attribute(self, entity_id: int, key: str, value: Any) -> None:
        """Merge one attribute into the entity JSONB; touches updated_at."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("update_entity_attributes"),
                            (Json({key: value}, dumps=_dumps),
                             entity_id, self._ws))

    def find_entity(self, ontology_type: str, name: str) -> int | None:
        """Entity id by type + display name (add_relationship target)."""
        row = self._one("select_entity_by_type_name",
                        (self._ws, ontology_type, name))
        return int(row[0]) if row else None

    def add_relationship(self, source_id: int, target_id: int, name: str) -> None:
        """Insert a relationship row (Postgres first; graph reprojects)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_relationship"),
                            (self._ws, source_id, target_id, name, 1.0))

    def remove_relationship(self, source_id: int, name: str) -> int:
        """Remove named relationships from an entity; returns rows removed."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("remove_relationship_named"),
                            (self._ws, source_id, name))
                return cur.rowcount

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

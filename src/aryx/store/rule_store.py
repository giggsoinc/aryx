"""Inference rule store — JSON when/then DSL, evaluator reads from here."""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.types.json import Json

from aryx.queries import load

logger = logging.getLogger(__name__)


class RuleStore:
    """CRUD for aryx_ontology_rule scoped by workspace."""

    def __init__(self, dsn: str) -> None:
        """Open a connection."""
        self._conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def upsert(self, workspace_id: int, name: str, when: dict,
               then: dict, enabled: bool = True) -> dict[str, Any]:
        """Insert or replace a rule by (workspace, name)."""
        with self._conn.cursor() as cur:
            cur.execute(load("upsert_rule"), (
                int(workspace_id), name, Json(when), Json(then),
                bool(enabled),
            ))
            row = cur.fetchone()
        logger.info("rule upserted ws=%s name=%s", workspace_id, name)
        return {"id": row[0], "name": row[1], "enabled": row[2],
                "fires_count": row[3], "created_at": row[4]}

    def list_(self, workspace_id: int) -> list[dict[str, Any]]:
        """Return all rules in a workspace."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_rules"), (int(workspace_id),))
            rows = cur.fetchall()
        return [{"id": r[0], "workspace_id": r[1], "name": r[2],
                 "when": r[3], "then": r[4], "enabled": r[5],
                 "fires_count": r[6], "last_run_at": r[7],
                 "created_at": r[8]} for r in rows]

    def set_enabled(self, workspace_id: int, name: str,
                    enabled: bool) -> dict[str, Any]:
        """Toggle one rule's enabled flag."""
        with self._conn.cursor() as cur:
            cur.execute(load("set_rule_enabled"),
                        (bool(enabled), int(workspace_id), name))
            row = cur.fetchone()
        return {"id": row[0], "name": row[1], "enabled": row[2]}

    def delete(self, workspace_id: int, name: str) -> int:
        """Delete a rule. Returns id or 0 if not found."""
        with self._conn.cursor() as cur:
            cur.execute(load("delete_rule"), (int(workspace_id), name))
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def bump(self, workspace_id: int, name: str, fires: int) -> None:
        """Increment fires_count + set last_run_at after an evaluator pass."""
        with self._conn.cursor() as cur:
            cur.execute(load("bump_rule_fires"),
                        (int(fires), int(workspace_id), name))

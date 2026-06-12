"""Ontology version snapshot store — full JSON dump on each version cut."""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class VersionStore:
    """CRUD for aryx_ontology_version + aryx_ontology_change_log."""

    def __init__(self, dsn: str) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)

    def snapshot(self, workspace_id: int, label: str, types: list[dict],
                 rules: list[dict], actor: str = "") -> dict[str, Any]:
        """Create a new version snapshot of the ontology + rules."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_ontology_version"), (
                    int(workspace_id), int(workspace_id), label,
                    Json(types), Json(rules), actor,
                ))
                row = cur.fetchone()
        logger.info("ontology version snapshot ws=%s v=%d",
                    workspace_id, row[1])
        return {"id": row[0], "version_no": row[1], "created_at": row[2]}

    def list_(self, workspace_id: int, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent version snapshots, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_ontology_versions"),
                            (int(workspace_id), int(limit)))
                rows = cur.fetchall()
        return [{"id": r[0], "workspace_id": r[1], "version_no": r[2],
                 "label": r[3], "types_json": r[4], "rules_json": r[5],
                 "created_by": r[6], "created_at": r[7]} for r in rows]

    def log_change(self, workspace_id: int, actor: str, op: str,
                   target_kind: str, target_name: str,
                   before: dict | list | None,
                   after: dict | list | None) -> dict[str, Any]:
        """Append one row to the ontology change log."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_change_log"), (
                    int(workspace_id), actor, op, target_kind, target_name,
                    Json(before) if before is not None else None,
                    Json(after) if after is not None else None,
                ))
                row = cur.fetchone()
        return {"id": row[0], "changed_at": row[1]}

    def changes(self, workspace_id: int, limit: int = 50) -> list[dict]:
        """Return the recent change-log rows for a workspace."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_change_log"),
                            (int(workspace_id), int(limit)))
                rows = cur.fetchall()
        return [{"id": r[0], "workspace_id": r[1], "actor": r[2],
                 "op": r[3], "target_kind": r[4], "target_name": r[5],
                 "before": r[6], "after": r[7], "changed_at": r[8]}
                for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

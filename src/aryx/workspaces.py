"""Workspaces: create/list/delete logically + physically isolated spaces.

Each workspace owns a LIST partition (FOR VALUES IN (id)) of every resolution
table and its own FalkorDB named graph. Create attaches partitions; delete
drops them (instant physical purge). Dynamic identifiers are built with
psycopg.sql so the workspace id is never string-interpolated unsafely.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg import sql

from aryx.queries import load

logger = logging.getLogger(__name__)

_PARTITIONED = ["aryx_landed_record", "aryx_entity", "aryx_entity_member", "aryx_relationship"]


def ws_graph(workspace_id: int) -> str:
    """FalkorDB graph name for a workspace."""
    return f"aryx_ws_{int(workspace_id)}"


class WorkspaceStore:
    """CRUD over workspaces plus their per-workspace table partitions."""

    def __init__(self, dsn: str) -> None:
        self._conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        self._conn.close()

    def _attach_partitions(self, wid: int) -> None:
        template = load("create_partition")
        for base in _PARTITIONED:
            self._conn.execute(sql.SQL(template).format(
                child=sql.Identifier(f"{base}_ws{wid}"),
                parent=sql.Identifier(base), wid=sql.Literal(wid)))

    def _drop_partitions(self, wid: int) -> None:
        template = load("drop_partition")
        for base in _PARTITIONED:
            self._conn.execute(sql.SQL(template).format(
                child=sql.Identifier(f"{base}_ws{wid}")))

    def create(self, name: str, description: str = "",
               context: str = "") -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("insert_workspace"), (name, description, context))
            row = cur.fetchone()
        wid = int(row[0])
        self._attach_partitions(wid)
        logger.info("workspace created id=%d name=%s", wid, name)
        return {"id": wid, "name": row[1], "description": row[2],
                "context": row[3], "created_at": row[4]}

    def list_all(self) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(load("select_workspaces"))
            return [{"id": r[0], "name": r[1], "description": r[2],
                     "context": r[3], "created_at": r[4]}
                    for r in cur.fetchall()]

    def set_context(self, wid: int, context: str) -> dict[str, Any]:
        """Update the workspace-level business context."""
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_context"), (context, int(wid)))
            row = cur.fetchone()
        logger.info("workspace context updated id=%s len=%d", wid, len(context))
        return {"id": row[0], "name": row[1], "description": row[2],
                "context": row[3], "created_at": row[4]}

    def delete(self, wid: int) -> None:
        """Physically purge a workspace: drop partitions + its run/job rows."""
        if int(wid) == 1:
            raise ValueError("the Default workspace cannot be deleted")
        self._drop_partitions(int(wid))
        with self._conn.cursor() as cur:
            cur.execute(load("delete_profiles_by_workspace"), (wid,))
            cur.execute(load("delete_tags_by_workspace"), (wid,))
            cur.execute(load("delete_runs_by_workspace"), (wid,))
            cur.execute(load("delete_jobs_by_workspace"), (wid,))
            cur.execute(load("delete_workspace_row"), (wid,))
        logger.info("workspace deleted id=%s", wid)

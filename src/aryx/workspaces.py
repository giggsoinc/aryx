"""Workspaces: CRUD + purge/nuke over LIST-partitioned isolated spaces."""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Json

from aryx.naming import ws_graph  # noqa: F401  re-exported for back-compat
from aryx.queries import load

logger = logging.getLogger(__name__)

_PARTITIONED = ["aryx_landed_record", "aryx_entity", "aryx_entity_member", "aryx_relationship"]


class WorkspaceStore:
    """CRUD + purge/nuke over workspaces and their table partitions."""

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

    def create(self, name: str, description: str = "", context: str = "",
               brief: dict | None = None) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("insert_workspace"),
                        (name, description, context, Json(brief or {})))
            row = cur.fetchone()
        wid = int(row[0])
        self._attach_partitions(wid)
        logger.info("workspace created id=%d name=%s", wid, name)
        return {"id": wid, "name": row[1], "description": row[2],
                "context": row[3], "brief": row[4] or {}, "created_at": row[5]}

    def list_all(self) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(load("select_workspaces"))
            return [{"id": r[0], "name": r[1], "description": r[2],
                     "context": r[3], "brief": r[4] or {}, "created_at": r[5]}
                    for r in cur.fetchall()]

    def set_context(self, wid: int, context: str) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_context"), (context, int(wid)))
            row = cur.fetchone()
        return {"id": row[0], "name": row[1], "description": row[2],
                "context": row[3], "brief": {}, "created_at": row[4]}

    def set_brief(self, wid: int, brief: dict) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_brief"),
                        (Json(brief or {}), int(wid)))
            row = cur.fetchone()
        logger.info("workspace brief updated id=%s keys=%d", wid, len(brief))
        return {"id": row[0], "name": row[1], "description": row[2],
                "context": row[3], "brief": row[4] or {},
                "created_at": row[5]}

    def get_survivorship(self, wid: int) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("select_workspace_survivorship"), (int(wid),))
            row = cur.fetchone()
        return (row[0] or {}) if row else {}

    def set_survivorship(self, wid: int, policy: dict) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_survivorship"),
                        (Json(policy or {}), int(wid)))
            row = cur.fetchone()
        logger.info("survivorship policy updated ws=%s", wid)
        return {"id": row[0], "survivorship": row[1] or {}}

    def purge_data(self, wid: int) -> dict[str, Any]:
        """Truncate partition children + delete non-partitioned rows by wid."""
        wid = int(wid)
        for base in _PARTITIONED:
            child = f"{base}_ws{wid}"
            try:
                self._conn.execute(
                    sql.SQL("TRUNCATE {} CASCADE").format(sql.Identifier(child)))
            except psycopg.errors.UndefinedTable:
                self._conn.rollback()
        stmts = load("purge_workspace_data")
        for stmt in stmts.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                self._conn.execute(stmt, {"wid": wid})
        with self._conn.cursor() as cur:
            cur.execute(load("delete_profiles_by_workspace"), (wid,))
            cur.execute(load("delete_tags_by_workspace"), (wid,))
        self._conn.execute(load("reset_workspace_context"), {"wid": wid})
        logger.info("workspace purged id=%s", wid)
        return {"status": "purged", "workspace_id": wid}

    def nuke(self) -> dict[str, Any]:
        """Factory reset: truncate everything, drop non-Default workspaces."""
        self._conn.execute(load("nuke_system"))
        for base in _PARTITIONED:
            for row in self._conn.execute(
                    load("select_partition_children"),
                    {"parent": base}).fetchall():
                self._conn.execute(
                    sql.SQL("TRUNCATE {} CASCADE").format(
                        sql.Identifier(row[0])))
        non_default = self._conn.execute(
            load("select_non_default_workspace_ids")).fetchall()
        for (wid,) in non_default:
            self._drop_partitions(wid)
        self._conn.execute(load("delete_non_default_workspaces"))
        self._conn.execute(load("reset_workspace_context"), {"wid": 1})
        logger.info("system nuked — factory reset complete")
        return {"status": "nuked", "workspaces_removed": len(non_default)}

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

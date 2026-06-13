"""CRUD for declared relationship types (Slice W2 / option g).

Backs the modelling canvas: drawn edges persist as owl:ObjectProperty-like
rows here so the ontology survives a refresh and the projection pipeline
has a catalog of expected edges before any ingest runs.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class RelationshipTypeStore:
    """Declared relationship type catalog scoped per workspace."""

    def __init__(self, dsn: str) -> None:
        self._pool = get_pool(dsn)

    def upsert(self, workspace_id: int, name: str,
               source_type: str, target_type: str,
               description: str = "") -> dict[str, Any]:
        """Idempotent declare: same (source, name, target) just updates desc."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("insert_relationship_type"), {
                "workspace_id": int(workspace_id), "name": name,
                "source_type": source_type, "target_type": target_type,
                "description": description})
            row = cur.fetchone()
        logger.info("relationship type upserted id=%s ws=%s %s-[%s]->%s",
                    row[0], workspace_id, source_type, name, target_type)
        return self._row(row)

    def list(self, workspace_id: int) -> list[dict[str, Any]]:
        """All declared relationship types for a workspace."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("select_relationship_types"),
                        {"workspace_id": int(workspace_id)})
            return [self._row(r) for r in cur.fetchall()]

    def delete(self, rel_id: int) -> None:
        """Hard-delete a declared relationship type."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("delete_relationship_type"),
                        {"id": int(rel_id)})
        logger.info("relationship type deleted id=%s", rel_id)

    @staticmethod
    def _row(row: tuple) -> dict[str, Any]:
        return {"id": row[0], "workspace_id": row[1], "name": row[2],
                "source_type": row[3], "target_type": row[4],
                "description": row[5], "created_at": row[6]}

"""Persistence for validated graph versions (C05).

Workspace-scoped. Versions are insert-only; the original JSON and the canonical
(normalized) graph are both stored. Same content hash under a graph is stored
once. Provides bounded adapter reads of the normalized graph.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from aryx.graph_intake.models import GraphIntakeResult
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class GraphIntakeStore:
    """Reads and writes validated graph versions for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def count_versions(self, graph_id: str) -> int:
        """Return how many versions exist for a graph (for the next tag)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("count_graph_versions"), (self._ws, graph_id))
                return int(cur.fetchone()[0])

    def find_by_hash(self, graph_id: str, content_hash: str) -> GraphIntakeResult | None:
        """Return an existing version with this content hash, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_graph_version_by_hash"),
                            (self._ws, graph_id, content_hash))
                row = cur.fetchone()
        return GraphIntakeResult(**row[0]) if row else None

    def save(self, result: GraphIntakeResult, graph_json: dict[str, Any],
             normalized: dict[str, Any]) -> None:
        """Insert one immutable graph version."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_graph_version"),
                    (
                        self._ws, result.graph_id, result.graph_version,
                        result.content_hash, Json(result.dataset_ids),
                        result.entity_count, result.relationship_count,
                        result.duplicate_entities, result.duplicate_relationships,
                        result.dangling_relationships, result.schema_status,
                        result.normalized_graph_ref, Json(graph_json),
                        Json(normalized), Json(result.model_dump(mode="json")),
                    ),
                )
        logger.info("saved graph version ws=%s graph=%s version=%s status=%s",
                    self._ws, result.graph_id, result.graph_version, result.schema_status)

    def latest(self, graph_id: str) -> GraphIntakeResult | None:
        """Return the newest version's intake report, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_graph_latest"), (self._ws, graph_id))
                row = cur.fetchone()
        return GraphIntakeResult(**row[0]) if row else None

    def list(self, limit: int = 50) -> list[GraphIntakeResult]:
        """Return recent graph versions across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_graph_versions"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [GraphIntakeResult(**r[0]) for r in rows]

    def adapter_read(self, graph_id: str, limit: int = 100) -> dict[str, Any]:
        """Bounded read of the latest normalized graph (for the graph profiler)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_graph_normalized"), (self._ws, graph_id))
                row = cur.fetchone()
        if not row:
            return {"entities": [], "relationships": []}
        norm = row[0]
        cap = max(1, int(limit))
        return {
            "entities": (norm.get("entities") or [])[:cap],
            "relationships": (norm.get("relationships") or [])[:cap],
        }

    def full_normalized(self, graph_id: str) -> dict[str, Any]:
        """Return the complete latest normalized graph (for the graph profiler)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_graph_normalized"), (self._ws, graph_id))
                row = cur.fetchone()
        return row[0] if row else {"entities": [], "relationships": []}

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

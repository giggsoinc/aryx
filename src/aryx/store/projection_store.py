"""Projection bookkeeping for incremental graph updates (G8).

Dirty-set computation lives in Postgres — never diff the graph itself:
dirty entities are rows touched since the watermark; tombstones are ids in
the projected side table that no longer exist in aryx_entity.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ProjectionStore:
    """Watermark + projected-id side table + dirty-set queries."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def watermark(self) -> Any:
        """Last successful projection time, or None (forces full rebuild)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_projection_state"), (self._ws,))
                row = cur.fetchone()
        return row[0] if row else None

    def advance_watermark(self) -> None:
        """Record a successful projection at now()."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("upsert_projection_state"), (self._ws,))

    def total_entities(self) -> int:
        """Entity count for the dirty-ratio mode decision."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("count_entities"), (self._ws,))
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def dirty_entities(self, since: Any) -> list[tuple[int, str, dict]]:
        """(id, type, attributes) for entities touched since the watermark."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dirty_entities"), (self._ws, since))
                return [(r[0], r[1], r[2]) for r in cur.fetchall()]

    def tombstones(self) -> list[int]:
        """Projected entity ids that no longer exist in Postgres."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_tombstones"), (self._ws, self._ws))
                return [r[0] for r in cur.fetchall()]

    def mark_projected(self, entity_ids: list[int]) -> None:
        """Record entity ids as present in the graph."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(load("upsert_projected_entity"),
                                [(self._ws, eid) for eid in entity_ids])

    def unmark_projected(self, entity_ids: list[int]) -> None:
        """Drop tombstoned ids from the side table."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(load("remove_projected_entity"),
                                [(self._ws, eid) for eid in entity_ids])

    def provenance_for(self, entity_ids: list[int]) -> list[tuple]:
        """(entity_id, system, dataset, record_id) for the dirty set."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_provenance_for_entities"),
                            (self._ws, entity_ids))
                return cur.fetchall()

    def relationships_for(self, entity_ids: list[int]) -> list[tuple]:
        """(source_id, target_id, name) edges touching the dirty set."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_relationships_for_entities"),
                            (self._ws, entity_ids, entity_ids))
                return cur.fetchall()

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

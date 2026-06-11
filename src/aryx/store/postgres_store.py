"""PostgreSQL landing store: persists cleaned records + run bookkeeping (P1).

RDB is the source of truth. Statement text lives in aryx/queries/*.sql (DB-Guard
discipline: no inline SQL). Non-native payload values are stringified on the way
to JSONB so heterogeneous source types land safely.
"""
from __future__ import annotations

import json
import logging

from psycopg.types.json import Json

from aryx.models import CleanRecord, FieldProfile, FieldTag
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


def _dumps(value: object) -> str:
    """JSON-encode a value, stringifying non-native types (datetimes, etc.)."""
    return json.dumps(value, default=str)


class PostgresStore:
    """Persists landed records, profiles, and run bookkeeping to Postgres."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN.

        Args:
            dsn: PostgreSQL connection string.
            workspace_id: Partition this store writes into.
        """
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def start_run(self, system: str, dataset: str) -> int:
        """Open a run row in this workspace and return its generated id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_run"), (self._ws, system, dataset))
                row = cur.fetchone()
        run_id = int(row[0]) if row else 0
        logger.info("run started run_id=%s ws=%s system=%s", run_id, self._ws, system)
        return run_id

    def insert_records(self, run_id: int, records: list[CleanRecord]) -> None:
        """Bulk-insert a batch of cleaned records with provenance."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    load("insert_landed_record"),
                    [
                        (
                            self._ws,
                            run_id,
                            r.source.system,
                            r.source.dataset,
                            r.source.record_id,
                            Json(r.payload, dumps=_dumps),
                            r.cleaned_at,
                        )
                        for r in records
                    ],
                )

    def save_profiles(self, run_id: int, profiles: list[FieldProfile]) -> None:
        """Persist per-field profiles for a run."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    load("insert_field_profile"),
                    [
                        (
                            run_id,
                            p.field,
                            p.non_null,
                            p.distinct,
                            p.distinct_capped,
                            Json(p.samples, dumps=_dumps),
                        )
                        for p in profiles
                    ],
                )

    def save_tags(self, run_id: int, tags: list[FieldTag]) -> None:
        """Persist cheap-tier semantic field tags for a run."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    load("insert_field_tag"),
                    [(run_id, t.field, t.semantic_type, t.is_pii) for t in tags],
                )

    def finish_run(self, run_id: int, record_count: int) -> None:
        """Mark a run complete with its final record count."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("finish_run"), (record_count, run_id))

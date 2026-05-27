"""PostgreSQL landing store: persists cleaned records + run bookkeeping (P1).

RDB is the source of truth. Statement text lives in aryx/queries/*.sql (DB-Guard
discipline: no inline SQL). Non-native payload values are stringified on the way
to JSONB so heterogeneous source types land safely.
"""
from __future__ import annotations

import json
import logging

import psycopg
from psycopg.types.json import Json

from aryx.models import CleanRecord, FieldProfile
from aryx.queries import load

logger = logging.getLogger(__name__)


def _dumps(value: object) -> str:
    """JSON-encode a value, stringifying non-native types (datetimes, etc.)."""
    return json.dumps(value, default=str)


class PostgresStore:
    """Persists landed records, profiles, and run bookkeeping to Postgres."""

    def __init__(self, dsn: str) -> None:
        """Open a (non-autocommit) connection to the landing database.

        Args:
            dsn: PostgreSQL connection string.
        """
        self._conn = psycopg.connect(dsn, autocommit=False)

    def start_run(self, system: str, dataset: str) -> int:
        """Open a run row and return its generated id."""
        with self._conn.cursor() as cur:
            cur.execute(load("insert_run"), (system, dataset))
            row = cur.fetchone()
        self._conn.commit()
        run_id = int(row[0]) if row else 0
        logger.info("run started run_id=%s system=%s dataset=%s", run_id, system, dataset)
        return run_id

    def insert_records(self, run_id: int, records: list[CleanRecord]) -> None:
        """Bulk-insert a batch of cleaned records with provenance."""
        with self._conn.cursor() as cur:
            cur.executemany(
                load("insert_landed_record"),
                [
                    (
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
        self._conn.commit()

    def save_profiles(self, run_id: int, profiles: list[FieldProfile]) -> None:
        """Persist per-field profiles for a run."""
        with self._conn.cursor() as cur:
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
        self._conn.commit()

    def finish_run(self, run_id: int, record_count: int) -> None:
        """Mark a run complete with its final record count."""
        with self._conn.cursor() as cur:
            cur.execute(load("finish_run"), (record_count, run_id))
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

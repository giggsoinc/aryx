"""Persistence for Dataset Upload & Ingestion (C02).

Workspace-scoped. Versions are insert-only; the same content hash under a
dataset is stored once. Raw bytes live on disk (aryx.store.blob_store),
content-addressed by hash — Postgres holds only the hash + metadata, never
the bytes themselves (see migration 0043's header for why).
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.config import get_settings
from aryx.dataset.models import DatasetIngestResult
from aryx.queries import load
from aryx.store.blob_store import read_blob, write_blob
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class DatasetStore:
    """Reads and writes dataset + immutable version records for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)
        self._blob_dir = get_settings().blob_dir

    def upsert_dataset(self, dataset_id: str, request_id: str, file_name: str) -> None:
        """Create or refresh the logical dataset row."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("upsert_dataset"),
                            (self._ws, dataset_id, request_id, file_name))

    def count_versions(self, dataset_id: str) -> int:
        """Return how many versions exist for a dataset (for the next tag)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("count_dataset_versions"), (self._ws, dataset_id))
                return int(cur.fetchone()[0])

    def find_version_by_hash(self, dataset_id: str, content_hash: str) -> DatasetIngestResult | None:
        """Return an existing version with this content hash, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_version_by_hash"),
                            (self._ws, dataset_id, content_hash))
                row = cur.fetchone()
        return _row_to_result(row) if row else None

    def save_version(self, result: DatasetIngestResult, raw_bytes: bytes) -> None:
        """Snapshot the raw bytes to disk (content-addressed), then insert
        one immutable version row pointing at that blob. Mutates
        `result.raw_snapshot_ref` to the real stored ref so the in-memory
        result the caller holds matches what was actually persisted."""
        blob_ref = write_blob(self._blob_dir, result.content_hash, raw_bytes)
        result.raw_snapshot_ref = blob_ref
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_dataset_version"),
                    (
                        self._ws, result.dataset_id, result.dataset_version,
                        result.request_id, result.format, result.content_hash,
                        blob_ref,
                        result.row_count_estimate, Json(result.columns),
                        Json(result.sheets), result.ingestion_status,
                        result.processing_status, Json(result.errors),
                        result.file_name, result.file_size_bytes,
                    ),
                )
        logger.info("saved dataset version ws=%s dataset=%s version=%s",
                    self._ws, result.dataset_id, result.dataset_version)

    def set_processing(self, dataset_id: str, version: str, status: str,
                       errors: list[str] | None = None) -> None:
        """Update a version's processing status (auto-trigger lifecycle)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("update_dataset_processing"),
                            (status, Json(errors or []), self._ws, dataset_id, version))

    def latest(self, dataset_id: str) -> DatasetIngestResult | None:
        """Return the newest version of a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return _row_to_result(row) if row else None

    def list_versions(self, limit: int = 50) -> list[DatasetIngestResult]:
        """Return recent versions across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_dataset_versions"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [_row_to_result(r) for r in rows]

    def latest_version(self, dataset_id: str) -> str | None:
        """Return the newest version tag for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_latest_version"),
                            (self._ws, dataset_id))
                row = cur.fetchone()
        return row[0] if row else None

    def get_raw(self, dataset_id: str, version: str) -> tuple[bytes, str] | None:
        """Return (raw_bytes, format) for a version's immutable snapshot,
        reading the bytes back from disk via its stored blob ref."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_raw"),
                            (self._ws, dataset_id, version))
                row = cur.fetchone()
        if not row:
            return None
        blob_ref, fmt = row
        return (read_blob(self._blob_dir, blob_ref), fmt)

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""


def _row_to_result(row: tuple) -> DatasetIngestResult:
    """Rebuild a DatasetIngestResult from a stored row (no raw bytes)."""
    return DatasetIngestResult(
        request_id=row[0],
        dataset_id=row[1],
        dataset_version=row[2],
        format=row[3],
        content_hash=row[4],
        raw_snapshot_ref=row[5],
        row_count_estimate=row[6],
        columns=row[7] or [],
        sheets=row[8] or [],
        ingestion_status=row[9],
        processing_status=row[10],
        errors=row[11] or [],
        file_name=row[12],
        file_size_bytes=row[13],
        created_at=row[14],
    )

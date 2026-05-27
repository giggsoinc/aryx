"""Batching RecordSink: buffers cleaned records and bulk-inserts them.

This is the concrete sink that plugs into the Increment-1 RecordSink seam,
keeping memory bounded at scale by flushing in fixed batches.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aryx.models import CleanRecord

if TYPE_CHECKING:
    from aryx.store.postgres_store import PostgresStore

_BATCH = 500


class BatchSink:
    """Buffer cleaned records and flush them to the store in batches."""

    def __init__(self, store: "PostgresStore", run_id: int, size: int = _BATCH) -> None:
        """Configure the sink for one run.

        Args:
            store: Open Postgres landing store.
            run_id: The run these records belong to.
            size: Number of records to buffer before a bulk insert.
        """
        self._store = store
        self._run_id = run_id
        self._size = size
        self._buffer: list[CleanRecord] = []
        self.total = 0

    def __call__(self, record: CleanRecord) -> None:
        """Accept one record, flushing when the batch fills."""
        self._buffer.append(record)
        self.total += 1
        if len(self._buffer) >= self._size:
            self.flush()

    def flush(self) -> None:
        """Persist any buffered records and clear the buffer."""
        if not self._buffer:
            return
        self._store.insert_records(self._run_id, self._buffer)
        self._buffer.clear()

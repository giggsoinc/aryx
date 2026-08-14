"""Dataset ingestion pipeline (C02) — deterministic, no LLM.

Mirrors the component Procedure:
  1. receive file bytes (streamed upload handled by the API layer)
  2. verify extension, MIME signature, size, file count (API + `detect`)
  3. reject encrypted or unsupported workbook content (`detect`)
  4. compute a SHA-256 content hash
  5. store the raw file immutably (versioned snapshot; API persists the bytes)
  6. enumerate CSV properties / (workbook sheets are rejected here)
  7. create dataset + version records
  8. (API) queue profiling / auto-trigger the entity pipeline

Immutability + versioning: identical content (same hash) under the same logical
dataset returns the existing version (status "duplicate"); new content becomes
the next version. The raw snapshot is never mutated.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Protocol

from psycopg.errors import UniqueViolation

from aryx.dataset.formats import detect, enumerate_data
from aryx.dataset.models import DatasetIngestResult

logger = logging.getLogger(__name__)

_MAX_FILE = 20 * 1024 * 1024  # 20 MB per file (matches the existing upload cap).
_VERSION_RETRIES = 5          # concurrent-upload version-collision retries


class DatasetSink(Protocol):
    """The persistence surface register_dataset needs (see store.dataset_store)."""

    def find_version_by_hash(self, dataset_id: str, content_hash: str) -> DatasetIngestResult | None: ...
    def count_versions(self, dataset_id: str) -> int: ...
    def upsert_dataset(self, dataset_id: str, request_id: str, file_name: str) -> None: ...
    def save_version(self, result: DatasetIngestResult, raw_bytes: bytes) -> None: ...


def _slug(file_name: str) -> str:
    """Derive a stable dataset slug from a file name stem."""
    stem = Path(file_name).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "dataset"


def register_dataset(
    *,
    data: bytes,
    file_name: str,
    request_id: str,
    store: DatasetSink,
) -> DatasetIngestResult:
    """Validate, hash, enumerate, and version a dataset upload.

    Returns a DatasetIngestResult. `ingestion_status` is:
      - "rejected"  — failed validation (not persisted; `errors` explains),
      - "duplicate" — identical content already stored (returns that version),
      - "accepted"  — a new immutable version was created.
    """
    ext = Path(file_name).suffix.lower()
    content_hash = "sha256:" + hashlib.sha256(data).hexdigest()
    dataset_id = f"dataset_{_slug(file_name)}"
    size = len(data)

    # Step 2/3 — signature + size + format gate.
    errors: list[str] = []
    if size > _MAX_FILE:
        errors.append(f"file exceeds 20 MB limit ({size} bytes)")
    fmt, reject = detect(data, ext)
    if reject:
        errors.append(reject)
    if errors:
        logger.info("dataset rejected file=%s reasons=%s", file_name, errors)
        return DatasetIngestResult(
            request_id=request_id, dataset_id=dataset_id,
            format=fmt or ext.lstrip("."), content_hash=content_hash,
            ingestion_status="rejected", errors=errors,
            file_name=file_name, file_size_bytes=size,
        )

    # Step 4/5 idempotency — identical content is the same immutable version.
    existing = store.find_version_by_hash(dataset_id, content_hash)
    if existing is not None:
        existing.ingestion_status = "duplicate"
        logger.info("dataset duplicate file=%s dataset=%s version=%s",
                    file_name, dataset_id, existing.dataset_version)
        return existing

    # Step 6 — enumerate.
    columns, row_count = enumerate_data(data, fmt)

    # Step 7 — records. Version is the next tag under this logical dataset.
    # Concurrent uploads to the same dataset can compute the same version tag;
    # the UNIQUE(workspace, dataset_id, version) constraint then rejects the
    # loser. Retry with a bumped tag; if a same-hash row appeared meanwhile,
    # return it as a duplicate instead of dropping the snapshot.
    store.upsert_dataset(dataset_id, request_id, file_name)
    for _ in range(_VERSION_RETRIES):
        version = f"v{store.count_versions(dataset_id) + 1}"
        result = DatasetIngestResult(
            request_id=request_id, dataset_id=dataset_id, dataset_version=version,
            format=fmt, content_hash=content_hash,
            # save_version fills this in with the real blob store key
            # (content-hash-derived) once the bytes are actually written.
            row_count_estimate=row_count, columns=columns, sheets=[],
            ingestion_status="accepted", processing_status="pending",
            file_name=file_name, file_size_bytes=size,
        )
        try:
            store.save_version(result, raw_bytes=data)
        except UniqueViolation:
            dup = store.find_version_by_hash(dataset_id, content_hash)
            if dup is not None:
                dup.ingestion_status = "duplicate"
                return dup
            continue  # version tag was taken by a concurrent upload; bump + retry
        logger.info("dataset accepted file=%s dataset=%s version=%s rows=%d cols=%d",
                    file_name, dataset_id, version, row_count, len(columns))
        return result
    raise RuntimeError(f"could not assign a version for {dataset_id} after "
                       f"{_VERSION_RETRIES} attempts")

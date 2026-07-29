"""Data contracts for Dataset Upload & Ingestion (C02)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class DatasetIngestResult(BaseModel):
    """Outcome of a dataset ingestion — one immutable version, or a rejection."""

    request_id: str = Field(default="", description="Correlation id from C01.")
    dataset_id: str = Field(description="Logical dataset id, e.g. 'dataset_contracts'.")
    dataset_version: str = Field(default="", description="Immutable version tag, e.g. 'v1'.")
    schema_version: str = Field(default=SCHEMA_VERSION)
    format: str = Field(default="", description="Detected format: 'csv' | 'json'.")
    content_hash: str = Field(default="", description="'sha256:<hex>' of the raw bytes.")
    raw_snapshot_ref: str = Field(default="", description="Logical ref of the immutable snapshot.")
    row_count_estimate: int = 0
    columns: list[str] = Field(default_factory=list)
    sheets: list[str] = Field(default_factory=list)
    ingestion_status: Literal["accepted", "rejected", "duplicate"] = "accepted"
    processing_status: str = Field(
        default="pending",
        description="pending | queued | running | complete | failed | awaiting_graph_json",
    )
    errors: list[str] = Field(default_factory=list)
    file_name: str = ""
    file_size_bytes: int = 0
    created_at: datetime = Field(default_factory=_utcnow)

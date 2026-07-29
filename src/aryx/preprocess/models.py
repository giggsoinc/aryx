"""Data contracts for Preprocessing and Transformation (C10).

C10 never mutates the raw C02 snapshot — it produces a transformation LOG
(this module) describing what would happen/happened to each referenced
column, not a second materialized copy of the row data. There is no
downstream execution/compute stage yet to consume materialized rows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TransformationEntry(BaseModel):
    """What happened to one column during preprocessing."""

    column: str
    operation: str
    failed_rows: int = 0
    changed_rows: int = 0
    reverted: bool = Field(
        default=False,
        description="True if failed_rows exceeded the safety threshold — this "
        "column was reverted to its original values and kept, not dropped.")


class AnalysisDataset(BaseModel):
    """The C10 transformation log for one dataset version."""

    analysis_dataset_id: str
    source_dataset_id: str
    source_dataset_version: str
    schema_version: str = SCHEMA_VERSION
    row_count: int = 0
    transformations: list[TransformationEntry] = Field(default_factory=list)
    quality_summary: dict[str, int] = Field(default_factory=dict)
    lineage_map_ref: str = ""
    status: Literal["ready", "ready_with_warnings"] = "ready"
    created_at: datetime = Field(default_factory=_utcnow)

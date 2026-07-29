"""Data contracts for the Deterministic Dataset Profiler (C03)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

CanonicalType = Literal[
    "identifier", "numeric", "categorical", "datetime", "boolean", "text", "empty",
]
CandidateRole = Literal[
    "identifier", "measure", "dimension", "time", "status", "attribute",
]


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class QualityFlag(BaseModel):
    """One evidence-based data-quality condition on a column."""

    column: str
    code: str = Field(description="e.g. 'missing_values', 'constant', 'mixed_types'.")
    count: int = 0
    detail: str = ""


class ColumnProfile(BaseModel):
    """Structure, quality, type, and role of a single column."""

    name: str
    original_type: str = Field(description="Type as loaded (string for CSV, JSON scalar type).")
    canonical_type: CanonicalType
    null_count: int = 0
    unique_count: int = 0
    sample_values: list[str] = Field(default_factory=list)
    candidate_role: CandidateRole
    # Applicable stats (populated when the type warrants).
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    top_categories: list[dict[str, object]] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    """Versioned, deterministic profile of one immutable dataset snapshot."""

    dataset_profile_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    row_count: int = 0
    column_count: int = 0
    duplicate_row_count: int = 0
    empty_row_count: int = 0
    columns: list[ColumnProfile] = Field(default_factory=list)
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    profile_status: Literal["valid", "invalid"] = "valid"
    created_at: datetime = Field(default_factory=_utcnow)

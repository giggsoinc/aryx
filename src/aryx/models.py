"""Core data contracts shared across pipeline stages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SourceRef(BaseModel):
    """Provenance pointer back to an originating record (P1)."""

    system: str = Field(description="Source system, e.g. 'postgresql', 'salesforce'.")
    dataset: str = Field(description="Table, object, or collection name.")
    record_id: str = Field(description="Natural key of the source record.")


class RawRecord(BaseModel):
    """A single record as extracted, before any cleaning."""

    source: SourceRef
    payload: dict[str, Any] = Field(description="Raw field values keyed by column.")
    extracted_at: datetime = Field(default_factory=_utcnow)


class CleanRecord(BaseModel):
    """A normalized record ready for profiling and downstream LLM stages."""

    source: SourceRef
    payload: dict[str, Any] = Field(description="Normalized field values.")
    cleaned_at: datetime = Field(default_factory=_utcnow)


class FieldProfile(BaseModel):
    """Aggregate statistics for one field across a batch (stage 3)."""

    field: str
    non_null: int = 0
    distinct: int = 0
    distinct_capped: bool = Field(
        default=False,
        description="True when distinct counting hit its cap (a floor, not exact).",
    )
    samples: list[str] = Field(default_factory=list)


class FieldTag(BaseModel):
    """A semantic type assigned to a field by the cheap-tier tagger (stage 4)."""

    field: str
    semantic_type: str = Field(description="snake_case type, e.g. 'email', 'amount'.")
    is_pii: bool = Field(default=False, description="True if the field holds PII.")

"""Data contracts for Knowledge Graph Intake & Validation (C05)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ValidationIssue(BaseModel):
    """One validation finding against the supplied graph."""

    code: str = Field(description="e.g. 'dangling_relationship', 'duplicate_entity'.")
    detail: str = ""
    count: int = 0


class GraphIntakeResult(BaseModel):
    """Outcome of validating + versioning one graph — the intake report."""

    graph_id: str
    graph_version: str = ""
    schema_version: str = SCHEMA_VERSION
    dataset_ids: list[str] = Field(default_factory=list)
    content_hash: str = ""
    normalized_graph_ref: str = ""
    entity_count: int = 0
    relationship_count: int = 0
    duplicate_entities: int = 0
    duplicate_relationships: int = 0
    dangling_relationships: int = 0
    empty_collections: list[str] = Field(default_factory=list)
    schema_status: Literal["valid", "invalid"] = "valid"
    issues: list[ValidationIssue] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)

"""Data contracts for the Semantic Field Interpreter (C04)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AlternativeMapping(BaseModel):
    """A runner-up concept for a column, kept for provenance/HITL."""

    business_concept: str
    confidence: float


class SemanticAnnotation(BaseModel):
    """A grounded mapping from one column to a business concept."""

    column: str
    business_concept: str
    confidence: float
    ontology_type: str = Field(default="", description="Provenance: ontology type the concept came from.")
    ontology_attribute: str = Field(default="", description="Provenance: ontology attribute matched.")
    evidence: str = Field(default="", description="Why this mapping was made (lexical/embedding).")
    alternatives: list[AlternativeMapping] = Field(default_factory=list)


class UnresolvedField(BaseModel):
    """A column left unresolved — no confident, grounded concept."""

    column: str
    reason: str
    best_confidence: float = 0.0


class SemanticProfile(BaseModel):
    """Versioned semantic interpretation of one dataset version."""

    semantic_profile_id: str
    dataset_id: str
    dataset_version: str
    dataset_profile_ref: str = ""
    domain: str = ""
    schema_version: str = SCHEMA_VERSION
    annotations: list[SemanticAnnotation] = Field(default_factory=list)
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    profile_status: Literal["valid", "invalid"] = "valid"
    created_at: datetime = Field(default_factory=_utcnow)

"""Core data contracts shared across pipeline stages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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


class OntologyType(BaseModel):
    """A canonical entity type in the ontology (stage 6)."""

    name: str = Field(description="Canonical type name, e.g. 'Organization'.")
    attributes: list[str] = Field(default_factory=list, description="Attribute names.")
    status: Literal["proposed", "approved"] = Field(
        default="proposed", description="HITL gate: new types start 'proposed'."
    )
    source: str = Field(default="agent", description="Origin: agent/dd/mdm/schema.org.")


class SchemaMapping(BaseModel):
    """Maps a source dataset/field to a canonical type/attribute (stage 6)."""

    source_system: str
    source_dataset: str
    source_field: str | None = Field(default=None, description="None = table-level.")
    ontology_type: str
    ontology_attribute: str | None = None
    confidence: float = 0.0


class ResolutionRecord(BaseModel):
    """A landed record prepared for entity resolution (stage 7)."""

    record_id: int = Field(description="aryx_landed_record.id (provenance link).")
    text: str = Field(description="Key text built from match attributes.")
    payload: dict[str, Any] = Field(description="Full payload for the golden record.")


class ResolvedEntity(BaseModel):
    """A canonical entity formed by merging matched records (stage 7)."""

    ontology_type: str
    attributes: dict[str, Any] = Field(description="Golden record (merged values).")
    confidence: float = 0.0


class EntityMember(BaseModel):
    """Provenance: a landed record belonging to a resolved entity (stage 7)."""

    landed_record_id: int
    confidence: float = 1.0


class Relationship(BaseModel):
    """A typed edge between two resolved entities (stage 8)."""

    source_entity_id: int
    target_entity_id: int
    name: str = Field(description="Edge label, e.g. 'places' or 'works_for'.")
    confidence: float = 0.0

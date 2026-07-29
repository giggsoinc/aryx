"""Data contracts for the Knowledge Graph Profiler (C06)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TypeCount(BaseModel):
    """A count of entities or relationships of one type."""

    type: str
    count: int = 0


class SchemaEdge(BaseModel):
    """A type-level edge that actually occurs in the graph."""

    source_type: str
    relationship: str
    target_type: str
    count: int = 0


class VerifiedPath(BaseModel):
    """A bounded, type-level path every hop of which exists in the graph."""

    path_id: str
    path: list[str] = Field(description="[Type, REL, Type, REL, Type, ...]")
    depth: int = Field(description="Number of relationship hops.")


class GraphQualityFlag(BaseModel):
    """A structural quality finding (disconnected/sparse region, missing key)."""

    code: str
    detail: str = ""
    type: str = ""
    count: int = 0


class GraphProfile(BaseModel):
    """Deterministic, versioned profile of a validated graph."""

    graph_profile_id: str
    graph_id: str
    graph_version: str
    schema_version: str = SCHEMA_VERSION
    user_objective: str = ""
    maximum_path_depth: int = 3
    entity_count: int = 0
    relationship_count: int = 0
    entity_types: list[TypeCount] = Field(default_factory=list)
    relationship_types: list[TypeCount] = Field(default_factory=list)
    schema_edges: list[SchemaEdge] = Field(default_factory=list)
    verified_paths: list[VerifiedPath] = Field(default_factory=list)
    quality_flags: list[GraphQualityFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    profile_status: Literal["valid", "invalid"] = "valid"
    created_at: datetime = Field(default_factory=_utcnow)

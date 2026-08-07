"""Data contracts for Context and Resource Retrieval (C07)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ApprovedColumn(BaseModel):
    """A column approved for planning, with its canonical type.

    `sample_values` are REAL values observed in the data (from C03's
    ColumnProfile.sample_values) — without these, the planner LLM has no way
    to know what literal string a categorical/status filter should compare
    against (e.g. "Renewed" vs "renewed" vs "Y") and either invents one or
    (more often, for a cautious model) omits the value entirely, which fails
    C09's missing_filter_value check. Capped small (see assemble.py) — this
    is a hint for the LLM to copy from, never a value it's required to use."""

    name: str
    type: str
    sample_values: list[str] = Field(default_factory=list)


class DatasetColumns(BaseModel):
    """One dataset's approved columns, kept namespaced within a workspace-scope
    context. Column names collide across datasets often (e.g. 'model' or
    'fields.item_id' can appear in a dozen unrelated files) — grouping by
    dataset_id, rather than flattening into one set, is what keeps a
    cross-dataset planning context unambiguous."""

    dataset_id: str
    dataset_version: str
    approved_columns: list[ApprovedColumn] = Field(default_factory=list)


class ResourceCitation(BaseModel):
    """Provenance for one retrieved resource in the package."""

    resource_id: str
    resource_type: str = Field(description="e.g. 'user_intent', 'dataset_profile'.")
    version: str = ""
    rank: int = 0
    retrieval_score: float = 1.0


class GraphPathHint(BaseModel):
    """Human-readable context for one `approved_graph_paths` entry.

    C06's GraphProfile already computes a full VerifiedPath (path segments,
    depth) for each id, but `approved_graph_paths` only ever kept the bare
    `path_id` string — the LLM had no way to judge which path is relevant
    without this. Additive only: `approved_graph_paths` stays the governed
    allow-list every consumer already types as `list[str]`; this is a
    parallel, cite-by-id lookup for planning-time judgment."""

    path_id: str
    label: str = Field(description="Human-readable rendering, e.g. "
                       "'Customer -> CONTRACT_CUSTOMER -> Contract'.")
    depth: int = 0


class PlanningContext(BaseModel):
    """The smallest versioned, approved context package for planning.

    Two scopes share this one model:
      - Single-dataset (dataset_id = a real dataset): `approved_columns` is
        that dataset's own columns; `datasets` is empty.
      - Workspace-wide (dataset_id = 'workspace_<id>', mirroring the C05/C06
        synthetic-id convention): `datasets` carries the authoritative,
        per-dataset-namespaced column groups; `approved_columns` is a deduped
        union kept for display/back-compat only — grounding code must use
        `datasets`, never the flat union, once `datasets` is non-empty.
    """

    planning_context_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    domain: str = ""
    objective: str = ""
    approved_columns: list[ApprovedColumn] = Field(default_factory=list)
    datasets: list[DatasetColumns] = Field(default_factory=list)
    approved_graph_paths: list[str] = Field(default_factory=list)
    graph_path_hints: list[GraphPathHint] = Field(
        default_factory=list, description="Readable label/depth per approved_graph_paths "
        "id — planning-time judgment aid, never a citable id itself.")
    graph_quality_notes: list[str] = Field(
        default_factory=list, description="Human-readable graph quality flags/limitations "
        "(C06) — grounds the LLM's own 'assumptions' instead of it guessing at caveats.")
    supported_operations: list[str] = Field(default_factory=list)
    supported_charts: list[str] = Field(default_factory=list)
    resource_citations: list[ResourceCitation] = Field(default_factory=list)
    completeness: dict[str, object] = Field(default_factory=dict)
    relevance: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    context_status: Literal["complete", "incomplete", "blocked"] = "complete"
    created_at: datetime = Field(default_factory=_utcnow)

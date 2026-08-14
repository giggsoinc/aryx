"""Data contracts for Dashboard Composition (C14).

Arranges an approved spec's already-validated results (C09/C13) into an
ordered, readable dashboard model. Can arrange artifacts — order, grouping,
section titles — but can NEVER alter a governed value, formula, axis, or ID
(see compose.py's module docstring). Hybrid: an optional LLM step may
suggest section titles/grouping, but the deterministic composition always
runs first and is the fallback whenever the LLM is unavailable or its
output doesn't validate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class DashboardComponent(BaseModel):
    """One placed, bound artifact — never a new value, formula, or ID; only
    an arrangement of an already-approved kpi_id/analysis_id."""

    component_id: str
    type: str
    source_ref: str = Field(description="The kpi_id or analysis_id this component renders.")
    position: int
    warning_refs: list[str] = Field(default_factory=list)
    compare_ref: str | None = Field(
        default=None, description="grouped_bar only: the second analysis_id "
        "to compare against source_ref, carried over from Visualization.")
    axis_refs: list[str] | None = Field(
        default=None, description="radar only: carried over from Visualization.axis_refs.")


class DashboardSection(BaseModel):
    section_id: str
    title: str
    components: list[DashboardComponent] = Field(default_factory=list)


class CompositionIssue(BaseModel):
    """A structural problem found during revalidation (step 7) — never a
    business-rule violation (C09/C13 already gate those)."""

    code: str
    reference: str = ""
    detail: str = ""


class DashboardModel(BaseModel):
    """The final, ordered dashboard document for one approved spec's results."""

    dashboard_model_id: str
    spec_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    title: str = ""
    audience: str = ""
    sections: list[DashboardSection] = Field(default_factory=list)
    max_columns: int = 3
    composition_status: Literal["valid", "invalid"] = "valid"
    issues: list[CompositionIssue] = Field(default_factory=list)
    composed_by: Literal["deterministic", "llm_assisted"] = "deterministic"
    created_at: datetime = Field(default_factory=_utcnow)

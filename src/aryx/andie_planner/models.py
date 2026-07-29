"""Data contracts for the Andie Jr Planning Orchestrator (C08)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class BusinessQuestion(BaseModel):
    question_id: str
    text: str


class KpiFilter(BaseModel):
    column: str
    operator: str = "equals"
    value: Any = None
    values: list[Any] | None = None


class KpiOperand(BaseModel):
    """One side of a ratio KPI (numerator or denominator)."""

    operation: str
    filter: KpiFilter | None = None


class Kpi(BaseModel):
    kpi_id: str
    name: str = ""
    dataset_id: str = Field(
        default="", description="Which dataset this KPI's columns come from "
        "(required in workspace-scope mode; empty in single-dataset mode).")
    source_columns: list[str] = Field(default_factory=list)
    operation: str
    measure: str | None = None
    filter: KpiFilter | None = None
    numerator: KpiOperand | None = None
    denominator: KpiOperand | None = None
    zero_denominator_policy: str | None = None
    format: str = "number"


class Analysis(BaseModel):
    analysis_id: str
    operation: str
    dataset_id: str = Field(
        default="", description="Which dataset this analysis's columns come "
        "from (required in workspace-scope mode; empty in single-dataset mode).")
    group_by: list[str] = Field(default_factory=list)
    metric: str | None = Field(default=None, description="A kpi_id this analysis reports on.")
    sort: str | None = None


class Visualization(BaseModel):
    chart_id: str
    chart_type: str
    source_ref: str = Field(description="A kpi_id or analysis_id this chart renders.")
    x_axis: str | None = None
    y_axis: str | None = None


class Assumption(BaseModel):
    code: str
    meaning: str = ""


class SpecWarning(BaseModel):
    code: str
    column: str = ""
    detail: str = ""


class DashboardSpec(BaseModel):
    """A candidate, non-executable dashboard specification."""

    spec_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    output_schema_version: str = "dashboard_spec_v1"
    objective: str = ""
    target_audience: str = ""
    business_questions: list[BusinessQuestion] = Field(default_factory=list)
    kpis: list[Kpi] = Field(default_factory=list)
    analyses: list[Analysis] = Field(default_factory=list)
    visualizations: list[Visualization] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[SpecWarning] = Field(default_factory=list)
    spec_status: Literal["valid", "invalid"] = "valid"
    model_name: str = ""
    model_tier: str = ""
    prompt_version: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class PlannerResult(BaseModel):
    """Outcome of one planning attempt — never an unhandled exception.

    `status="controlled_error"` covers a malformed/empty model response or a
    broker/provider failure that survived the one retry — the spec is None and
    `error_code`/`error_message` explain why. `status="controlled_failure"`
    covers a spec that parsed and grounded fine but was REJECTED by C09
    (pre-execution validation) on both the initial attempt and its one
    allowed repair retry — `spec` still holds the last (rejected) candidate
    for audit, `validation` holds its ValidationReport. The caller always
    gets a typed result, never a raised exception.
    """

    status: Literal["valid", "invalid", "controlled_error", "controlled_failure"]
    spec: DashboardSpec | None = None
    error_code: str | None = Field(
        default=None,
        description="'malformed_json' | 'llm_call_failed' | 'no_model_available' | "
        "'planner_validation_retry_exhausted'.")
    error_message: str = ""
    attempts: int = 0
    validation: dict[str, Any] | None = Field(
        default=None, description="Latest C09 ValidationReport, as a dict (see spec_validation.models).")
    analysis_datasets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="C10 AnalysisDataset transformation logs, one per dataset "
        "the approved spec references (see preprocess.models). Empty unless "
        "validation.status == 'approved'.")
    created_at: datetime = Field(default_factory=_utcnow)

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
    x_column: str | None = Field(
        default=None, description="row_points only: numeric column for the x value of each row.")
    y_column: str | None = Field(
        default=None, description="row_points only: numeric column for the y value of each row.")
    size_column: str | None = Field(
        default=None, description="row_points only (bubble chart_type): numeric column for point size.")
    start_column: str | None = Field(
        default=None, description="date_span/survival only: span start date, or cohort entry date.")
    end_column: str | None = Field(
        default=None, description="date_span/survival only: span end date, or event/exit date "
        "(null rows are censored — still active — for survival).")
    graph_path_id: str | None = Field(
        default=None, description="graph_relation only: an approved_graph_paths id (C06) "
        "naming the source/relationship/target triple to aggregate. group_by/metric are "
        "left empty for this operation.")


class Visualization(BaseModel):
    chart_id: str
    chart_type: str
    source_ref: str = Field(description="A kpi_id or analysis_id this chart renders.")
    x_axis: str | None = None
    y_axis: str | None = None
    compare_ref: str | None = Field(
        default=None, description="grouped_bar only: a second analysis_id to "
        "compare against source_ref, side-by-side per shared group_by category.")
    axis_refs: list[str] | None = Field(
        default=None, description="radar only: 3+ kpi_id/analysis_id refs, one per axis.")


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


class DeltaSpecItems(BaseModel):
    """One grounded ask-to-visualize request — see andie_planner.delta.

    `new_kpi`/`new_analysis` are populated only when the request needed a
    combination that didn't already exist in the spec being extended;
    `new_visualization` is the goal of the request and may be None if nothing
    survived grounding (see `warnings` for why)."""

    new_kpi: Kpi | None = None
    new_analysis: Analysis | None = None
    new_visualization: Visualization | None = None
    warnings: list[SpecWarning] = Field(default_factory=list)


class DeltaDraftResult(BaseModel):
    """Outcome of drafting one ask-to-visualize request — never an unhandled
    exception, same controlled-outcome contract as PlannerResult.

    `status="controlled_error"` mirrors PlannerResult: a malformed/empty
    model response or a broker/provider failure. `status="invalid"` means the
    model responded and grounding ran, but either nothing survived grounding
    (`items.new_visualization is None`) or the merged spec would fail C09
    validation (`would_validate=False`) — `preview_text`/`validation_errors`
    explain why either way. `status="valid"` means `items.new_visualization`
    is set AND the merged spec would pass C09 — safe to show the customer a
    confirm button."""

    status: Literal["valid", "invalid", "controlled_error"]
    items: DeltaSpecItems | None = None
    preview_text: str = ""
    would_validate: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str = ""
    attempts: int = 0
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
    execution_plans: list[dict[str, Any]] = Field(
        default_factory=list,
        description="C11 ExecutionPlan compilations, one per dataset the "
        "approved spec references (see execution_compiler.models). Empty "
        "unless validation.status == 'approved'.")
    created_at: datetime = Field(default_factory=_utcnow)

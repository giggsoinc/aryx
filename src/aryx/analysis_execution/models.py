"""Data contracts for Deterministic Analysis Execution (C12).

Runs a compiled C11 ExecutionPlan against real (C10-converted) rows and
produces the first real business values — KPI results, grouped analysis
breakdowns, lineage, and execution metrics. No LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class KpiLineage(BaseModel):
    """Which columns and compiled operations produced one KPI's value."""

    source_columns: list[str] = Field(default_factory=list)
    operation_ids: list[str] = Field(default_factory=list)
    dataset_version: str = ""


class KpiResult(BaseModel):
    """One KPI's real, computed value."""

    kpi_id: str
    value: float | None
    display_value: str
    numerator: float | None = None
    denominator: float | None = None
    sample_size: int = 0
    excluded_null_rows: int = 0
    lineage: KpiLineage = Field(default_factory=KpiLineage)


class AnalysisResultRow(BaseModel):
    """One group's breakdown from a grouped_* node.

    min/q1/q3/max are populated only for a grouped_quartiles_numeric result
    (box plot) — `value` still carries the median for KPI-card/table
    fallback display, same convention as ratio's numerator/denominator."""

    group_value: str
    value: float | None = None
    numerator: float | None = None
    denominator: float | None = None
    sample_size: int = 0
    min: float | None = None
    q1: float | None = None
    q3: float | None = None
    max: float | None = None
    # Populated only for a crosstab (grouped2d_*) result — the second
    # group_by column's value for this cell (e.g. sankey/treemap/heatmap_matrix).
    group_value_secondary: str | None = None
    # Populated only for a row_points result (scatter/bubble) — one point per
    # row, never aggregated.
    x: float | None = None
    y: float | None = None
    size: float | None = None
    # Populated only for a row_date_spans result (gantt) — raw date strings,
    # never parsed/computed here (C12 never invents a date format).
    start: str | None = None
    end: str | None = None
    # Populated only for a survival_curve result — one row per
    # (group_value, duration_days) point; `value` carries survived_fraction,
    # `sample_size` carries at_risk, same "value stands in" convention as
    # quartiles' median.
    duration_days: float | None = None
    # Populated only for a histogram_buckets result — group_value is the
    # group key ("_all_" when ungrouped).
    buckets: list[dict[str, float]] | None = None


class AnalysisResult(BaseModel):
    """One Analysis's full per-group breakdown."""

    analysis_id: str
    group_column: str
    rows: list[AnalysisResultRow] = Field(default_factory=list)


class ExecutionMetrics(BaseModel):
    runtime_ms: int = 0
    nodes_completed: int = 0
    nodes_failed: int = 0


class ExecutionRun(BaseModel):
    """One deterministic execution of a compiled plan — always a typed
    result, never an unhandled exception (mirrors PlannerResult's
    controlled-outcome contract)."""

    execution_run_id: str
    execution_plan_id: str
    spec_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    status: Literal["completed", "failed", "partial"] = "completed"
    kpi_results: list[KpiResult] = Field(default_factory=list)
    analysis_results: list[AnalysisResult] = Field(default_factory=list)
    execution_metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    errors: list[str] = Field(default_factory=list)
    validation: dict[str, object] | None = Field(
        default=None,
        description="C13 PostExecutionReport, as a dict (see "
        "post_execution_validation.models) — attached right after this run "
        "completes, gating eligible_for_dashboard independently of `status`.")
    created_at: datetime = Field(default_factory=_utcnow)

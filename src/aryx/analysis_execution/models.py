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
    """One group's breakdown from a grouped_* node."""

    group_value: str
    value: float | None = None
    numerator: float | None = None
    denominator: float | None = None
    sample_size: int = 0


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

"""Data contracts for the Execution Compiler (C11).

Compiles an approved DashboardSpec (C09) into a typed, acyclic execution plan
built exclusively from vetted operation templates (see templates.py) — no
LLM, no arbitrary code generation. The compiler only binds approved
parameters to known templates (see compile.py's module docstring).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ExecutionNode(BaseModel):
    """One bound operation in the execution DAG — a template name plus the
    approved parameters bound to it, and the node_ids it depends on."""

    node_id: str
    template: str
    dataset_id: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class CompilationIssue(BaseModel):
    """A structural problem found while compiling or validating the plan —
    never a business-rule violation (C09 already gates those)."""

    code: str
    node_id: str = ""
    detail: str = ""


class ExecutionPlan(BaseModel):
    """A typed, acyclic execution plan compiled from one approved DashboardSpec."""

    execution_plan_id: str
    spec_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    nodes: list[ExecutionNode] = Field(default_factory=list)
    plan_acyclic: bool = True
    row_limit: int = 0
    node_limit: int = 0
    compilation_status: Literal["success", "rejected"] = "success"
    issues: list[CompilationIssue] = Field(default_factory=list)
    kpi_final_node: dict[str, str] = Field(
        default_factory=dict,
        description="kpi_id -> the node_id whose result IS that KPI's value "
        "(the safe_ratio node for ratio KPIs, the count_rows/*_numeric node "
        "otherwise) — how C12 finds each KPI's value without guessing from "
        "node_id naming.")
    kpi_lineage_nodes: dict[str, list[str]] = Field(
        default_factory=dict,
        description="kpi_id -> every node_id compiled for that KPI (filters, "
        "operands, the final node), in execution order — C12's lineage.operation_ids.")
    analysis_node: dict[str, str] = Field(
        default_factory=dict,
        description="analysis_id -> its single grouped_* node_id.")
    created_at: datetime = Field(default_factory=_utcnow)

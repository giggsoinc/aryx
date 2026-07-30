"""Deterministic Analysis Execution (C12).

Runs a compiled C11 execution plan against real, C10-converted rows and
produces the first real business values: KPI results, grouped analysis
breakdowns, evidence lineage, and execution metrics. No LLM. On-demand only
(POST /execution-run/run) — never auto-chained onto C08-C11's approval flow.
"""

from aryx.analysis_execution.execute import run_plan
from aryx.analysis_execution.models import (
    AnalysisResult, AnalysisResultRow, ExecutionMetrics, ExecutionRun, KpiLineage, KpiResult,
)
from aryx.analysis_execution.run import run_analysis_execution

__all__ = [
    "run_analysis_execution", "run_plan",
    "ExecutionRun", "KpiResult", "KpiLineage", "AnalysisResult", "AnalysisResultRow",
    "ExecutionMetrics",
]

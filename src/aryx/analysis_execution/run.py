"""Glue: run C12 for the latest compiled C11 execution plan and persist the
result.

On-demand only (like C08) — never auto-chained. Triggered explicitly via
POST /execution-run/run; nothing runs until asked.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from aryx.analysis_execution.data import load_typed_rows
from aryx.analysis_execution.execute import (
    _kpi_result_from_node,
    resolve_graph_relation_nodes,
    run_plan,
)
from aryx.analysis_execution.models import (
    AnalysisResult,
    AnalysisResultRow,
    ExecutionMetrics,
    ExecutionRun,
    KpiLineage,
    KpiResult,
)
from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi
from aryx.ports import ports
from aryx.post_execution_validation.run import run_post_execution_validation
from aryx.store.dashboard_spec_store import DashboardSpecStore
from aryx.store.execution_plan_store import ExecutionPlanStore
from aryx.store.execution_run_store import ExecutionRunStore

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RUNTIME_SECONDS = 30.0
_DEFAULT_MAX_ROWS = 1_000_000


def _display_value(value: float | None, fmt: str) -> str:
    if value is None:
        return "—"  # em dash — zero-denominator/no-data, never fabricated as "0%"
    if fmt == "percentage":
        return f"{value * 100:.2f}%"
    if fmt == "currency":
        return f"${value:,.0f}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _1d_grouped_rows(grouped: dict[str, Any]) -> list[AnalysisResultRow]:
    """The original C12 shape: one flat row per group, value shape depending
    on which grouped_* template produced it (count/sum/average/median/ratio/
    quartiles) — unchanged from before C15's new chart-type shapes."""
    return [
        AnalysisResultRow(
            group_value=g,
            value=(v.get("median") if isinstance(v, dict) and "q1" in v
                  else v.get("value") if isinstance(v, dict) else float(v)),
            numerator=(v.get("numerator") if isinstance(v, dict) else None),
            denominator=(v.get("denominator") if isinstance(v, dict) else None),
            sample_size=(v.get("sample_size") if isinstance(v, dict) else int(v)),
            min=(v.get("min") if isinstance(v, dict) else None),
            q1=(v.get("q1") if isinstance(v, dict) else None),
            q3=(v.get("q3") if isinstance(v, dict) else None),
            max=(v.get("max") if isinstance(v, dict) else None))
        for g, v in sorted(grouped.items())
    ]


def _crosstab_rows(grouped: dict[tuple[str, str], Any]) -> list[AnalysisResultRow]:
    """crosstab (grouped2d_*) — same per-cell value shapes as the 1D case,
    keyed by (group_value, group_value_secondary) instead of a bare group."""
    return [
        AnalysisResultRow(
            group_value=g1, group_value_secondary=g2,
            value=(v.get("value") if isinstance(v, dict) else float(v)),
            numerator=(v.get("numerator") if isinstance(v, dict) else None),
            denominator=(v.get("denominator") if isinstance(v, dict) else None),
            sample_size=(v.get("sample_size") if isinstance(v, dict) else int(v)))
        for (g1, g2), v in sorted(grouped.items())
    ]


def _row_points_rows(points: list[dict[str, Any]]) -> list[AnalysisResultRow]:
    """row_points — one AnalysisResultRow per already-computed point, never
    re-aggregated (scatter/bubble)."""
    return [AnalysisResultRow(group_value=pt["label"], x=pt["x"], y=pt["y"], size=pt.get("size"),
                              sample_size=1)
           for pt in points]


def _date_span_rows(spans: list[dict[str, Any]]) -> list[AnalysisResultRow]:
    """date_span — one AnalysisResultRow per span (gantt)."""
    return [AnalysisResultRow(group_value=span["label"], start=span["start"], end=span.get("end"),
                              sample_size=1)
           for span in spans]


def _survival_rows(curves: dict[str, list[dict[str, float]]]) -> list[AnalysisResultRow]:
    """survival — one AnalysisResultRow per (group, duration) point; `value`
    carries survived_fraction and `sample_size` carries at_risk, the same
    "value stands in for the real payload" convention quartiles already
    uses for its median."""
    return [
        AnalysisResultRow(group_value=g, duration_days=pt["duration_days"],
                          value=pt["survived_fraction"], sample_size=int(pt["at_risk"]))
        for g, points in sorted(curves.items()) for pt in points
    ]


def _histogram_rows(result: dict[str, Any]) -> list[AnalysisResultRow]:
    """histogram — one AnalysisResultRow per group (or a single "_all_" row
    when the Analysis has no group_by), `buckets` carrying the payload."""
    if "buckets" in result:  # ungrouped: {"buckets": [...], "sample_size": ..., ...}
        return [AnalysisResultRow(group_value="_all_", buckets=result["buckets"],
                                  sample_size=result["sample_size"])]
    return [
        AnalysisResultRow(group_value=g, buckets=v["buckets"], sample_size=v["sample_size"])
        for g, v in sorted(result.items())
    ]


def _analysis_rows(analysis: Analysis, result: Any) -> list[AnalysisResultRow]:
    """Dispatch on the Analysis's own `operation` (never shape-sniffed) to
    the right unpacking of its compiled node's raw result — see
    execution_compiler.compile._compile_analysis for what each operation
    compiles to."""
    if analysis.operation == "crosstab":
        return _crosstab_rows(result)
    if analysis.operation == "row_points":
        return _row_points_rows(result)
    if analysis.operation == "date_span":
        return _date_span_rows(result)
    if analysis.operation == "survival":
        return _survival_rows(result)
    if analysis.operation == "histogram":
        return _histogram_rows(result)
    return _1d_grouped_rows(result)


def _unpack_analysis(
    analysis: Analysis, result: Any,
) -> tuple[list[AnalysisResultRow] | None, str]:
    """Unpack one analysis's node result, containing any shape mismatch.

    Returns `(rows, "")` on success and `(None, reason)` when the computed
    result does not match the shape `analysis.operation` promised.

    `_analysis_rows` dispatches strictly on the DECLARED operation and never
    shape-sniffs — that is deliberate, but it makes C12 wholly dependent on
    C11 honouring the declaration. When C11 cannot compile the declared
    operation it falls back to another template, and the node still
    SUCCEEDS — so the mismatch never reaches `exec_errors` via the normal
    node-failure path, and the raw exception used to escape the analysis
    loop and abort the entire run. One unusable chart must never discard
    every other analysis's real results, so it is downgraded to a per-
    analysis error and the run completes as "partial".
    """
    try:
        return _analysis_rows(analysis, result), ""
    except (TypeError, KeyError, IndexError, AttributeError, ValueError) as exc:
        return None, (
            f"analysis {analysis.analysis_id!r} declared operation "
            f"{analysis.operation!r} but its computed result did not match "
            f"that shape — {type(exc).__name__}: {exc}. This chart is "
            f"omitted; the rest of the dashboard is unaffected.")


def _kpi_source_columns(kpi: Kpi) -> list[str]:
    """Every column this KPI's lineage should cite — source_columns plus
    whatever measure/filter columns the compiler actually bound."""
    cols = list(kpi.source_columns)
    if kpi.measure and kpi.measure not in cols:
        cols.append(kpi.measure)
    if kpi.filter and kpi.filter.column not in cols:
        cols.append(kpi.filter.column)
    for operand in (kpi.numerator, kpi.denominator):
        if operand and operand.filter and operand.filter.column not in cols:
            cols.append(operand.filter.column)
    return cols


def run_analysis_execution(
    dsn: str, workspace_id: int, dataset_id: str, *,
    maximum_runtime_seconds: float = _DEFAULT_MAX_RUNTIME_SECONDS,
    maximum_rows: int = _DEFAULT_MAX_ROWS,
) -> ExecutionRun:
    """Run C12 for `dataset_id`'s latest compiled plan — a real dataset_id in
    single-dataset mode, "workspace_{id}" in workspace mode (same convention
    C08/C11 already use). Always returns a typed ExecutionRun; never raises.
    """
    start = time.monotonic()
    execution_run_id = f"execution_{dataset_id}_{uuid.uuid4().hex[:8]}"

    plan_store = ExecutionPlanStore(dsn, workspace_id)
    try:
        plan = plan_store.latest(dataset_id)
    finally:
        plan_store.close()
    if plan is None:
        return ExecutionRun(
            execution_run_id=execution_run_id, execution_plan_id="", spec_id="",
            dataset_id=dataset_id, dataset_version="", status="failed",
            errors=[f"no compiled execution plan for {dataset_id!r} — approve a spec first"])
    if plan.compilation_status == "rejected":
        return ExecutionRun(
            execution_run_id=execution_run_id, execution_plan_id=plan.execution_plan_id,
            spec_id=plan.spec_id, dataset_id=dataset_id, dataset_version=plan.dataset_version,
            status="failed",
            errors=["execution plan was rejected at compile time (C11) — nothing to run"])

    spec_store = DashboardSpecStore(dsn, workspace_id)
    try:
        planner_result = spec_store.latest(dataset_id)
    finally:
        spec_store.close()
    spec: DashboardSpec | None = planner_result.spec if planner_result else None
    if spec is None:
        return ExecutionRun(
            execution_run_id=execution_run_id, execution_plan_id=plan.execution_plan_id,
            spec_id=plan.spec_id, dataset_id=dataset_id, dataset_version=plan.dataset_version,
            status="failed", errors=["no approved spec on record to resolve KPI metadata"])

    # plan.row_limit is the plan-wide cap (see execution_compiler.compile);
    # applied per referenced dataset here for simplicity — generous, never
    # unsafe, in the multi-dataset case.
    row_cap = min(maximum_rows, plan.row_limit) if plan.row_limit else maximum_rows
    dataset_ids = sorted({n.dataset_id for n in plan.nodes if n.dataset_id})
    rows_by_dataset: dict[str, list] = {}
    dataset_version_by_id: dict[str, str] = {}
    for did in dataset_ids:
        rows, version = load_typed_rows(dsn, workspace_id, did, spec, row_cap)
        rows_by_dataset[did] = rows
        dataset_version_by_id[did] = version

    resolve_graph_relation_nodes(dsn, workspace_id, plan)
    graph_reader = (ports().graph_reader(workspace_id)
                    if any(n.template == "graph_relation_count" for n in plan.nodes) else None)
    node_results, exec_errors, completed, failed = run_plan(
        plan, rows_by_dataset, maximum_runtime_seconds=maximum_runtime_seconds,
        graph_reader=graph_reader)

    kpis_by_id = {k.kpi_id: k for k in spec.kpis}
    kpi_results: list[KpiResult] = []
    for kpi_id, final_node in plan.kpi_final_node.items():
        kpi = kpis_by_id.get(kpi_id)
        result = node_results.get(final_node)
        if kpi is None or result is None:
            continue
        value, numerator, denominator, sample_size, excluded = _kpi_result_from_node(result)
        kpi_results.append(KpiResult(
            kpi_id=kpi_id, value=value, display_value=_display_value(value, kpi.format),
            numerator=numerator, denominator=denominator, sample_size=sample_size,
            excluded_null_rows=excluded,
            lineage=KpiLineage(source_columns=_kpi_source_columns(kpi),
                               operation_ids=plan.kpi_lineage_nodes.get(kpi_id, []),
                               dataset_version=dataset_version_by_id.get(kpi.dataset_id, ""))))

    analyses_by_id = {a.analysis_id: a for a in spec.analyses}
    analysis_results: list[AnalysisResult] = []
    for analysis_id, node_id in plan.analysis_node.items():
        analysis = analyses_by_id.get(analysis_id)
        result = node_results.get(node_id)
        if analysis is None or result is None:
            continue
        rows, unpack_error = _unpack_analysis(analysis, result)
        if unpack_error:
            exec_errors.append(unpack_error)
            logger.warning("analysis unpack mismatch ws=%s analysis=%s op=%s",
                           workspace_id, analysis_id, analysis.operation)
            continue
        analysis_results.append(AnalysisResult(
            analysis_id=analysis_id,
            group_column=analysis.group_by[0] if analysis.group_by else "",
            rows=rows or []))

    status = "completed" if not exec_errors else ("partial" if node_results else "failed")
    run = ExecutionRun(
        execution_run_id=execution_run_id, execution_plan_id=plan.execution_plan_id,
        spec_id=plan.spec_id, dataset_id=dataset_id, dataset_version=plan.dataset_version,
        status=status, kpi_results=kpi_results, analysis_results=analysis_results,
        execution_metrics=ExecutionMetrics(
            runtime_ms=int((time.monotonic() - start) * 1000),
            nodes_completed=completed, nodes_failed=failed),
        errors=exec_errors,
    )

    try:
        report = run_post_execution_validation(dsn, workspace_id, plan, spec, run, row_cap=row_cap)
        run.validation = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — C13 is additive, never blocks the C12 result
        logger.warning("C13 post-execution validation failed ws=%s run=%s",
                       workspace_id, execution_run_id, exc_info=True)

    store = ExecutionRunStore(dsn, workspace_id)
    try:
        store.save(run)
    finally:
        store.close()
    logger.info("analysis_execution ws=%s dataset=%s status=%s kpis=%d analyses=%d validation=%s",
               workspace_id, dataset_id, status, len(kpi_results), len(analysis_results),
               (run.validation or {}).get("status"))
    return run

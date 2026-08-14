"""Independently re-executes a compiled plan for post-execution validation.

Reuses C12's own data-loading + node-execution primitives — same
deterministic algorithm, freshly loaded rows — so a stored ExecutionRun's
reported values get cross-checked against a fresh computation rather than
trusted at face value. This is the mechanism behind check B (aggregation
correctness): recomputing, not re-reading, the answer.
"""
from __future__ import annotations

from aryx.analysis_execution.data import load_typed_rows
from aryx.analysis_execution.execute import resolve_graph_relation_nodes, run_plan
from aryx.andie_planner.models import DashboardSpec
from aryx.execution_compiler.models import ExecutionPlan
from aryx.ports import ports


def recompute(
    dsn: str, workspace_id: int, plan: ExecutionPlan, spec: DashboardSpec, row_cap: int,
) -> tuple[dict[str, object], list[str]]:
    """Return (node_results, errors) from a fresh execution of `plan` — the
    exact same shape `analysis_execution.execute.run_plan` produces, so
    callers can map through `plan.kpi_final_node`/`plan.analysis_node`
    themselves rather than this module guessing at KPI-level semantics."""
    dataset_ids = sorted({n.dataset_id for n in plan.nodes if n.dataset_id})
    rows_by_dataset: dict[str, list] = {}
    for did in dataset_ids:
        rows, _version = load_typed_rows(dsn, workspace_id, did, spec, row_cap)
        rows_by_dataset[did] = rows
    resolve_graph_relation_nodes(dsn, workspace_id, plan)
    graph_reader = (ports().graph_reader(workspace_id)
                    if any(n.template == "graph_relation_count" for n in plan.nodes) else None)
    node_results, errors, _completed, _failed = run_plan(
        plan, rows_by_dataset, graph_reader=graph_reader)
    return node_results, errors

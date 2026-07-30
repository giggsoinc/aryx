"""C11 — Execution Compiler: turn an approved DashboardSpec's KPIs and
analyses into a typed, acyclic execution plan built from vetted operation
templates (templates.py).

No LLM, no arbitrary code generation. The compiler only binds approved
parameters (columns, constants, node references) to a fixed, known set of
templates — never authoring SQL/Python itself. Business-rule validity
(numeric measures, ratio numerator/denominator presence, operation
whitelisting) is already guaranteed by C09 by the time a spec reaches here;
this module is a mechanical binding step plus its own structural self-check
(validate.py) — never a re-litigation of C09's decisions.
"""
from __future__ import annotations

import uuid

from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.models import CompilationIssue, ExecutionNode, ExecutionPlan
from aryx.execution_compiler.templates import (
    GROUPED_NUMERIC_TEMPLATES, NUMERIC_TEMPLATES, RATIO_OPERATIONS,
)
from aryx.execution_compiler.validate import check_resource_limits, is_acyclic, validate_bindings

DEFAULT_ROW_LIMIT = 1_000_000
DEFAULT_NODE_LIMIT = 200

# Compilation issue codes that mean the plan cannot run at all.
_HARD_FAILURE_CODES = frozenset({
    "unknown_template", "parameter_mismatch", "dangling_dependency",
    "duplicate_node_id", "cyclic_dependency", "node_limit_exceeded",
})


def _filter_node(node_id: str, filt: KpiFilter) -> ExecutionNode:
    """Step 2/3: map one KpiFilter to its vetted filter template."""
    if filt.values is not None:
        return ExecutionNode(node_id=node_id, template="filter_in",
                             parameters={"column": filt.column, "values": filt.values})
    return ExecutionNode(node_id=node_id, template="filter_equals",
                         parameters={"column": filt.column, "value": filt.value})


def _compile_operand(kpi_id: str, role: str, operand: KpiOperand | None) -> tuple[list[ExecutionNode], str]:
    """Compile one side (numerator/denominator) of a ratio KPI.

    C09's formula_validity check already guarantees a ratio/percentage KPI
    has both operands, but a component built for defense-in-depth degrades
    to a bare count_rows rather than crashing if one is somehow missing.
    """
    nodes: list[ExecutionNode] = []
    depends_on: list[str] = []
    if operand is not None and operand.filter is not None:
        filt = _filter_node(f"op_{kpi_id}_{role}_filter", operand.filter)
        nodes.append(filt)
        depends_on = [filt.node_id]
    op = operand.operation if operand is not None else "count"
    node_id = f"op_{kpi_id}_{role}_{op}"
    if op in NUMERIC_TEMPLATES:
        nodes.append(ExecutionNode(
            node_id=node_id, template=NUMERIC_TEMPLATES[op],
            parameters={"column": "", "null_policy": "exclude"}, depends_on=depends_on))
    else:
        nodes.append(ExecutionNode(node_id=node_id, template="count_rows",
                                   parameters={}, depends_on=depends_on))
    return nodes, node_id


def _compile_kpi(kpi: Kpi) -> list[ExecutionNode]:
    """Steps 2-4 for one KPI: filter -> measure/count -> (for ratios) safe_ratio."""
    if kpi.operation in RATIO_OPERATIONS:
        num_nodes, num_id = _compile_operand(kpi.kpi_id, "numerator", kpi.numerator)
        den_nodes, den_id = _compile_operand(kpi.kpi_id, "denominator", kpi.denominator)
        ratio_node = ExecutionNode(
            node_id=f"op_{kpi.kpi_id}_ratio", template="safe_ratio",
            parameters={"numerator_ref": num_id, "denominator_ref": den_id,
                       "zero_policy": kpi.zero_denominator_policy or "return_null_with_warning"},
            depends_on=[num_id, den_id],
        )
        return [*num_nodes, *den_nodes, ratio_node]

    nodes: list[ExecutionNode] = []
    depends_on: list[str] = []
    if kpi.filter is not None:
        filt = _filter_node(f"op_{kpi.kpi_id}_filter", kpi.filter)
        nodes.append(filt)
        depends_on = [filt.node_id]

    if kpi.operation in NUMERIC_TEMPLATES:
        nodes.append(ExecutionNode(
            node_id=f"op_{kpi.kpi_id}_{kpi.operation}", template=NUMERIC_TEMPLATES[kpi.operation],
            parameters={"column": kpi.measure or "", "null_policy": "exclude"}, depends_on=depends_on))
    else:
        # "count" and any other whitelisted-but-non-numeric op reduce to a
        # row count over the (optionally filtered) rows.
        nodes.append(ExecutionNode(
            node_id=f"op_{kpi.kpi_id}_count", template="count_rows",
            parameters={}, depends_on=depends_on))
    return nodes


def _operand_status_column(kpi: Kpi) -> str:
    """Best-effort column name a grouped_safe_ratio names as `status_column` —
    the first operand filter's column (e.g. "renewal_status"), for display/
    dry-run metadata only; the template still runs the same filters the
    ungrouped ratio would."""
    for operand in (kpi.numerator, kpi.denominator):
        if operand is not None and operand.filter is not None:
            return operand.filter.column
    return ""


def _compile_analysis(analysis: Analysis, kpis_by_id: dict[str, Kpi]) -> list[ExecutionNode]:
    """Step 4 for one Analysis: a single grouped_* node per group_by + metric.

    Analyses report on an existing KPI (`metric`) rather than declaring their
    own measure/filter — the grouped template re-derives the per-group
    breakdown of that KPI's own operation, so there is no cross-node
    dependency to wire here (unlike a ratio KPI's numerator/denominator).
    """
    group_column = analysis.group_by[0] if analysis.group_by else ""
    node_id = f"op_{analysis.analysis_id}_grouped"
    metric_kpi = kpis_by_id.get(analysis.metric or "")
    if metric_kpi is None:
        return [ExecutionNode(node_id=node_id, template="grouped_count_rows",
                              parameters={"group_column": group_column})]
    if metric_kpi.operation in RATIO_OPERATIONS:
        return [ExecutionNode(
            node_id=node_id, template="grouped_safe_ratio",
            parameters={"group_column": group_column,
                       "status_column": _operand_status_column(metric_kpi)})]
    if metric_kpi.operation in NUMERIC_TEMPLATES:
        return [ExecutionNode(
            node_id=node_id, template=GROUPED_NUMERIC_TEMPLATES[metric_kpi.operation],
            parameters={"group_column": group_column, "column": metric_kpi.measure or "",
                       "null_policy": "exclude"})]
    return [ExecutionNode(node_id=node_id, template="grouped_count_rows",
                          parameters={"group_column": group_column})]


def compile_plan(
    spec_id: str, dataset_id: str, dataset_version: str,
    kpis: list[Kpi], analyses: list[Analysis], *,
    row_limit: int = DEFAULT_ROW_LIMIT, node_limit: int = DEFAULT_NODE_LIMIT,
    dataset_row_count: int | None = None,
) -> ExecutionPlan:
    """Compile one dataset's worth of KPIs/analyses into an ExecutionPlan.

    `kpis`/`analyses` are already scoped to one dataset by the caller (see
    andie_planner.run — single-dataset mode passes the whole spec's lists;
    workspace mode passes only the items whose `dataset_id` matches).
    """
    kpis_by_id = {k.kpi_id: k for k in kpis}
    nodes: list[ExecutionNode] = []
    for kpi in kpis:
        nodes.extend(_compile_kpi(kpi))
    for analysis in analyses:
        nodes.extend(_compile_analysis(analysis, kpis_by_id))

    # Steps 5-7: resource/row limits, template-binding + acyclic self-check.
    issues: list[CompilationIssue] = []
    issues.extend(check_resource_limits(nodes, node_limit))
    issues.extend(validate_bindings(nodes))
    acyclic = is_acyclic(nodes)
    if not acyclic:
        issues.append(CompilationIssue(code="cyclic_dependency",
                                       detail="dependency graph contains a cycle"))

    hard_failed = any(i.code in _HARD_FAILURE_CODES for i in issues)
    status = "rejected" if hard_failed else "success"
    effective_row_limit = row_limit
    if dataset_row_count is not None and dataset_row_count > 0:
        effective_row_limit = min(row_limit, dataset_row_count)

    return ExecutionPlan(
        execution_plan_id=f"execution_plan_{dataset_id}_{uuid.uuid4().hex[:8]}",
        spec_id=spec_id, dataset_id=dataset_id, dataset_version=dataset_version,
        nodes=nodes, plan_acyclic=acyclic, row_limit=effective_row_limit,
        node_limit=node_limit, compilation_status=status, issues=issues,
    )


def compile_plan_for_spec(spec: DashboardSpec, *, dataset_row_count: int | None = None) -> ExecutionPlan:
    """Single-dataset-mode convenience wrapper: compile the WHOLE spec (every
    KPI/analysis) against its one dataset. Workspace mode calls compile_plan
    directly with a per-dataset-filtered kpis/analyses list instead."""
    return compile_plan(spec.spec_id, spec.dataset_id, spec.dataset_version,
                        spec.kpis, spec.analyses, dataset_row_count=dataset_row_count)

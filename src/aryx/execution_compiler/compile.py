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
    GROUPED_2D_NUMERIC_TEMPLATES, GROUPED_HISTOGRAM_TEMPLATES, GROUPED_NUMERIC_TEMPLATES,
    GROUPED_QUARTILE_TEMPLATES, HISTOGRAM_TEMPLATES, NUMERIC_TEMPLATES, QUARTILE_TEMPLATES,
    RATIO_OPERATIONS,
)
from aryx.execution_compiler.validate import (
    check_ratio_operand_operations, check_resource_limits, is_acyclic, validate_bindings,
)

DEFAULT_ROW_LIMIT = 1_000_000
DEFAULT_NODE_LIMIT = 200

# Compilation issue codes that mean the plan cannot run at all.
_HARD_FAILURE_CODES = frozenset({
    "unknown_template", "parameter_mismatch", "dangling_dependency",
    "duplicate_node_id", "cyclic_dependency", "node_limit_exceeded",
    "unsupported_ratio_operand_operation",
})


def _filter_node(node_id: str, dataset_id: str, filt: KpiFilter) -> ExecutionNode:
    """Step 2/3: map one KpiFilter to its vetted filter template."""
    if filt.values is not None:
        return ExecutionNode(node_id=node_id, template="filter_in", dataset_id=dataset_id,
                             parameters={"column": filt.column, "values": filt.values})
    return ExecutionNode(node_id=node_id, template="filter_equals", dataset_id=dataset_id,
                         parameters={"column": filt.column, "value": filt.value})


def _filter_values(filt: KpiFilter | None) -> list:
    """Normalize a KpiFilter to a value list — [] if there is none."""
    if filt is None:
        return []
    if filt.values is not None:
        return list(filt.values)
    return [filt.value]


def _compile_operand(kpi_id: str, dataset_id: str, role: str,
                     operand: KpiOperand | None) -> tuple[list[ExecutionNode], str]:
    """Compile one side (numerator/denominator) of a ratio KPI.

    C09's formula_validity check already guarantees a ratio/percentage KPI
    has both operands, but a component built for defense-in-depth degrades
    to a bare count_rows rather than crashing if one is somehow missing.
    """
    nodes: list[ExecutionNode] = []
    depends_on: list[str] = []
    if operand is not None and operand.filter is not None:
        filt = _filter_node(f"op_{kpi_id}_{role}_filter", dataset_id, operand.filter)
        nodes.append(filt)
        depends_on = [filt.node_id]
    op = operand.operation if operand is not None else "count"
    node_id = f"op_{kpi_id}_{role}_{op}"
    if op in NUMERIC_TEMPLATES:
        nodes.append(ExecutionNode(
            node_id=node_id, template=NUMERIC_TEMPLATES[op], dataset_id=dataset_id,
            parameters={"column": "", "null_policy": "exclude"}, depends_on=depends_on))
    else:
        nodes.append(ExecutionNode(node_id=node_id, template="count_rows", dataset_id=dataset_id,
                                   parameters={}, depends_on=depends_on))
    return nodes, node_id


def _compile_kpi(kpi: Kpi) -> tuple[list[ExecutionNode], str]:
    """Steps 2-4 for one KPI: filter -> measure/count -> (for ratios)
    safe_ratio. Returns (nodes, final_node_id) — the node whose result IS
    this KPI's value."""
    did = kpi.dataset_id
    if kpi.operation in RATIO_OPERATIONS:
        num_nodes, num_id = _compile_operand(kpi.kpi_id, did, "numerator", kpi.numerator)
        den_nodes, den_id = _compile_operand(kpi.kpi_id, did, "denominator", kpi.denominator)
        ratio_id = f"op_{kpi.kpi_id}_ratio"
        ratio_node = ExecutionNode(
            node_id=ratio_id, template="safe_ratio", dataset_id=did,
            parameters={"numerator_ref": num_id, "denominator_ref": den_id,
                       "zero_policy": kpi.zero_denominator_policy or "return_null_with_warning"},
            depends_on=[num_id, den_id],
        )
        return [*num_nodes, *den_nodes, ratio_node], ratio_id

    nodes: list[ExecutionNode] = []
    depends_on: list[str] = []
    if kpi.filter is not None:
        filt = _filter_node(f"op_{kpi.kpi_id}_filter", did, kpi.filter)
        nodes.append(filt)
        depends_on = [filt.node_id]

    if kpi.operation in NUMERIC_TEMPLATES:
        final_id = f"op_{kpi.kpi_id}_{kpi.operation}"
        nodes.append(ExecutionNode(
            node_id=final_id, template=NUMERIC_TEMPLATES[kpi.operation], dataset_id=did,
            parameters={"column": kpi.measure or "", "null_policy": "exclude"}, depends_on=depends_on))
    elif kpi.operation in QUARTILE_TEMPLATES:
        final_id = f"op_{kpi.kpi_id}_{kpi.operation}"
        nodes.append(ExecutionNode(
            node_id=final_id, template=QUARTILE_TEMPLATES[kpi.operation], dataset_id=did,
            parameters={"column": kpi.measure or "", "null_policy": "exclude"}, depends_on=depends_on))
    elif kpi.operation in HISTOGRAM_TEMPLATES:
        final_id = f"op_{kpi.kpi_id}_{kpi.operation}"
        nodes.append(ExecutionNode(
            node_id=final_id, template=HISTOGRAM_TEMPLATES[kpi.operation], dataset_id=did,
            parameters={"column": kpi.measure or "", "null_policy": "exclude"}, depends_on=depends_on))
    else:
        # "count" and any other whitelisted-but-non-numeric op reduce to a
        # row count over the (optionally filtered) rows.
        final_id = f"op_{kpi.kpi_id}_count"
        nodes.append(ExecutionNode(
            node_id=final_id, template="count_rows", dataset_id=did,
            parameters={}, depends_on=depends_on))
    return nodes, final_id


def _operand_status_column(kpi: Kpi) -> str:
    """Best-effort column name a grouped_safe_ratio names as `status_column` —
    the first operand filter's column (e.g. "renewal_status")."""
    for operand in (kpi.numerator, kpi.denominator):
        if operand is not None and operand.filter is not None:
            return operand.filter.column
    return ""


def _compile_analysis(analysis: Analysis, kpis_by_id: dict[str, Kpi]) -> tuple[list[ExecutionNode], str]:
    """Step 4 for one Analysis: a single grouped_* node per group_by + metric.

    Analyses report on an existing KPI (`metric`) rather than declaring their
    own measure/filter — the grouped template re-derives the per-group
    breakdown of that KPI's own operation using the SAME filter values the
    ungrouped KPI would use, so there is no cross-node dependency to wire
    here (unlike a ratio KPI's numerator/denominator).
    """
    did = analysis.dataset_id
    group_column = analysis.group_by[0] if analysis.group_by else ""
    node_id = f"op_{analysis.analysis_id}_grouped"

    # row_points/date_span/survival need no metric_kpi at all — they read
    # their own columns directly off the Analysis, never aggregated through
    # a KPI (there is no single scalar to report; the whole point is the
    # per-row/per-duration shape itself).
    if analysis.operation == "row_points":
        return [ExecutionNode(
            node_id=node_id, template="row_points", dataset_id=did,
            parameters={"label_column": group_column, "x_column": analysis.x_column or "",
                       "y_column": analysis.y_column or "", "size_column": analysis.size_column or ""},
        )], node_id
    if analysis.operation == "date_span":
        return [ExecutionNode(
            node_id=node_id, template="row_date_spans", dataset_id=did,
            parameters={"label_column": group_column, "start_column": analysis.start_column or "",
                       "end_column": analysis.end_column or ""},
        )], node_id
    if analysis.operation == "survival":
        return [ExecutionNode(
            node_id=node_id, template="survival_curve", dataset_id=did,
            parameters={"group_column": group_column, "start_column": analysis.start_column or "",
                       "end_column": analysis.end_column or ""},
        )], node_id

    # graph_relation: no dataset rows involved at all — dataset_id="" so the
    # execution loader never tries to fetch rows for this node; the actual
    # source/relationship/target triple is resolved from graph_path_id at
    # execution time (compile has no DB/graph access), see
    # analysis_execution.execute.resolve_graph_relation_nodes.
    if analysis.operation == "graph_relation":
        return [ExecutionNode(
            node_id=node_id, template="graph_relation_count", dataset_id="",
            parameters={"path_id": analysis.graph_path_id or ""},
        )], node_id

    metric_kpi = kpis_by_id.get(analysis.metric or "")

    # crosstab: group_by has 2 columns — dispatch on the referenced KPI's own
    # operation, same convention as the 1D grouped branches below.
    if analysis.operation == "crosstab" and len(analysis.group_by) >= 2:
        group_column_2 = analysis.group_by[1]
        base_params = {"group_column": group_column, "group_column_2": group_column_2}
        if metric_kpi is not None and metric_kpi.operation in RATIO_OPERATIONS:
            return [ExecutionNode(
                node_id=node_id, template="grouped2d_safe_ratio", dataset_id=did,
                parameters={
                    **base_params, "status_column": _operand_status_column(metric_kpi),
                    "numerator_values": _filter_values(
                        metric_kpi.numerator.filter if metric_kpi.numerator else None),
                    "denominator_values": _filter_values(
                        metric_kpi.denominator.filter if metric_kpi.denominator else None),
                    "zero_policy": metric_kpi.zero_denominator_policy or "return_null_with_warning",
                })], node_id
        if metric_kpi is not None and metric_kpi.operation in GROUPED_2D_NUMERIC_TEMPLATES:
            return [ExecutionNode(
                node_id=node_id, template=GROUPED_2D_NUMERIC_TEMPLATES[metric_kpi.operation],
                dataset_id=did,
                parameters={**base_params, "column": metric_kpi.measure or "", "null_policy": "exclude"},
            )], node_id
        return [ExecutionNode(node_id=node_id, template="grouped2d_count_rows", dataset_id=did,
                              parameters=base_params)], node_id

    # histogram: mirrors quartiles — the KPI carries the measure column, the
    # Analysis carries the (optional) grouping.
    if analysis.operation == "histogram" and metric_kpi is not None \
            and metric_kpi.operation in HISTOGRAM_TEMPLATES:
        if group_column:
            return [ExecutionNode(
                node_id=node_id, template=GROUPED_HISTOGRAM_TEMPLATES[metric_kpi.operation],
                dataset_id=did,
                parameters={"group_column": group_column, "column": metric_kpi.measure or "",
                           "null_policy": "exclude"})], node_id
        return [ExecutionNode(
            node_id=node_id, template="histogram_buckets_numeric", dataset_id=did,
            parameters={"column": metric_kpi.measure or "", "null_policy": "exclude"})], node_id

    if metric_kpi is None:
        return [ExecutionNode(node_id=node_id, template="grouped_count_rows", dataset_id=did,
                              parameters={"group_column": group_column})], node_id
    if metric_kpi.operation in RATIO_OPERATIONS:
        return [ExecutionNode(
            node_id=node_id, template="grouped_safe_ratio", dataset_id=did,
            parameters={
                "group_column": group_column,
                "status_column": _operand_status_column(metric_kpi),
                "numerator_values": _filter_values(
                    metric_kpi.numerator.filter if metric_kpi.numerator else None),
                "denominator_values": _filter_values(
                    metric_kpi.denominator.filter if metric_kpi.denominator else None),
                "zero_policy": metric_kpi.zero_denominator_policy or "return_null_with_warning",
            })], node_id
    if metric_kpi.operation in NUMERIC_TEMPLATES:
        return [ExecutionNode(
            node_id=node_id, template=GROUPED_NUMERIC_TEMPLATES[metric_kpi.operation], dataset_id=did,
            parameters={"group_column": group_column, "column": metric_kpi.measure or "",
                       "null_policy": "exclude"})], node_id
    if metric_kpi.operation in GROUPED_QUARTILE_TEMPLATES:
        return [ExecutionNode(
            node_id=node_id, template=GROUPED_QUARTILE_TEMPLATES[metric_kpi.operation], dataset_id=did,
            parameters={"group_column": group_column, "column": metric_kpi.measure or "",
                       "null_policy": "exclude"})], node_id
    return [ExecutionNode(node_id=node_id, template="grouped_count_rows", dataset_id=did,
                          parameters={"group_column": group_column})], node_id


def compile_plan(
    spec_id: str, dataset_id: str, dataset_version: str,
    kpis: list[Kpi], analyses: list[Analysis], *,
    row_limit: int = DEFAULT_ROW_LIMIT, node_limit: int = DEFAULT_NODE_LIMIT,
    dataset_row_count: int | None = None,
) -> ExecutionPlan:
    """Compile a spec's (or one dataset's scoped subset of) KPIs/analyses
    into an ExecutionPlan. Each node carries its own `dataset_id` (from the
    originating KPI/Analysis), so a single plan can span several datasets —
    see compile_plan_for_spec, the caller andie_planner.run actually uses.
    """
    kpis_by_id = {k.kpi_id: k for k in kpis}
    nodes: list[ExecutionNode] = []
    kpi_final_node: dict[str, str] = {}
    kpi_lineage_nodes: dict[str, list[str]] = {}
    analysis_node: dict[str, str] = {}
    for kpi in kpis:
        kpi_nodes, final_id = _compile_kpi(kpi)
        nodes.extend(kpi_nodes)
        kpi_final_node[kpi.kpi_id] = final_id
        kpi_lineage_nodes[kpi.kpi_id] = [n.node_id for n in kpi_nodes]
    for analysis in analyses:
        an_nodes, an_id = _compile_analysis(analysis, kpis_by_id)
        nodes.extend(an_nodes)
        analysis_node[analysis.analysis_id] = an_id

    # Steps 5-7: resource/row limits, template-binding + acyclic self-check.
    issues: list[CompilationIssue] = []
    issues.extend(check_ratio_operand_operations(kpis))
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
        kpi_final_node=kpi_final_node, kpi_lineage_nodes=kpi_lineage_nodes,
        analysis_node=analysis_node,
    )


def compile_plan_for_spec(spec: DashboardSpec, *, dataset_row_count: int | None = None) -> ExecutionPlan:
    """Compile the WHOLE spec (every KPI/analysis, regardless of how many
    datasets they individually reference) into one plan — the convention
    andie_planner.run uses for both single-dataset and workspace-scope specs."""
    return compile_plan(spec.spec_id, spec.dataset_id, spec.dataset_version,
                        spec.kpis, spec.analyses, dataset_row_count=dataset_row_count)

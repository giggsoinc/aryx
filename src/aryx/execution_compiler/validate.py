"""Steps 5-7 of the Execution Compiler procedure: resource/row limits,
template-binding checks, and acyclic verification for a compiled node list.

Purely structural — never a re-check of C09's business-rule validation
(numeric measures, ratio operand presence, operation whitelisting are
already guaranteed by the time compile.py runs).
"""
from __future__ import annotations

from aryx.andie_planner.models import Analysis, Kpi
from aryx.execution_compiler.models import CompilationIssue, ExecutionNode
from aryx.execution_compiler.templates import (
    HISTOGRAM_TEMPLATES,
    NUMERIC_TEMPLATES,
    RATIO_OPERATIONS,
    TEMPLATES,
)


def validate_bindings(nodes: list[ExecutionNode]) -> list[CompilationIssue]:
    """Every node's template must be a known, vetted one (templates.py) with
    exactly its required parameter keys, a unique node_id, and dependencies
    that resolve to another node in the same plan."""
    issues: list[CompilationIssue] = []
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            issues.append(CompilationIssue(code="duplicate_node_id", node_id=node.node_id))
        seen.add(node.node_id)
        required = TEMPLATES.get(node.template)
        if required is None:
            issues.append(CompilationIssue(code="unknown_template", node_id=node.node_id,
                                           detail=node.template))
            continue
        actual = frozenset(node.parameters.keys())
        if actual != required:
            issues.append(CompilationIssue(
                code="parameter_mismatch", node_id=node.node_id,
                detail=f"template {node.template!r} expects {sorted(required)}, got {sorted(actual)}"))
    for node in nodes:
        for dep in node.depends_on:
            if dep not in seen:
                issues.append(CompilationIssue(code="dangling_dependency", node_id=node.node_id,
                                               detail=dep))
    return issues


def is_acyclic(nodes: list[ExecutionNode]) -> bool:
    """Kahn's algorithm: True iff the dependency graph has no cycle.

    A dependency naming a node_id outside this plan is ignored here (already
    reported as `dangling_dependency` by validate_bindings) so one bad
    reference doesn't also mask the real acyclic/cyclic verdict.
    """
    by_id = {n.node_id: n for n in nodes}
    indegree = {n.node_id: 0 for n in nodes}
    children: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for node in nodes:
        for dep in node.depends_on:
            if dep in by_id:
                children[dep].append(node.node_id)
                indegree[node.node_id] += 1

    queue = [node_id for node_id, deg in indegree.items() if deg == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return visited == len(nodes)


def check_ratio_operand_operations(kpis: list[Kpi]) -> list[CompilationIssue]:
    """A ratio/percentage KPI's numerator/denominator (`KpiOperand`) carries
    no measure/column field — only `operation` + an optional filter. "count"
    binds to count_rows with no column needed, but sum/average/median would
    silently bind to an empty column name (see _compile_operand) and yield a
    fabricated 0.0 instead of a real value or a loud failure. Reject here
    instead."""
    issues: list[CompilationIssue] = []
    for kpi in kpis:
        if kpi.operation not in RATIO_OPERATIONS:
            continue
        for role, operand in (("numerator", kpi.numerator), ("denominator", kpi.denominator)):
            if operand is not None and operand.operation in NUMERIC_TEMPLATES:
                issues.append(CompilationIssue(
                    code="unsupported_ratio_operand_operation", node_id=f"kpi:{kpi.kpi_id}",
                    detail=f"{role} operation {operand.operation!r} has no column to bind — "
                          "only 'count' is supported for ratio operands"))
    return issues


def check_analysis_operation_compilable(
    analyses: list[Analysis], kpis_by_id: dict[str, Kpi],
) -> list[CompilationIssue]:
    """An Analysis's declared `operation` is a PROMISE about the shape of its
    node's result — C12 unpacks strictly on it (analysis_execution.run
    ._analysis_rows dispatches, never shape-sniffs).

    _compile_analysis can only honour that promise for `histogram` when the
    referenced metric KPI is itself a histogram (HISTOGRAM_TEMPLATES is keyed
    by the KPI's operation). Referencing e.g. a `count` KPI makes it fall
    through to the generic grouped path, which emits grouped_count_rows —
    a `{group: int}` result that C12 then tries to read as `{group:
    {"buckets": ...}}`. The node succeeds, so nothing else catches it.

    Reject the mismatch here rather than letting the compiler quietly swap
    the shape out from under the executor.
    """
    issues: list[CompilationIssue] = []
    for analysis in analyses:
        if analysis.operation != "histogram":
            continue
        metric_kpi = kpis_by_id.get(analysis.metric or "")
        if metric_kpi is not None and metric_kpi.operation in HISTOGRAM_TEMPLATES:
            continue
        found = (f"{metric_kpi.operation!r}" if metric_kpi is not None
                 else "no such KPI")
        issues.append(CompilationIssue(
            code="uncompilable_analysis_operation",
            node_id=f"analysis:{analysis.analysis_id}",
            detail=(f"operation 'histogram' needs metric KPI "
                    f"{analysis.metric!r} to be a histogram KPI with a numeric "
                    f"measure, but found {found} — the plan would silently "
                    "compile to a grouped count instead")))
    return issues


def check_resource_limits(nodes: list[ExecutionNode], node_limit: int) -> list[CompilationIssue]:
    """Step 5: reject a plan that would compile more nodes than node_limit —
    an engineering safety cap, not a spec'd number (mirrors C10's THRESHOLD:
    flagged here as adjustable, not authoritative)."""
    if len(nodes) > node_limit:
        return [CompilationIssue(code="node_limit_exceeded",
                                 detail=f"{len(nodes)} nodes exceeds node_limit={node_limit}")]
    return []

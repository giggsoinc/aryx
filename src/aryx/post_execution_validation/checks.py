"""The 7 named C13 checks (A-G in the component spec) — pure, deterministic,
no LLM, no I/O. Each takes the stored ExecutionRun (C12's reported results)
plus context (the approved spec, the compiled plan, a fresh recomputation,
and dataset profiles) and returns (CheckResult, errors, warnings).
"""
from __future__ import annotations

from typing import Any

from aryx.analysis_execution.execute import _kpi_result_from_node
from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.execution_compiler.models import ExecutionPlan
from aryx.post_execution_validation.models import (
    SMALL_SAMPLE_THRESHOLD, CheckResult, ValidationError, ValidationWarning,
)
from aryx.profiler.models import DatasetProfile

_TOLERANCE = 1e-6


def _node_dataset(plan: ExecutionPlan, node_id: str) -> str:
    return next((n.dataset_id for n in plan.nodes if n.node_id == node_id), "")


def check_result_identity(
    spec: DashboardSpec, run: ExecutionRun,
) -> tuple[CheckResult, list[ValidationError], list[ValidationWarning]]:
    """A. Every reported result ID must be one the approved spec actually
    declared — an unexpected ID (invented/hallucinated) is a hard error; an
    expected ID that never got computed is a warning, not an invention."""
    expected_kpi = {k.kpi_id for k in spec.kpis}
    expected_an = {a.analysis_id for a in spec.analyses}
    actual_kpi = {k.kpi_id for k in run.kpi_results}
    actual_an = {a.analysis_id for a in run.analysis_results}

    errors = [ValidationError(code="unexpected_result_id", reference=r)
             for r in sorted((actual_kpi - expected_kpi) | (actual_an - expected_an))]
    warnings = [ValidationWarning(code="missing_result_id", reference=r)
               for r in sorted((expected_kpi - actual_kpi) | (expected_an - actual_an))]
    status = "failed" if errors else "passed"
    return CheckResult(check="result_ids_match_spec", status=status), errors, warnings


def _mismatch(reported: float | None, recomputed: float | None) -> bool:
    if (reported is None) != (recomputed is None):
        return True
    if reported is None:
        return False
    return abs(reported - recomputed) > _TOLERANCE


def check_aggregation_correctness(
    run: ExecutionRun, recomputed_nodes: dict[str, Any], plan: ExecutionPlan,
) -> tuple[CheckResult, list[ValidationError]]:
    """B. Recompute every KPI's value AND every analysis row's value fresh
    and compare — a structurally valid but numerically incorrect result is
    still blocked, regardless of how confident-looking the stored result is.
    Analysis rows get the identical treatment as KPIs here: recompute.py
    already reruns every grouped_* node too, so skipping run.analysis_results
    would leave tampered group breakdowns completely unchecked."""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        node_id = plan.kpi_final_node.get(kpi.kpi_id)
        recomputed_raw = recomputed_nodes.get(node_id) if node_id else None
        if recomputed_raw is None:
            errors.append(ValidationError(
                code="result_formula_mismatch", reference=kpi.kpi_id,
                details={"reported_value": kpi.value, "recomputed_value": None,
                        "explanation_code": "no_recomputed_node"}))
            continue
        recomputed_value, *_ = _kpi_result_from_node(recomputed_raw)
        if _mismatch(kpi.value, recomputed_value):
            errors.append(ValidationError(
                code="result_formula_mismatch", reference=kpi.kpi_id,
                details={"reported_value": kpi.value, "recomputed_value": recomputed_value,
                        "explanation_code": "computed_value_does_not_match_lineage"}))

    for analysis in run.analysis_results:
        node_id = plan.analysis_node.get(analysis.analysis_id)
        recomputed_groups = recomputed_nodes.get(node_id) if node_id else None
        for row in analysis.rows:
            reference = f"{analysis.analysis_id}:{row.group_value}"
            recomputed_raw = (
                recomputed_groups.get(row.group_value)
                if isinstance(recomputed_groups, dict) else None
            )
            if recomputed_raw is None:
                errors.append(ValidationError(
                    code="result_formula_mismatch", reference=reference,
                    details={"reported_value": row.value, "recomputed_value": None,
                            "explanation_code": "no_recomputed_group"}))
                continue
            recomputed_value, *_ = _kpi_result_from_node(recomputed_raw)
            if _mismatch(row.value, recomputed_value):
                errors.append(ValidationError(
                    code="result_formula_mismatch", reference=reference,
                    details={"reported_value": row.value, "recomputed_value": recomputed_value,
                            "explanation_code": "computed_value_does_not_match_lineage"}))
    status = "failed" if errors else "passed"
    return CheckResult(check="aggregation_correctness", status=status), errors


def check_sample_size_reconciliation(
    run: ExecutionRun,
) -> tuple[CheckResult, list[ValidationError]]:
    """C. Internal arithmetic consistency: a ratio's numerator can never
    exceed its denominator, and every count must be non-negative. Applies to
    analysis rows too — AnalysisResultRow carries the identical
    numerator/denominator/sample_size fields KPIs do."""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        if kpi.numerator is not None and kpi.denominator is not None and kpi.numerator > kpi.denominator:
            errors.append(ValidationError(
                code="sample_size_inconsistent", reference=kpi.kpi_id,
                details={"numerator": kpi.numerator, "denominator": kpi.denominator}))
        if kpi.sample_size < 0 or kpi.excluded_null_rows < 0:
            errors.append(ValidationError(
                code="sample_size_inconsistent", reference=kpi.kpi_id,
                details={"sample_size": kpi.sample_size, "excluded_null_rows": kpi.excluded_null_rows}))
    for analysis in run.analysis_results:
        for row in analysis.rows:
            reference = f"{analysis.analysis_id}:{row.group_value}"
            if row.numerator is not None and row.denominator is not None and row.numerator > row.denominator:
                errors.append(ValidationError(
                    code="sample_size_inconsistent", reference=reference,
                    details={"numerator": row.numerator, "denominator": row.denominator}))
            if row.sample_size < 0:
                errors.append(ValidationError(
                    code="sample_size_inconsistent", reference=reference,
                    details={"sample_size": row.sample_size}))
    status = "failed" if errors else "passed"
    return CheckResult(check="sample_size_reconciliation", status=status), errors


def check_evidence_lineage(
    plan: ExecutionPlan, run: ExecutionRun,
) -> tuple[CheckResult, list[ValidationError]]:
    """D. Every result must trace through real, compiled operations — its
    lineage.operation_ids must be exactly the nodes C11 actually compiled
    for that KPI, and its dataset_version must match the plan's."""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        expected_ops = plan.kpi_lineage_nodes.get(kpi.kpi_id, [])
        if not kpi.lineage.operation_ids or set(kpi.lineage.operation_ids) != set(expected_ops):
            errors.append(ValidationError(
                code="lineage_broken", reference=kpi.kpi_id,
                details={"expected_operation_ids": expected_ops,
                        "reported_operation_ids": kpi.lineage.operation_ids}))
        if kpi.lineage.dataset_version and kpi.lineage.dataset_version != run.dataset_version \
                and plan.dataset_id == run.dataset_id:
            # Single-dataset runs: the KPI's own dataset_version must agree
            # with the run's. (Workspace runs span several datasets/versions
            # by design, so this narrower check only applies when they're the same dataset.)
            errors.append(ValidationError(
                code="lineage_broken", reference=kpi.kpi_id,
                details={"reason": "dataset_version_mismatch"}))
    status = "failed" if errors else "passed"
    return CheckResult(check="evidence_lineage", status=status), errors


def check_no_invented_columns(
    plan: ExecutionPlan, run: ExecutionRun, profile_by_dataset: dict[str, DatasetProfile],
) -> tuple[CheckResult, list[ValidationError]]:
    """E (columns). Every lineage source column must be a real column in
    the dataset's own profile — never a name the model invented."""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        node_id = plan.kpi_final_node.get(kpi.kpi_id)
        did = _node_dataset(plan, node_id) if node_id else ""
        profile = profile_by_dataset.get(did)
        if profile is None:
            continue
        real_cols = {c.name for c in profile.columns}
        for col in kpi.lineage.source_columns:
            if col not in real_cols:
                errors.append(ValidationError(
                    code="unknown_column", reference=kpi.kpi_id, details={"column": col}))
    status = "failed" if errors else "passed"
    return CheckResult(check="no_invented_columns", status=status), errors


def check_no_invented_kpis(
    plan: ExecutionPlan, run: ExecutionRun,
) -> tuple[CheckResult, list[ValidationError]]:
    """E (IDs). Every analysis_id/kpi_id the run reports must have a
    corresponding compiled node, i.e. it came from C11's own DAG, never
    fabricated post-hoc. (A row's *group* being traceable to a real
    recomputed group is checked separately, in check_aggregation_correctness
    — a group missing from the recomputation surfaces there as
    "no_recomputed_group".)"""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        if kpi.kpi_id not in plan.kpi_final_node:
            errors.append(ValidationError(code="unapproved_kpi", reference=kpi.kpi_id))
    for analysis in run.analysis_results:
        if analysis.analysis_id not in plan.analysis_node:
            errors.append(ValidationError(code="unapproved_analysis", reference=analysis.analysis_id))
    status = "failed" if errors else "passed"
    return CheckResult(check="no_invented_kpis", status=status), errors


def check_result_shape(run: ExecutionRun) -> tuple[CheckResult, list[ValidationError]]:
    """F. Types must match what the schema promises — a numeric field that
    somehow became a string (data corruption, a stale/incompatible schema)
    fails here even though `"renewal_rate": "low"` would parse as valid JSON."""
    errors: list[ValidationError] = []
    for kpi in run.kpi_results:
        if kpi.value is not None and not isinstance(kpi.value, (int, float)):
            errors.append(ValidationError(code="type_mismatch", reference=kpi.kpi_id,
                                          details={"field": "value"}))
        if not isinstance(kpi.sample_size, int):
            errors.append(ValidationError(code="type_mismatch", reference=kpi.kpi_id,
                                          details={"field": "sample_size"}))
    for analysis in run.analysis_results:
        for row in analysis.rows:
            ref = f"{analysis.analysis_id}:{row.group_value}"
            if not isinstance(row.group_value, str):
                errors.append(ValidationError(code="type_mismatch", reference=ref,
                                              details={"field": "group_value"}))
            if row.value is not None and not isinstance(row.value, (int, float)):
                errors.append(ValidationError(code="type_mismatch", reference=ref,
                                              details={"field": "value"}))
            if not isinstance(row.sample_size, int):
                errors.append(ValidationError(code="type_mismatch", reference=ref,
                                              details={"field": "sample_size"}))
    status = "failed" if errors else "passed"
    return CheckResult(check="result_shape", status=status), errors


def small_sample_warnings(run: ExecutionRun) -> list[ValidationWarning]:
    """G. A valid result on a small sample is still valid — flag it, never reject it."""
    warnings: list[ValidationWarning] = []
    for kpi in run.kpi_results:
        if kpi.sample_size < SMALL_SAMPLE_THRESHOLD:
            warnings.append(ValidationWarning(
                code="small_sample_size", reference=kpi.kpi_id,
                details={"sample_size": kpi.sample_size, "threshold": SMALL_SAMPLE_THRESHOLD}))
    for analysis in run.analysis_results:
        for row in analysis.rows:
            if row.sample_size < SMALL_SAMPLE_THRESHOLD:
                warnings.append(ValidationWarning(
                    code="small_sample_size", reference=f"{analysis.analysis_id}:{row.group_value}",
                    details={"analysis_id": analysis.analysis_id, "group": row.group_value,
                            "sample_size": row.sample_size, "threshold": SMALL_SAMPLE_THRESHOLD}))
    return warnings


def null_exclusion_warnings(run: ExecutionRun) -> list[ValidationWarning]:
    """Every KPI that silently dropped null rows gets a warning — the result
    is still valid, but the exclusion should never be invisible."""
    return [
        ValidationWarning(code="null_values_excluded", reference=kpi.kpi_id,
                          details={"excluded_rows": kpi.excluded_null_rows})
        for kpi in run.kpi_results if kpi.excluded_null_rows > 0
    ]


def null_result_warnings(run: ExecutionRun) -> list[ValidationWarning]:
    """A ratio KPI's `zero_denominator_policy` is only ever authored as
    "return_null_with_warning" in practice — but C12's safe_ratio/
    grouped_safe_ratio only ever did the "return_null" half; nothing
    actually emitted the promised warning. This closes that gap: a `None`
    value (only possible from a zero denominator — sum/average/count always
    produce a real number) always surfaces here, valid but flagged."""
    warnings = [
        ValidationWarning(code="null_result", reference=kpi.kpi_id)
        for kpi in run.kpi_results if kpi.value is None
    ]
    warnings.extend(
        ValidationWarning(code="null_result", reference=f"{analysis.analysis_id}:{row.group_value}")
        for analysis in run.analysis_results for row in analysis.rows if row.value is None
    )
    return warnings

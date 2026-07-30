"""Tests for Post-Execution Validation (C13) — pure, no DB, no LLM.

Builds a real compiled plan (C11) and a real execution run (C12, via
run_plan) rather than mocking either, then exercises checks.py/validate.py
against it — including the doc's own "Key control": a structurally valid
but numerically incorrect result is still blocked.
"""
from __future__ import annotations

from aryx.analysis_execution.execute import _kpi_result_from_node, run_plan
from aryx.analysis_execution.models import (
    AnalysisResult, AnalysisResultRow, ExecutionMetrics, ExecutionRun, KpiLineage, KpiResult,
)
from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.compile import compile_plan
from aryx.post_execution_validation.checks import (
    check_evidence_lineage, check_no_invented_columns,
    check_no_invented_kpis, check_result_identity, check_result_shape,
    check_sample_size_reconciliation, null_exclusion_warnings, small_sample_warnings,
)
from aryx.post_execution_validation.models import SMALL_SAMPLE_THRESHOLD
from aryx.post_execution_validation.validate import validate_execution
from aryx.profiler.models import ColumnProfile, DatasetProfile

DATASET = "dataset_contracts"


def _rows(renewed: int, not_renewed: int, region: str = "North") -> list[dict]:
    rows = [{"contract_id": f"r{i}", "renewal_status": "Renewed", "region": region,
            "contract_value": 100.0} for i in range(renewed)]
    rows += [{"contract_id": f"nr{i}", "renewal_status": "Not Renewed", "region": region,
             "contract_value": None} for i in range(not_renewed)]
    return rows


def _spec_and_plan(kpis: list[Kpi], analyses: list[Analysis] | None = None):
    analyses = analyses or []
    spec = DashboardSpec(spec_id="spec_1", dataset_id=DATASET, dataset_version="v1",
                         kpis=kpis, analyses=analyses)
    plan = compile_plan("spec_1", DATASET, "v1", kpis, analyses)
    return spec, plan


def _renewal_rate_kpi() -> Kpi:
    return Kpi(
        kpi_id="kpi_renewal_rate", dataset_id=DATASET, operation="ratio",
        source_columns=["renewal_status"],
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count",
                             filter=KpiFilter(column="renewal_status", value="Renewed")),
        denominator=KpiOperand(operation="count",
                               filter=KpiFilter(column="renewal_status",
                                                values=["Renewed", "Not Renewed"])),
    )


def _profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_profile_id="profile_1", dataset_id=DATASET, dataset_version="v1",
        row_count=340, column_count=3,
        columns=[
            ColumnProfile(name="renewal_status", original_type="string",
                         canonical_type="categorical", candidate_role="status"),
            ColumnProfile(name="region", original_type="string",
                         canonical_type="categorical", candidate_role="dimension"),
            ColumnProfile(name="contract_value", original_type="number",
                         canonical_type="numeric", candidate_role="measure"),
        ],
    )


def _run_for(spec: DashboardSpec, plan, rows: list[dict]) -> ExecutionRun:
    """Build a real ExecutionRun the same way analysis_execution.run does,
    minus the DB round-trip — reuses the exact same node execution + KPI
    mapping logic (run_plan + _kpi_result_from_node)."""
    node_results, errors, completed, failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    kpis_by_id = {k.kpi_id: k for k in spec.kpis}
    kpi_results = []
    for kpi_id, node_id in plan.kpi_final_node.items():
        kpi = kpis_by_id[kpi_id]
        value, num, den, sample_size, excluded = _kpi_result_from_node(node_results[node_id])
        kpi_results.append(KpiResult(
            kpi_id=kpi_id, value=value, display_value=str(value),
            numerator=num, denominator=den, sample_size=sample_size, excluded_null_rows=excluded,
            lineage=KpiLineage(source_columns=kpi.source_columns,
                               operation_ids=plan.kpi_lineage_nodes[kpi_id], dataset_version="v1")))
    analysis_results = []
    for analysis_id, node_id in plan.analysis_node.items():
        grouped = node_results[node_id]
        rows_out = [
            AnalysisResultRow(group_value=g,
                             value=(v.get("value") if isinstance(v, dict) else float(v)),
                             numerator=(v.get("numerator") if isinstance(v, dict) else None),
                             denominator=(v.get("denominator") if isinstance(v, dict) else None),
                             sample_size=(v.get("sample_size") if isinstance(v, dict) else int(v)))
            for g, v in sorted(grouped.items())
        ]
        analysis_results.append(AnalysisResult(analysis_id=analysis_id, group_column="region",
                                               rows=rows_out))
    return ExecutionRun(
        execution_run_id="execution_1", execution_plan_id=plan.execution_plan_id,
        spec_id=spec.spec_id, dataset_id=DATASET, dataset_version="v1", status="completed",
        kpi_results=kpi_results, analysis_results=analysis_results,
        execution_metrics=ExecutionMetrics(runtime_ms=1, nodes_completed=completed, nodes_failed=failed),
    )


# ── happy path ────────────────────────────────────────────────────────────

def test_correct_run_is_approved_with_warnings_for_small_sample() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=6, not_renewed=9)  # 15 total -> below the 30 threshold
    run = _run_for(spec, plan, rows)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    profile_by_dataset = {DATASET: _profile()}

    report = validate_execution(spec, plan, run, node_results, profile_by_dataset)
    assert report.status == "approved_with_warnings"
    assert report.eligible_for_dashboard is True
    assert all(c.status == "passed" for c in report.checks)
    assert any(w.code == "small_sample_size" for w in report.warnings)


def test_large_sample_with_no_nulls_is_cleanly_approved() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=211, not_renewed=129)  # 340 total, well above threshold
    run = _run_for(spec, plan, rows)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    profile_by_dataset = {DATASET: _profile()}

    report = validate_execution(spec, plan, run, node_results, profile_by_dataset)
    assert report.status == "approved"
    assert report.warnings == []
    assert report.eligible_for_dashboard is True


# ── Key control: wrong arithmetic is blocked even if well-formed ─────────

def test_wrong_reported_value_is_rejected_even_though_well_formed() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=211, not_renewed=129)
    run = _run_for(spec, plan, rows)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    profile_by_dataset = {DATASET: _profile()}

    run.kpi_results[0].value = 0.67  # tamper with an otherwise well-formed result
    report = validate_execution(spec, plan, run, node_results, profile_by_dataset)
    assert report.status == "rejected"
    assert report.eligible_for_dashboard is False
    mismatch = next(e for e in report.errors if e.code == "result_formula_mismatch")
    assert mismatch.details["reported_value"] == 0.67
    assert round(mismatch.details["recomputed_value"], 10) == round(211 / 340, 10)


# ── individual checks ─────────────────────────────────────────────────────

def test_check_result_identity_flags_unexpected_and_missing() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.kpi_results.append(KpiResult(
        kpi_id="kpi_customer_churn_probability", value=0.5, display_value="50%"))
    result, errors, warnings = check_result_identity(spec, run)
    assert result.status == "failed"
    assert any(e.code == "unexpected_result_id" and e.reference == "kpi_customer_churn_probability"
              for e in errors)
    assert warnings == []  # every expected kpi_id (kpi_renewal_rate) IS present


def test_check_no_invented_kpis_flags_result_not_in_plan() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.kpi_results.append(KpiResult(kpi_id="kpi_ghost", value=1.0, display_value="1"))
    result, errors = check_no_invented_kpis(plan, run)
    assert result.status == "failed"
    assert any(e.code == "unapproved_kpi" and e.reference == "kpi_ghost" for e in errors)


def test_check_no_invented_columns_flags_unknown_column() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.kpi_results[0].lineage.source_columns = ["renewal_status", "made_up_column"]
    result, errors = check_no_invented_columns(plan, run, {DATASET: _profile()})
    assert result.status == "failed"
    assert any(e.code == "unknown_column" and e.details["column"] == "made_up_column" for e in errors)


def test_check_evidence_lineage_flags_broken_operation_ids() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.kpi_results[0].lineage.operation_ids = ["op_that_was_never_compiled"]
    result, errors = check_evidence_lineage(plan, run)
    assert result.status == "failed"
    assert any(e.code == "lineage_broken" and e.reference == "kpi_renewal_rate" for e in errors)


def test_check_result_shape_flags_string_value() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.analysis_results.append(AnalysisResult(
        analysis_id="an_region", group_column="region",
        rows=[AnalysisResultRow(group_value="West", value=0.4, sample_size=15)]))
    run.analysis_results[0].rows[0].value = "low"  # bypass the pydantic field type on purpose
    result, errors = check_result_shape(run)
    assert result.status == "failed"
    assert any(e.code == "type_mismatch" and e.details["field"] == "value" for e in errors)


def test_check_sample_size_reconciliation_flags_numerator_over_denominator() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=1, not_renewed=1)
    run = _run_for(spec, plan, rows)
    run.kpi_results[0].numerator = 999  # impossible: exceeds its own denominator
    result, errors = check_sample_size_reconciliation(run)
    assert result.status == "failed"
    assert any(e.code == "sample_size_inconsistent" for e in errors)


def test_small_sample_warning_fires_at_exact_threshold_boundary() -> None:
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=15, not_renewed=15)  # exactly 30 total
    run = _run_for(spec, plan, rows)
    warnings = small_sample_warnings(run)
    assert warnings == []  # 30 is not LESS than the threshold of 30

    rows29 = _rows(renewed=14, not_renewed=15)  # 29 total
    run29 = _run_for(spec, plan, rows29)
    warnings29 = small_sample_warnings(run29)
    assert any(w.code == "small_sample_size" and w.details["sample_size"] == 29 for w in warnings29)
    assert SMALL_SAMPLE_THRESHOLD == 30


def test_null_exclusion_warning_fires_for_excluded_rows() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum", measure="contract_value",
             source_columns=["contract_value"],
             filter=KpiFilter(column="renewal_status", value="Renewed"))
    spec, plan = _spec_and_plan([kpi])
    rows = _rows(renewed=3, not_renewed=1)  # the "Not Renewed" row has a null contract_value,
                                            # but the filter is on renewal_status="Renewed" so
                                            # nothing is actually excluded here; use a null among
                                            # the renewed rows instead:
    rows[0]["contract_value"] = None
    run = _run_for(spec, plan, rows)
    warnings = null_exclusion_warnings(run)
    assert any(w.code == "null_values_excluded" and w.reference == "kpi_value"
              and w.details["excluded_rows"] == 1 for w in warnings)

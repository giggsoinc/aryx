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
from aryx.analysis_execution.run import _analysis_rows
from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.compile import compile_plan
from aryx.post_execution_validation.checks import (
    check_aggregation_correctness, check_evidence_lineage, check_no_invented_columns,
    check_no_invented_kpis, check_result_identity, check_result_shape,
    check_sample_size_reconciliation, null_exclusion_warnings, null_result_warnings,
    small_sample_warnings,
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


def test_wrong_analysis_row_value_is_rejected_not_just_kpis() -> None:
    # Regression: check_aggregation_correctness originally only recomputed
    # run.kpi_results — a tampered analysis (grouped) row sailed through
    # completely unchecked even though recompute.py already reruns the
    # grouped_* nodes too.
    kpi = _renewal_rate_kpi()
    analysis = Analysis(analysis_id="an_region", operation="group_by", dataset_id=DATASET,
                       group_by=["region"], metric="kpi_renewal_rate")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = _rows(renewed=6, not_renewed=9, region="West")
    run = _run_for(spec, plan, rows)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    profile_by_dataset = {DATASET: _profile()}

    run.analysis_results[0].rows[0].value = 0.99  # tamper the grouped value, not the KPI
    report = validate_execution(spec, plan, run, node_results, profile_by_dataset)
    assert report.status == "rejected"
    mismatch = next(e for e in report.errors if e.code == "result_formula_mismatch"
                    and e.reference == "an_region:West")
    assert mismatch.details["reported_value"] == 0.99
    assert round(mismatch.details["recomputed_value"], 4) == round(6 / 15, 4)


def test_wrong_analysis_row_q1_is_rejected_not_just_the_median() -> None:
    # Regression: a box-plot row's min/q1/q3/max live outside the single
    # "value"/median slot check_aggregation_correctness already recomputes —
    # a tampered q1 must not sail through just because the median matches.
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="quartiles",
             source_columns=["deal_value"], measure="deal_value")
    analysis = Analysis(analysis_id="an_deal_size", operation="group_by", dataset_id=DATASET,
                       group_by=["region"], metric="kpi_deal_size")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = [{"contract_id": f"w{i}", "region": "West", "deal_value": v}
           for i, v in enumerate([100.0, 200.0, 300.0])]
    run = _run_for(spec, plan, rows)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    profile_by_dataset = {DATASET: _profile()}

    run.analysis_results[0].rows[0].q1 = 999.0  # tamper q1 only, leave median (value) correct
    report = validate_execution(spec, plan, run, node_results, profile_by_dataset)
    assert report.status == "rejected"
    mismatch = next(e for e in report.errors if e.code == "result_formula_mismatch"
                    and e.reference == "an_deal_size:West:q1")
    assert mismatch.details["reported_value"] == 999.0
    assert mismatch.details["recomputed_value"] == 150.0


# ── new chart-type shapes (crosstab/row_points/date_span/survival/histogram) ──
# Regression: check_aggregation_correctness's recompute-and-compare lookup
# originally assumed every analysis result is a flat group_value-keyed dict
# — crosstab (tuple-keyed), row_points/date_span (lists), and survival
# (dict of lists) all failed with a spurious "no_recomputed_group" even when
# the reported values were exactly correct, blocking every new chart type
# from ever reaching composition.

def _analysis_run(spec: DashboardSpec, plan, rows: list[dict], analysis: Analysis) -> ExecutionRun:
    node_results, errors, completed, failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    node_id = plan.analysis_node[analysis.analysis_id]
    result = AnalysisResult(analysis_id=analysis.analysis_id,
                            group_column=analysis.group_by[0] if analysis.group_by else "",
                            rows=_analysis_rows(analysis, node_results[node_id]))
    return ExecutionRun(
        execution_run_id="execution_1", execution_plan_id=plan.execution_plan_id,
        spec_id=spec.spec_id, dataset_id=DATASET, dataset_version="v1", status="completed",
        analysis_results=[result],
        execution_metrics=ExecutionMetrics(runtime_ms=1, nodes_completed=completed, nodes_failed=failed),
    )


def test_crosstab_row_matches_recompute_not_falsely_rejected() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="an_flow", operation="crosstab", dataset_id=DATASET,
                       group_by=["region", "renewal_status"], metric="kpi_value")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = _rows(renewed=3, not_renewed=2, region="West")
    run = _analysis_run(spec, plan, rows, analysis)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", errors


def test_crosstab_row_tampered_is_still_caught() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="an_flow", operation="crosstab", dataset_id=DATASET,
                       group_by=["region", "renewal_status"], metric="kpi_value")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = _rows(renewed=3, not_renewed=2, region="West")
    run = _analysis_run(spec, plan, rows, analysis)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    run.analysis_results[0].rows[0].value = 99999.0  # tamper
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "failed"
    assert any(e.code == "result_formula_mismatch"
              and e.details["explanation_code"] == "computed_value_does_not_match_lineage"
              for e in errors)


def test_row_points_matches_recompute_not_falsely_rejected() -> None:
    analysis = Analysis(analysis_id="an_scatter", operation="row_points", dataset_id=DATASET,
                       group_by=["contract_id"], x_column="contract_value", y_column="contract_value")
    spec, plan = _spec_and_plan([], [analysis])
    rows = _rows(renewed=3, not_renewed=0, region="West")
    run = _analysis_run(spec, plan, rows, analysis)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", errors


def test_date_span_matches_recompute_not_falsely_rejected() -> None:
    analysis = Analysis(analysis_id="an_gantt", operation="date_span", dataset_id=DATASET,
                       group_by=["contract_id"], start_column="region", end_column="renewal_status")
    spec, plan = _spec_and_plan([], [analysis])
    rows = _rows(renewed=2, not_renewed=0, region="West")
    run = _analysis_run(spec, plan, rows, analysis)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", errors


def test_survival_matches_recompute_not_falsely_rejected() -> None:
    rows = [
        {"contract_id": "c1", "signup": "2024-01-01", "churn": "2024-01-11"},
        {"contract_id": "c2", "signup": "2024-01-01", "churn": None},
        {"contract_id": "c3", "signup": "2024-01-01", "churn": "2024-01-06"},
    ]
    analysis = Analysis(analysis_id="an_survival", operation="survival", dataset_id=DATASET,
                       start_column="signup", end_column="churn")
    spec, plan = _spec_and_plan([], [analysis])
    node_results, errors, _c, _f = run_plan(plan, {DATASET: rows})
    assert errors == []
    node_id = plan.analysis_node["an_survival"]
    result_rows = _analysis_rows(analysis, node_results[node_id])
    run = ExecutionRun(
        execution_run_id="execution_1", execution_plan_id=plan.execution_plan_id,
        spec_id=spec.spec_id, dataset_id=DATASET, dataset_version="v1", status="completed",
        analysis_results=[AnalysisResult(analysis_id="an_survival", group_column="", rows=result_rows)],
        execution_metrics=ExecutionMetrics(runtime_ms=1, nodes_completed=_c, nodes_failed=_f),
    )
    result, check_errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", check_errors


def test_ungrouped_histogram_matches_recompute_not_falsely_rejected() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="histogram", measure="deal_value")
    analysis = Analysis(analysis_id="an_hist", operation="histogram", dataset_id=DATASET, metric="kpi_deal_size")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = [{"contract_id": f"d{i}", "deal_value": v} for i, v in enumerate([100.0, 200.0, 300.0])]
    run = _analysis_run(spec, plan, rows, analysis)
    node_results, _errors, _c, _f = run_plan(plan, {DATASET: rows})
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", errors


class _FakeGraphReader:
    """Minimal double for GraphReaderPort — only count_by_relationship is used."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def count_by_relationship(self, source_type, relationship, target_type, direction="out"):
        return dict(self._counts)


def _graph_relation_run(counts: dict[str, int]):
    analysis = Analysis(analysis_id="an_by_manager", operation="graph_relation",
                       dataset_id="", graph_path_id="path_contract_manager")
    spec, plan = _spec_and_plan([], [analysis])
    for node in plan.nodes:  # resolve_graph_relation_nodes's job, done by hand here
        if node.template == "graph_relation_count":
            node.parameters = {**node.parameters, "source_type": "Contract",
                               "relationship": "MANAGED_BY", "target_type": "Manager",
                               "direction": "out"}
    reader = _FakeGraphReader(counts)
    node_results, errors, _c, _f = run_plan(plan, {}, graph_reader=reader)
    assert errors == []
    node_id = plan.analysis_node["an_by_manager"]
    result_rows = _analysis_rows(analysis, node_results[node_id])
    run = ExecutionRun(
        execution_run_id="execution_1", execution_plan_id=plan.execution_plan_id,
        spec_id=spec.spec_id, dataset_id="workspace_1", dataset_version="v1", status="completed",
        analysis_results=[AnalysisResult(analysis_id="an_by_manager", group_column="", rows=result_rows)],
        execution_metrics=ExecutionMetrics(runtime_ms=1, nodes_completed=_c, nodes_failed=_f),
    )
    return spec, plan, run, node_results


def test_graph_relation_matches_recompute_not_falsely_rejected() -> None:
    # graph_relation's dict[str, int] result reuses the same default 1D
    # grouped-row check every ungrouped/1D operation already gets — no
    # dedicated branch needed, proven here the same way crosstab/histogram
    # proved theirs above.
    spec, plan, run, node_results = _graph_relation_run({"Jane Doe": 3, "Sam Lee": 1})
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "passed", errors


def test_graph_relation_tampered_is_still_caught() -> None:
    spec, plan, run, node_results = _graph_relation_run({"Jane Doe": 3, "Sam Lee": 1})
    run.analysis_results[0].rows[0].value = 99999.0  # tamper
    result, errors = check_aggregation_correctness(spec, run, node_results, plan)
    assert result.status == "failed"
    assert any(e.code == "result_formula_mismatch"
              and e.details["explanation_code"] == "computed_value_does_not_match_lineage"
              for e in errors)


def test_impossible_analysis_row_numerator_is_rejected() -> None:
    kpi = _renewal_rate_kpi()
    analysis = Analysis(analysis_id="an_region", operation="group_by", dataset_id=DATASET,
                       group_by=["region"], metric="kpi_renewal_rate")
    spec, plan = _spec_and_plan([kpi], [analysis])
    rows = _rows(renewed=6, not_renewed=9, region="West")
    run = _run_for(spec, plan, rows)
    run.analysis_results[0].rows[0].numerator = 999  # exceeds its own denominator
    result, errors = check_sample_size_reconciliation(run)
    assert result.status == "failed"
    assert any(e.code == "sample_size_inconsistent" and e.reference == "an_region:West"
              for e in errors)


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


def test_null_result_warning_fires_for_zero_denominator() -> None:
    # zero_denominator_policy is only ever authored as
    # "return_null_with_warning" — this closes the "with warning" half,
    # which C12 alone never fulfilled (it only ever did the "return_null" part).
    kpi = _renewal_rate_kpi()
    spec, plan = _spec_and_plan([kpi])
    run = _run_for(spec, plan, [])  # no rows at all -> denominator is 0
    assert run.kpi_results[0].value is None
    warnings = null_result_warnings(run)
    assert any(w.code == "null_result" and w.reference == "kpi_renewal_rate" for w in warnings)

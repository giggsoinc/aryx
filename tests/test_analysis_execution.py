"""Tests for Deterministic Analysis Execution (C12) — pure, no DB, no LLM.

Executes real ExecutionPlans (compiled by C11, exercised for real here) against
small in-memory row sets — no mocking of compile.py's output, so a C11
regression that breaks node shapes would also break these tests.
"""
from __future__ import annotations

from aryx.analysis_execution.execute import run_plan
from aryx.analysis_execution.run import _display_value, _kpi_result_from_node, _kpi_source_columns
from aryx.andie_planner.models import Analysis, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.compile import compile_plan

DATASET = "dataset_contracts"


def _rows(renewed: int, not_renewed: int, region: str = "North") -> list[dict]:
    rows = [{"contract_id": f"r{i}", "renewal_status": "Renewed", "region": region,
            "contract_value": 100.0} for i in range(renewed)]
    rows += [{"contract_id": f"nr{i}", "renewal_status": "Not Renewed", "region": region,
             "contract_value": None} for i in range(not_renewed)]
    return rows


def _renewal_rate_kpi() -> Kpi:
    return Kpi(
        kpi_id="kpi_renewal_rate", dataset_id=DATASET, operation="ratio",
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count",
                             filter=KpiFilter(column="renewal_status", value="Renewed")),
        denominator=KpiOperand(operation="count",
                               filter=KpiFilter(column="renewal_status",
                                                values=["Renewed", "Not Renewed"])),
    )


# ── ratio KPI, matches the C12 spec doc's worked example ─────────────────

def test_renewal_rate_matches_spec_doc_worked_example() -> None:
    # 211 Renewed / 340 Completed = 62.06%, per the component doc.
    rows = _rows(renewed=211, not_renewed=129)
    kpi = _renewal_rate_kpi()
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, completed, failed = run_plan(plan, {DATASET: rows})
    assert errors == [] and failed == 0 and completed == len(plan.nodes)

    ratio_result = results[plan.kpi_final_node["kpi_renewal_rate"]]
    assert ratio_result["numerator"] == 211
    assert ratio_result["denominator"] == 340
    assert round(ratio_result["value"], 10) == round(211 / 340, 10)

    value, num, den, sample_size, excluded = _kpi_result_from_node(kpi, ratio_result)
    assert (num, den, sample_size, excluded) == (211, 340, 340, 0)
    assert _display_value(value, "percentage") == "62.06%"


def test_sum_kpi_excludes_nulls_and_formats_currency() -> None:
    rows = _rows(renewed=3, not_renewed=1)  # the 1 "Not Renewed" row has a null contract_value
    kpi = Kpi(kpi_id="kpi_renewed_value", dataset_id=DATASET, operation="sum",
             measure="contract_value",
             filter=KpiFilter(column="renewal_status", value="Renewed"))
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    sum_result = results[plan.kpi_final_node["kpi_renewed_value"]]
    value, num, den, sample_size, excluded = _kpi_result_from_node(kpi, sum_result)
    assert value == 300.0  # 3 renewed rows * 100.0
    assert sample_size == 3 and excluded == 0
    assert num is None and den is None
    assert _display_value(value, "currency") == "$300"


def test_count_kpi_has_no_ratio_fields() -> None:
    rows = _rows(renewed=2, not_renewed=5)
    kpi = Kpi(kpi_id="kpi_all", dataset_id=DATASET, operation="count")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    count_result = results[plan.kpi_final_node["kpi_all"]]
    value, num, den, sample_size, excluded = _kpi_result_from_node(kpi, count_result)
    assert value == 7.0 and sample_size == 7 and num is None and den is None


# ── grouped analysis ──────────────────────────────────────────────────────

def test_grouped_safe_ratio_breaks_down_by_region() -> None:
    rows = _rows(renewed=6, not_renewed=9, region="West") + _rows(renewed=45, not_renewed=35, region="South")
    kpi = _renewal_rate_kpi()
    analysis = Analysis(analysis_id="analysis_by_region", operation="group_by",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_renewal_rate")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["analysis_by_region"]]
    assert grouped["West"] == {"numerator": 6, "denominator": 15, "value": 0.4, "sample_size": 15}
    south = grouped["South"]
    assert south["numerator"] == 45 and south["denominator"] == 80
    assert round(south["value"], 4) == round(45 / 80, 4)


def test_grouped_sum_numeric_by_region() -> None:
    rows = _rows(renewed=2, not_renewed=0, region="East") + _rows(renewed=3, not_renewed=0, region="West")
    kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="analysis_value_by_region", operation="group_by",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_value")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["analysis_value_by_region"]]
    assert grouped["East"] == {"value": 200.0, "sample_size": 2}
    assert grouped["West"] == {"value": 300.0, "sample_size": 3}


# ── controlled degradation ────────────────────────────────────────────────

def test_zero_denominator_returns_none_value_not_a_crash() -> None:
    rows: list[dict] = []  # no rows at all -> denominator is 0
    kpi = _renewal_rate_kpi()
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, failed = run_plan(plan, {DATASET: rows})
    assert errors == [] and failed == 0
    ratio_result = results[plan.kpi_final_node["kpi_renewal_rate"]]
    assert ratio_result == {"numerator": 0, "denominator": 0, "value": None}
    value, *_ = _kpi_result_from_node(kpi, ratio_result)
    assert _display_value(value, "percentage") == "—"


def test_unknown_dataset_rows_degrade_to_empty_not_a_crash() -> None:
    kpi = Kpi(kpi_id="kpi_all", dataset_id=DATASET, operation="count")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, completed, failed = run_plan(plan, {})  # dataset never loaded
    assert errors == [] and failed == 0 and completed == 1
    assert results[plan.kpi_final_node["kpi_all"]] == 0


def test_maximum_runtime_seconds_stops_execution_gracefully() -> None:
    kpi = Kpi(kpi_id="kpi_all", dataset_id=DATASET, operation="count")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, failed = run_plan(
        plan, {DATASET: _rows(1, 1)}, maximum_runtime_seconds=-1)
    assert failed == len(plan.nodes)
    assert any("maximum_runtime_seconds exceeded" in e for e in errors)
    assert results == {}


# ── lineage / display helpers ─────────────────────────────────────────────

def test_kpi_source_columns_collects_every_bound_column() -> None:
    # Numerator and denominator both filter on renewal_status — deduped, not repeated.
    assert _kpi_source_columns(_renewal_rate_kpi()) == ["renewal_status"]

    sum_kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum",
                 measure="contract_value", source_columns=["contract_id"],
                 filter=KpiFilter(column="renewal_status", value="Renewed"))
    assert _kpi_source_columns(sum_kpi) == ["contract_id", "contract_value", "renewal_status"]


def test_display_value_number_formatting() -> None:
    assert _display_value(1234.0, "number") == "1,234"
    assert _display_value(1234.5, "number") == "1,234.50"
    assert _display_value(None, "number") == "—"

"""Tests for Deterministic Analysis Execution (C12) — pure, no DB, no LLM.

Executes real ExecutionPlans (compiled by C11, exercised for real here) against
small in-memory row sets — no mocking of compile.py's output, so a C11
regression that breaks node shapes would also break these tests.
"""
from __future__ import annotations

from aryx.analysis_execution import execute as execute_module
from datetime import datetime

from aryx.analysis_execution.execute import (
    _histogram_buckets, _kpi_result_from_node, _loose_equals, _loose_in, _survival_curve,
    resolve_graph_relation_nodes, run_plan,
)
from aryx.analysis_execution.run import _analysis_rows, _display_value, _kpi_source_columns
from aryx.andie_planner.models import Analysis, BucketDef, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.compile import compile_plan
from aryx.graph_profiler.models import GraphProfile, VerifiedPath

DATASET = "dataset_contracts"


# ── filter/ratio type coercion — real bug found this session ─────────────
#
# C10 (aryx.preprocess.transform, via load_typed_rows) converts a
# boolean/numeric/date column's raw CSV strings into a real Python
# bool/float/datetime before C12 ever runs. The planner, meanwhile, always
# writes filter values as bare strings (copied verbatim from a column's
# string sample_values). Plain `==`/`in` then silently matches ZERO rows for
# every filter on a boolean/numeric/date column — e.g. is_at_risk="1" against
# a row whose typed value is Python True — a wrong ZERO that looks like a
# real, legitimate result rather than a loud failure. Caught live: a
# named_buckets "Revenue at Risk by Lapsed Time" chart, correctly specified
# end to end, rendered every bucket at exactly zero.

def test_loose_equals_matches_boolean_row_value_against_string_filter() -> None:
    assert _loose_equals(True, "1") is True
    assert _loose_equals(True, "true") is True
    assert _loose_equals(False, "0") is True
    assert _loose_equals(False, "no") is True
    assert _loose_equals(True, "0") is False


def test_loose_equals_matches_numeric_row_value_against_string_filter() -> None:
    assert _loose_equals(1.0, "1") is True
    assert _loose_equals(42.0, "42") is True
    assert _loose_equals(1.0, "2") is False


def test_loose_equals_matches_datetime_row_value_against_iso_string_filter() -> None:
    assert _loose_equals(datetime(2024, 1, 15), "2024-01-15") is True
    assert _loose_equals(datetime(2024, 1, 15), "2024-01-16") is False


def test_loose_equals_still_matches_plain_strings_exactly() -> None:
    assert _loose_equals("DRAFT", "DRAFT") is True
    assert _loose_equals("DRAFT", "draft") is False  # never case-fold real categoricals


def test_loose_in_checks_every_candidate() -> None:
    assert _loose_in(True, ["0", "1"]) is True
    assert _loose_in(False, ["1"]) is False
    assert _loose_in("ACTIVE", []) is False


def test_filter_equals_on_a_boolean_typed_column_matches_real_rows() -> None:
    # is_at_risk stored as Python bool (post C10 conversion), filter value
    # a bare string "1" — this used to match zero rows.
    rows = [{"is_at_risk": True, "estimated_amount": 100.0},
           {"is_at_risk": False, "estimated_amount": 999.0},
           {"is_at_risk": True, "estimated_amount": 50.0}]
    kpi = Kpi(kpi_id="kpi_at_risk", dataset_id=DATASET, operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="is_at_risk", value="1"))
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    result = results[f"op_{kpi.kpi_id}_sum"]
    assert result["value"] == 150.0 and result["sample_size"] == 2


def test_filter_equals_on_a_numeric_typed_column_matches_real_rows() -> None:
    rows = [{"account_number": 10074303.0, "estimated_amount": 100.0},
           {"account_number": 20000000.0, "estimated_amount": 999.0}]
    kpi = Kpi(kpi_id="kpi_one_account", dataset_id=DATASET, operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="account_number", value="10074303"))
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    assert results[f"op_{kpi.kpi_id}_sum"]["value"] == 100.0


def test_grouped_safe_ratio_status_column_boolean_typed_matches_real_rows() -> None:
    # kpi_renewal_rate-shaped ratio whose status_column (is_renewed) is
    # boolean-typed post-C10 — grouped by region, both operands filtered.
    rows = [
        {"is_renewed": True, "region": "North"}, {"is_renewed": True, "region": "North"},
        {"is_renewed": False, "region": "North"},
        {"is_renewed": True, "region": "South"}, {"is_renewed": False, "region": "South"},
    ]
    kpi = Kpi(
        kpi_id="kpi_renewal_rate", dataset_id=DATASET, operation="ratio",
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count", filter=KpiFilter(column="is_renewed", value="1")),
        denominator=KpiOperand(operation="count",
                               filter=KpiFilter(column="is_renewed", values=["1", "0"])),
    )
    analysis = Analysis(analysis_id="an_renewal_by_region", operation="group_by",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_renewal_rate")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    result = results[plan.analysis_node["an_renewal_by_region"]]
    assert result["North"]["numerator"] == 2 and result["North"]["denominator"] == 3
    assert result["South"]["numerator"] == 1 and result["South"]["denominator"] == 2


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

    value, num, den, sample_size, excluded = _kpi_result_from_node(ratio_result)
    assert (num, den, sample_size, excluded) == (211, 340, 340, 0)
    assert _display_value(value, "percentage") == "62.06%"


def test_ratio_kpi_with_top_level_filter_never_exceeds_100_percent() -> None:
    # Regression, found live: "Manual Renewal Rate" = ratio(is_renewed=1)
    # scoped by a top-level filter renewal_type=MANUAL. Before the fix, the
    # numerator ignored the MANUAL scoping entirely and counted every
    # renewed row in the whole dataset (AUTO included) — against a
    # denominator correctly scoped to MANUAL-only rows — producing a
    # mathematically impossible rate above 1.0 (100%).
    rows = [
        {"renewal_type": "MANUAL", "is_renewed": True},
        {"renewal_type": "MANUAL", "is_renewed": False},
        {"renewal_type": "MANUAL", "is_renewed": False},
        {"renewal_type": "AUTO", "is_renewed": True},
        {"renewal_type": "AUTO", "is_renewed": True},
        {"renewal_type": "AUTO", "is_renewed": True},
    ]
    kpi = Kpi(
        kpi_id="kpi_manual_rate", dataset_id=DATASET, operation="ratio",
        filter=KpiFilter(column="renewal_type", value="MANUAL"),
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count", filter=KpiFilter(column="is_renewed", value="1")),
        denominator=KpiOperand(operation="count"),
    )
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    ratio_result = results[plan.kpi_final_node["kpi_manual_rate"]]
    # 1 renewed MANUAL row / 3 total MANUAL rows — AUTO rows must not leak in.
    assert ratio_result["numerator"] == 1
    assert ratio_result["denominator"] == 3
    assert ratio_result["value"] <= 1.0
    assert round(ratio_result["value"], 4) == round(1 / 3, 4)


def test_sum_kpi_excludes_nulls_and_formats_currency() -> None:
    rows = _rows(renewed=3, not_renewed=1)  # the 1 "Not Renewed" row has a null contract_value
    kpi = Kpi(kpi_id="kpi_renewed_value", dataset_id=DATASET, operation="sum",
             measure="contract_value",
             filter=KpiFilter(column="renewal_status", value="Renewed"))
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    sum_result = results[plan.kpi_final_node["kpi_renewed_value"]]
    value, num, den, sample_size, excluded = _kpi_result_from_node(sum_result)
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
    value, num, den, sample_size, excluded = _kpi_result_from_node(count_result)
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


def test_grouped_safe_ratio_keeps_a_group_with_only_numerator_hits() -> None:
    # Regression: a group whose rows only ever matched numerator_values (and
    # never denominator_values — disjoint filter sets are structurally
    # valid) used to vanish from the output entirely instead of appearing
    # with denominator=0.
    rows = [
        {"deal_id": "d1", "outcome": "Won", "region": "West"},
        {"deal_id": "d2", "outcome": "Won", "region": "West"},
        {"deal_id": "d3", "outcome": "Lost", "region": "East"},
    ]
    kpi = Kpi(
        kpi_id="kpi_win_loss", dataset_id=DATASET, operation="ratio",
        numerator=KpiOperand(operation="count", filter=KpiFilter(column="outcome", value="Won")),
        denominator=KpiOperand(operation="count", filter=KpiFilter(column="outcome", value="Lost")),
    )
    analysis = Analysis(analysis_id="an_win_loss", operation="group_by",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_win_loss")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["an_win_loss"]]
    assert grouped["West"] == {"numerator": 2, "denominator": 0, "value": None, "sample_size": 0}
    assert grouped["East"] == {"numerator": 0, "denominator": 1, "value": 0.0, "sample_size": 1}


def test_grouped_safe_ratio_with_an_unfiltered_denominator_counts_every_row() -> None:
    # Regression, found live building a real dashboard: the single most
    # natural way to define a rate KPI — numerator "is_renewed=1",
    # denominator a bare unfiltered count (exactly the component doc's own
    # worked example) — reported denominator=0 for EVERY group the moment
    # it was charted grouped by anything. An empty denominator_values list
    # (compile._filter_values(None) == []) was read as "matches no row"
    # instead of "no filter was declared, matches every row".
    rows = [
        {"line_description": "Plan A", "is_renewed": "1"},
        {"line_description": "Plan A", "is_renewed": "0"},
        {"line_description": "Plan A", "is_renewed": "0"},
        {"line_description": "Plan B", "is_renewed": "1"},
        {"line_description": "Plan B", "is_renewed": "1"},
    ]
    kpi = Kpi(
        kpi_id="kpi_line_renewal_rate", dataset_id=DATASET, operation="ratio",
        numerator=KpiOperand(operation="count", filter=KpiFilter(column="is_renewed", value="1")),
        denominator=KpiOperand(operation="count"),  # no filter at all
    )
    analysis = Analysis(analysis_id="an_low_renewal_products", operation="group_by",
                        dataset_id=DATASET, group_by=["line_description"], metric="kpi_line_renewal_rate")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["an_low_renewal_products"]]
    assert grouped["Plan A"] == {"numerator": 1, "denominator": 3, "value": 1 / 3,
                                 "sample_size": 3}
    assert grouped["Plan B"] == {"numerator": 2, "denominator": 2, "value": 1.0, "sample_size": 2}


def test_quartiles_kpi_computes_min_q1_median_q3_max() -> None:
    rows = [{"deal_id": f"d{i}", "deal_value": v} for i, v in enumerate(
        [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0])]
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="quartiles", measure="deal_value")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    node_result = results[plan.kpi_final_node["kpi_deal_size"]]
    assert node_result == {"min": 100.0, "q1": 300.0, "median": 500.0, "q3": 700.0,
                           "max": 900.0, "sample_size": 9, "excluded_null_rows": 0}
    value, num, den, sample_size, excluded = _kpi_result_from_node(node_result)
    assert value == 500.0  # median stands in as "value", same convention as ratio's numerator/denominator
    assert (num, den, sample_size, excluded) == (None, None, 9, 0)


def test_grouped_quartiles_numeric_by_region() -> None:
    rows = (
        [{"deal_id": f"w{i}", "deal_value": v, "region": "West"} for i, v in enumerate([100.0, 200.0, 300.0])]
        + [{"deal_id": f"e{i}", "deal_value": v, "region": "East"} for i, v in enumerate([10.0, 20.0, 30.0])]
    )
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="quartiles", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_deal_size_by_region", operation="group_by",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_deal_size")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["analysis_deal_size_by_region"]]
    assert grouped["West"] == {"min": 100.0, "q1": 150.0, "median": 200.0, "q3": 250.0,
                               "max": 300.0, "sample_size": 3}
    assert grouped["East"] == {"min": 10.0, "q1": 15.0, "median": 20.0, "q3": 25.0,
                               "max": 30.0, "sample_size": 3}


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


def test_grouped_sum_numeric_honors_the_metric_kpis_own_filter() -> None:
    # Regression, found while building four tab-focused MSI_SRM dashboards:
    # a filtered "sum" KPI (e.g. revenue at risk, WHERE is_at_risk=1) grouped
    # by anything used to silently sum EVERY row, not just the filtered
    # subset — a wrong total that looks like a real, legitimate result.
    rows = [
        {"contract_type": "SERVICE", "is_at_risk": True, "estimated_amount": 100.0},
        {"contract_type": "SERVICE", "is_at_risk": False, "estimated_amount": 999.0},
        {"contract_type": "SUBSCRIPTION", "is_at_risk": True, "estimated_amount": 50.0},
    ]
    kpi = Kpi(kpi_id="kpi_at_risk_value", dataset_id=DATASET, operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="is_at_risk", value="1"))
    analysis = Analysis(analysis_id="an_risk_by_type", operation="group_by",
                        dataset_id=DATASET, group_by=["contract_type"], metric="kpi_at_risk_value")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["an_risk_by_type"]]
    assert grouped == {
        "SERVICE": {"value": 100.0, "sample_size": 1},
        "SUBSCRIPTION": {"value": 50.0, "sample_size": 1},
    }


def test_grouped_count_rows_honors_the_metric_kpis_own_filter() -> None:
    rows = [
        {"line_type": "SERVICE", "non_standard_duration": True},
        {"line_type": "SERVICE", "non_standard_duration": False},
        {"line_type": "SUBSCRIPTION", "non_standard_duration": True},
    ]
    kpi = Kpi(kpi_id="kpi_non_standard", dataset_id=DATASET, operation="count",
             filter=KpiFilter(column="non_standard_duration", value="1"))
    analysis = Analysis(analysis_id="an_non_standard_by_type", operation="group_by",
                        dataset_id=DATASET, group_by=["line_type"], metric="kpi_non_standard")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    assert results[plan.analysis_node["an_non_standard_by_type"]] == {"SERVICE": 1, "SUBSCRIPTION": 1}


def test_crosstab_sum_numeric_honors_the_metric_kpis_own_filter() -> None:
    rows = [
        {"contract_type": "SERVICE", "renewal_type": "AUTO", "is_at_risk": True, "estimated_amount": 10.0},
        {"contract_type": "SERVICE", "renewal_type": "AUTO", "is_at_risk": False, "estimated_amount": 999.0},
        {"contract_type": "SERVICE", "renewal_type": "MANUAL", "is_at_risk": True, "estimated_amount": 20.0},
    ]
    kpi = Kpi(kpi_id="kpi_at_risk_value", dataset_id=DATASET, operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="is_at_risk", value="1"))
    analysis = Analysis(analysis_id="an_risk_crosstab", operation="crosstab", dataset_id=DATASET,
                        group_by=["contract_type", "renewal_type"], metric="kpi_at_risk_value")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["an_risk_crosstab"]]
    assert grouped == {
        ("SERVICE", "AUTO"): {"value": 10.0, "sample_size": 1},
        ("SERVICE", "MANUAL"): {"value": 20.0, "sample_size": 1},
    }


# ── controlled degradation ────────────────────────────────────────────────

def test_zero_denominator_returns_none_value_not_a_crash() -> None:
    rows: list[dict] = []  # no rows at all -> denominator is 0
    kpi = _renewal_rate_kpi()
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [])
    results, errors, _completed, failed = run_plan(plan, {DATASET: rows})
    assert errors == [] and failed == 0
    ratio_result = results[plan.kpi_final_node["kpi_renewal_rate"]]
    assert ratio_result == {"numerator": 0, "denominator": 0, "value": None}
    value, *_ = _kpi_result_from_node(ratio_result)
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


# ── crosstab (sankey/treemap/sunburst/heatmap_matrix) ─────────────────────

def test_crosstab_sum_numeric_by_two_columns() -> None:
    rows = [
        {"region": "West", "product": "A", "contract_value": 100.0},
        {"region": "West", "product": "A", "contract_value": 50.0},
        {"region": "West", "product": "B", "contract_value": 30.0},
        {"region": "East", "product": "A", "contract_value": 10.0},
    ]
    kpi = Kpi(kpi_id="kpi_value", dataset_id=DATASET, operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="analysis_flow", operation="crosstab", dataset_id=DATASET,
                        group_by=["region", "product"], metric="kpi_value")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["analysis_flow"]]
    assert grouped[("West", "A")] == {"value": 150.0, "sample_size": 2}
    assert grouped[("West", "B")] == {"value": 30.0, "sample_size": 1}
    assert grouped[("East", "A")] == {"value": 10.0, "sample_size": 1}

    result_rows = _analysis_rows(analysis, grouped)
    by_cell = {(r.group_value, r.group_value_secondary): r.value for r in result_rows}
    assert by_cell == {("East", "A"): 10.0, ("West", "A"): 150.0, ("West", "B"): 30.0}


def test_crosstab_safe_ratio_with_an_unfiltered_denominator_counts_every_row() -> None:
    # crosstab sibling of the grouped_safe_ratio regression above.
    rows = [
        {"contract_type": "SERVICE", "renewal_type": "AUTO", "is_renewed": "1"},
        {"contract_type": "SERVICE", "renewal_type": "AUTO", "is_renewed": "0"},
        {"contract_type": "SERVICE", "renewal_type": "MANUAL", "is_renewed": "1"},
    ]
    kpi = Kpi(
        kpi_id="kpi_renewal_rate", dataset_id=DATASET, operation="ratio",
        numerator=KpiOperand(operation="count", filter=KpiFilter(column="is_renewed", value="1")),
        denominator=KpiOperand(operation="count"),
    )
    analysis = Analysis(analysis_id="an_rate_crosstab", operation="crosstab", dataset_id=DATASET,
                        group_by=["contract_type", "renewal_type"], metric="kpi_renewal_rate")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    grouped = results[plan.analysis_node["an_rate_crosstab"]]
    assert grouped[("SERVICE", "AUTO")] == {"numerator": 1, "denominator": 2, "value": 0.5,
                                            "sample_size": 2}
    assert grouped[("SERVICE", "MANUAL")] == {"numerator": 1, "denominator": 1, "value": 1.0,
                                              "sample_size": 1}


# ── row_points (scatter/bubble) ────────────────────────────────────────────

def test_row_points_skips_rows_missing_x_or_y() -> None:
    rows = [
        {"account_name": "Acme", "deal_value": 100.0, "tenure_months": 12.0},
        {"account_name": "Beta", "deal_value": None, "tenure_months": 6.0},  # dropped: no x
        {"account_name": "Gamma", "deal_value": 50.0, "tenure_months": 3.0},
    ]
    analysis = Analysis(analysis_id="analysis_scatter", operation="row_points", dataset_id=DATASET,
                        group_by=["account_name"], x_column="deal_value", y_column="tenure_months")
    plan = compile_plan("spec_1", DATASET, "v1", [], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    points = results[plan.analysis_node["analysis_scatter"]]
    assert points == [
        {"label": "Acme", "x": 100.0, "y": 12.0, "size": None},
        {"label": "Gamma", "x": 50.0, "y": 3.0, "size": None},
    ]
    result_rows = _analysis_rows(analysis, points)
    assert [(r.group_value, r.x, r.y) for r in result_rows] == [("Acme", 100.0, 12.0), ("Gamma", 50.0, 3.0)]


# ── date_span (gantt) ───────────────────────────────────────────────────────

def test_date_span_sorts_by_start_and_skips_null_start() -> None:
    rows = [
        {"contract_id": "c1", "start_date": "2024-03-01", "end_date": "2024-06-01"},
        {"contract_id": "c2", "start_date": "2024-01-01", "end_date": "2024-02-01"},
        {"contract_id": "c3", "start_date": None, "end_date": "2024-09-01"},
    ]
    analysis = Analysis(analysis_id="analysis_gantt", operation="date_span", dataset_id=DATASET,
                        group_by=["contract_id"], start_column="start_date", end_column="end_date")
    plan = compile_plan("spec_1", DATASET, "v1", [], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    spans = results[plan.analysis_node["analysis_gantt"]]
    assert [s["label"] for s in spans] == ["c2", "c1"]
    result_rows = _analysis_rows(analysis, spans)
    assert [(r.group_value, r.start, r.end) for r in result_rows] == [
        ("c2", "2024-01-01", "2024-02-01"), ("c1", "2024-03-01", "2024-06-01"),
    ]


# ── survival (Kaplan-Meier) ─────────────────────────────────────────────────

def test_survival_curve_hand_computed_example() -> None:
    # 4 rows, all starting day 0. A/D churn at day 10, C churns at day 5, B is
    # still active (censored) — the latest date anywhere in the cohort is
    # day 10 (A/D's churn date), so B's duration-as-of is 10-0=10 too.
    #
    # Hand-computed KM by hand:
    #   at_risk=4, survival=1.0
    #   t=5:  1 event (C) of 4 at risk  -> survival *= (1 - 1/4) = 0.75; at_risk -= 1 (C exits) -> 3
    #   t=10: 2 events (A,D) of 3 at risk -> survival *= (1 - 2/3) = 0.25; at_risk -= 3 (A,B,D exit) -> 0
    rows = [
        {"cohort": "all", "signup_date": "2024-01-01", "churn_date": "2024-01-11"},  # A: day 10, event
        {"cohort": "all", "signup_date": "2024-01-01", "churn_date": None},           # B: censored, day 10
        {"cohort": "all", "signup_date": "2024-01-01", "churn_date": "2024-01-06"},   # C: day 5, event
        {"cohort": "all", "signup_date": "2024-01-01", "churn_date": "2024-01-11"},   # D: day 10, event
    ]
    curves = _survival_curve(rows, group_column="", start_column="signup_date", end_column="churn_date")
    assert curves["_all_"] == [
        {"duration_days": 5.0, "survived_fraction": 0.75, "at_risk": 4.0},
        {"duration_days": 10.0, "survived_fraction": 0.25, "at_risk": 3.0},
    ]


def test_survival_curve_drops_rows_with_unparseable_start() -> None:
    rows = [{"signup_date": None, "churn_date": "2024-01-11"}]
    curves = _survival_curve(rows, group_column="", start_column="signup_date", end_column="churn_date")
    assert curves == {}


def test_survival_curve_execution_and_row_unpacking() -> None:
    rows = [
        {"signup_date": "2024-01-01", "churn_date": "2024-01-11"},
        {"signup_date": "2024-01-01", "churn_date": None},
        {"signup_date": "2024-01-01", "churn_date": "2024-01-06"},
        {"signup_date": "2024-01-01", "churn_date": "2024-01-11"},
    ]
    analysis = Analysis(analysis_id="analysis_survival", operation="survival", dataset_id=DATASET,
                        start_column="signup_date", end_column="churn_date")
    plan = compile_plan("spec_1", DATASET, "v1", [], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    curves = results[plan.analysis_node["analysis_survival"]]
    result_rows = _analysis_rows(analysis, curves)
    assert [(r.group_value, r.duration_days, r.value, r.sample_size) for r in result_rows] == [
        ("_all_", 5.0, 0.75, 4), ("_all_", 10.0, 0.25, 3),
    ]


# ── histogram ────────────────────────────────────────────────────────────

def test_histogram_buckets_equal_width_bins() -> None:
    values = [float(v) for v in range(0, 100, 10)]  # 0,10,...,90 -> 10 values, range 0-90
    buckets = _histogram_buckets(values, bucket_count=3)
    assert len(buckets) == 3
    assert sum(b["count"] for b in buckets) == 10
    assert buckets[0]["bucket_start"] == 0.0 and buckets[-1]["bucket_end"] == 90.0


def test_histogram_buckets_empty_input() -> None:
    assert _histogram_buckets([]) == []


def test_ungrouped_histogram_execution_and_row_unpacking() -> None:
    rows = [{"deal_value": v} for v in [100.0, 200.0, 300.0, None]]
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="histogram", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_hist_all", operation="histogram",
                        dataset_id=DATASET, metric="kpi_deal_size")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    hist_result = results[plan.analysis_node["analysis_hist_all"]]
    assert hist_result["sample_size"] == 3 and hist_result["excluded_null_rows"] == 1
    result_rows = _analysis_rows(analysis, hist_result)
    assert len(result_rows) == 1
    assert result_rows[0].group_value == "_all_"
    assert result_rows[0].buckets == hist_result["buckets"]


def test_grouped_histogram_execution_and_row_unpacking() -> None:
    rows = (
        [{"deal_value": v, "region": "West"} for v in [100.0, 200.0]]
        + [{"deal_value": v, "region": "East"} for v in [10.0, 20.0]]
    )
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id=DATASET, operation="histogram", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_hist_by_region", operation="histogram",
                        dataset_id=DATASET, group_by=["region"], metric="kpi_deal_size")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    hist_result = results[plan.analysis_node["analysis_hist_by_region"]]
    result_rows = _analysis_rows(analysis, hist_result)
    assert {r.group_value for r in result_rows} == {"West", "East"}


# ── named_buckets ──────────────────────────────────────────────────────

_SEVERITY_BUCKETS = [
    BucketDef(label="Low (<=60d)", max=60), BucketDef(label="Medium (60-180d)", max=180),
    BucketDef(label="High (180-365d)", max=365), BucketDef(label="Critical (>365d)"),
]


def test_named_buckets_counts_rows_per_bucket_in_declared_order() -> None:
    rows = [
        {"draft_age_days": 10, "renewal_status": "DRAFT"},   # Low
        {"draft_age_days": 90, "renewal_status": "DRAFT"},   # Medium
        {"draft_age_days": 90, "renewal_status": "DRAFT"},   # Medium
        {"draft_age_days": 400, "renewal_status": "DRAFT"},  # Critical
        {"draft_age_days": 5, "renewal_status": "ACTIVE"},   # excluded by filter
        {"draft_age_days": None, "renewal_status": "DRAFT"},  # null, excluded
    ]
    kpi = Kpi(kpi_id="kpi_draft_severity", dataset_id=DATASET, operation="named_buckets",
             measure="draft_age_days", buckets=_SEVERITY_BUCKETS,
             filter=KpiFilter(column="renewal_status", value="DRAFT"))
    analysis = Analysis(analysis_id="an_draft_severity", operation="named_buckets",
                        dataset_id=DATASET, metric="kpi_draft_severity")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    result = results[plan.analysis_node["an_draft_severity"]]
    assert result["sample_size"] == 4  # DRAFT + non-null only
    assert result["excluded_null_rows"] == 1  # the null draft_age_days row
    result_rows = _analysis_rows(analysis, result)
    # Declared order preserved (Low, Medium, High, Critical) — NOT alphabetical.
    assert [r.group_value for r in result_rows] == [
        "Low (<=60d)", "Medium (60-180d)", "High (180-365d)", "Critical (>365d)"]
    assert [r.value for r in result_rows] == [1, 2, 0, 1]
    value, *_rest, sample_size, excluded = _kpi_result_from_node(result)
    assert value is None  # no single scalar, same contract as histogram
    assert sample_size == 4 and excluded == 1


def test_named_buckets_sums_a_value_column_per_bucket() -> None:
    rows = [
        {"end_date": "2020-01-01", "is_at_risk": "1", "estimated_amount": 100.0},  # far past -> Critical
        {"end_date": "2020-01-01", "is_at_risk": "1", "estimated_amount": 50.0},
        {"end_date": "2020-01-01", "is_at_risk": "0", "estimated_amount": 999.0},  # excluded by filter
    ]
    kpi = Kpi(kpi_id="kpi_risk_lapsed", dataset_id=DATASET, operation="named_buckets",
             date_diff_from="end_date", bucket_value_column="estimated_amount",
             buckets=[BucketDef(label="Lapsed <=30d", max=30), BucketDef(label="Lapsed >30d")],
             filter=KpiFilter(column="is_at_risk", value="1"))
    analysis = Analysis(analysis_id="an_risk_lapsed", operation="named_buckets",
                        dataset_id=DATASET, metric="kpi_risk_lapsed")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    result = results[plan.analysis_node["an_risk_lapsed"]]
    result_rows = {r.group_value: r for r in _analysis_rows(analysis, result)}
    assert result_rows["Lapsed <=30d"].value == 0.0
    assert result_rows["Lapsed >30d"].value == 150.0
    assert result_rows["Lapsed >30d"].sample_size == 2


def test_named_buckets_seeds_empty_buckets_at_zero_rather_than_omitting_them() -> None:
    rows = [{"draft_age_days": 10, "renewal_status": "DRAFT"}]
    kpi = Kpi(kpi_id="kpi_draft_severity", dataset_id=DATASET, operation="named_buckets",
             measure="draft_age_days", buckets=_SEVERITY_BUCKETS,
             filter=KpiFilter(column="renewal_status", value="DRAFT"))
    analysis = Analysis(analysis_id="an_draft_severity", operation="named_buckets",
                        dataset_id=DATASET, metric="kpi_draft_severity")
    plan = compile_plan("spec_1", DATASET, "v1", [kpi], [analysis])
    results, errors, _completed, _failed = run_plan(plan, {DATASET: rows})
    assert errors == []
    result_rows = _analysis_rows(analysis, results[plan.analysis_node["an_draft_severity"]])
    assert len(result_rows) == 4  # all 4 buckets present, even the 3 empty ones
    assert {r.group_value for r in result_rows} == {
        "Low (<=60d)", "Medium (60-180d)", "High (180-365d)", "Critical (>365d)"}


# ── graph_relation (C06 verified paths, no dataset rows involved) ─────────

class _FakeGraphReader:
    """Minimal double for GraphReaderPort — only count_by_relationship is used."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def count_by_relationship(self, source_type, relationship, target_type, direction="out"):
        assert (source_type, relationship, target_type) == ("Contract", "MANAGED_BY", "Manager")
        return dict(self._counts)


class _FakeGraphProfileStore:
    """Double for GraphProfileStore — resolve_graph_relation_nodes only calls
    .latest()/.close()."""

    def __init__(self, profile: GraphProfile | None) -> None:
        self._profile = profile

    def __call__(self, dsn, workspace_id):  # mimics the class constructor
        return self

    def latest(self, graph_id):
        # GraphProfileStore's graph_id is a Postgres-side identifier
        # ("graph_workspace_{id}", see planning/run.py's own gstore.latest()
        # call) — a different convention from ws_graph()'s FalkorDB graph
        # NAME ("aryx_ws_{id}"). Asserting the exact value here is what
        # would have caught the real bug where resolve_graph_relation_nodes
        # was built against the wrong one and silently found no profile.
        assert graph_id == "graph_workspace_1"
        return self._profile

    def close(self) -> None:
        pass


def _graph_relation_plan() -> tuple:
    analysis = Analysis(analysis_id="analysis_by_manager", operation="graph_relation",
                        dataset_id="", graph_path_id="path_contract_manager")
    plan = compile_plan("spec_1", "workspace_1", "v1", [], [analysis])
    return plan, analysis


def test_resolve_graph_relation_nodes_fills_in_the_triple(monkeypatch) -> None:
    plan, _ = _graph_relation_plan()
    profile = GraphProfile(
        graph_profile_id="gp1", graph_id="graph_workspace_1", graph_version="v1",
        verified_paths=[VerifiedPath(path_id="path_contract_manager",
                                     path=["Contract", "MANAGED_BY", "Manager"], depth=1)])
    monkeypatch.setattr(execute_module, "GraphProfileStore", _FakeGraphProfileStore(profile))
    resolve_graph_relation_nodes("dsn", 1, plan)
    node = next(n for n in plan.nodes if n.template == "graph_relation_count")
    assert node.parameters == {"path_id": "path_contract_manager", "source_type": "Contract",
                               "relationship": "MANAGED_BY", "target_type": "Manager",
                               "direction": "out"}


def test_resolve_graph_relation_nodes_leaves_deeper_path_unresolved(monkeypatch) -> None:
    plan, _ = _graph_relation_plan()
    profile = GraphProfile(
        graph_profile_id="gp1", graph_id="graph_workspace_1", graph_version="v1",
        verified_paths=[VerifiedPath(
            path_id="path_contract_manager",
            path=["Contract", "MANAGED_BY", "Team", "PART_OF", "Manager"], depth=2)])
    monkeypatch.setattr(execute_module, "GraphProfileStore", _FakeGraphProfileStore(profile))
    resolve_graph_relation_nodes("dsn", 1, plan)
    node = next(n for n in plan.nodes if n.template == "graph_relation_count")
    assert node.parameters == {"path_id": "path_contract_manager"}  # left as-is, not truncated


def test_graph_relation_node_executes_with_injected_graph_reader() -> None:
    plan, analysis = _graph_relation_plan()
    for node in plan.nodes:
        if node.template == "graph_relation_count":
            node.parameters = {**node.parameters, "source_type": "Contract",
                               "relationship": "MANAGED_BY", "target_type": "Manager",
                               "direction": "out"}
    reader = _FakeGraphReader({"Jane Doe": 3, "Sam Lee": 1})
    results, errors, completed, failed = run_plan(plan, {}, graph_reader=reader)
    assert errors == [] and failed == 0 and completed == 1
    node_id = plan.analysis_node["analysis_by_manager"]
    assert results[node_id] == {"Jane Doe": 3, "Sam Lee": 1}
    result_rows = _analysis_rows(analysis, results[node_id])
    assert {r.group_value for r in result_rows} == {"Jane Doe", "Sam Lee"}


def test_graph_relation_node_fails_cleanly_without_graph_reader() -> None:
    plan, _ = _graph_relation_plan()
    for node in plan.nodes:
        if node.template == "graph_relation_count":
            node.parameters = {**node.parameters, "source_type": "Contract",
                               "relationship": "MANAGED_BY", "target_type": "Manager",
                               "direction": "out"}
    results, errors, completed, failed = run_plan(plan, {})  # no graph_reader injected
    assert failed == 1 and completed == 0
    assert results == {}
    assert any("graph_relation_count" in e for e in errors)


def test_graph_relation_node_fails_cleanly_when_path_unresolved() -> None:
    plan, _ = _graph_relation_plan()  # parameters == {"path_id": ...} only, never resolved
    reader = _FakeGraphReader({})
    results, errors, completed, failed = run_plan(plan, {}, graph_reader=reader)
    assert failed == 1 and completed == 0
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

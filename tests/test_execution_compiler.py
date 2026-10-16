"""Tests for the Execution Compiler (C11) — pure, no DB, no LLM."""
from __future__ import annotations

from aryx.andie_planner.models import Analysis, BucketDef, Kpi, KpiFilter, KpiOperand
from aryx.execution_compiler.compile import compile_plan, compile_plan_for_spec
from aryx.execution_compiler.models import ExecutionNode
from aryx.execution_compiler.validate import check_resource_limits, is_acyclic, validate_bindings


def _by_id(nodes, node_id):
    return next(n for n in nodes if n.node_id == node_id)


# ── single KPI compilation ────────────────────────────────────────────────

def test_count_kpi_with_filter_compiles_filter_then_count() -> None:
    kpi = Kpi(kpi_id="kpi_completed", dataset_id="ds1", operation="count",
             filter=KpiFilter(column="renewal_status", values=["Renewed", "Not Renewed"]))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    assert plan.compilation_status == "success"
    assert plan.plan_acyclic is True
    filt = _by_id(plan.nodes, "op_kpi_completed_filter")
    assert filt.template == "filter_in"
    assert filt.dataset_id == "ds1"
    assert filt.parameters == {"column": "renewal_status", "values": ["Renewed", "Not Renewed"]}
    count = _by_id(plan.nodes, "op_kpi_completed_count")
    assert count.template == "count_rows"
    assert count.depends_on == ["op_kpi_completed_filter"]
    assert plan.kpi_final_node["kpi_completed"] == "op_kpi_completed_count"
    assert plan.kpi_lineage_nodes["kpi_completed"] == ["op_kpi_completed_filter", "op_kpi_completed_count"]


def test_sum_kpi_without_filter_compiles_directly() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id="ds1", operation="sum", measure="contract_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    node = _by_id(plan.nodes, "op_kpi_value_sum")
    assert node.template == "sum_numeric"
    assert node.parameters == {"column": "contract_value", "null_policy": "exclude"}
    assert node.depends_on == []


def test_ratio_kpi_builds_full_numerator_denominator_dag() -> None:
    kpi = Kpi(
        kpi_id="kpi_renewal_rate", dataset_id="ds1", operation="ratio",
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count",
                             filter=KpiFilter(column="renewal_status", value="Renewed")),
        denominator=KpiOperand(operation="count",
                               filter=KpiFilter(column="renewal_status",
                                                values=["Renewed", "Not Renewed"])),
    )
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    assert plan.compilation_status == "success"
    assert plan.plan_acyclic is True

    num_filter = _by_id(plan.nodes, "op_kpi_renewal_rate_numerator_filter")
    assert num_filter.template == "filter_equals"
    num_count = _by_id(plan.nodes, "op_kpi_renewal_rate_numerator_count")
    assert num_count.depends_on == ["op_kpi_renewal_rate_numerator_filter"]

    den_filter = _by_id(plan.nodes, "op_kpi_renewal_rate_denominator_filter")
    assert den_filter.template == "filter_in"
    den_count = _by_id(plan.nodes, "op_kpi_renewal_rate_denominator_count")
    assert den_count.depends_on == ["op_kpi_renewal_rate_denominator_filter"]

    ratio = _by_id(plan.nodes, "op_kpi_renewal_rate_ratio")
    assert ratio.template == "safe_ratio"
    assert ratio.parameters == {
        "numerator_ref": "op_kpi_renewal_rate_numerator_count",
        "denominator_ref": "op_kpi_renewal_rate_denominator_count",
        "zero_policy": "return_null_with_warning",
    }
    assert set(ratio.depends_on) == {
        "op_kpi_renewal_rate_numerator_count", "op_kpi_renewal_rate_denominator_count",
    }
    assert len(plan.nodes) == 5  # numerator filter+count, denominator filter+count, ratio


def test_ratio_kpi_with_a_top_level_filter_scopes_both_operands() -> None:
    # Regression, found live building a real dashboard: a ratio KPI's own
    # top-level `.filter` (e.g. "Manual Renewal Rate" scoped to
    # renewal_type=MANUAL) was silently ignored by compilation — the
    # numerator (is_renewed=1) counted EVERY row in the dataset, not just
    # MANUAL ones, against a denominator correctly scoped to MANUAL via its
    # own operand filter. That produced a mathematically impossible rate
    # above 100% live. Both operands — including one with NO filter of its
    # own — must narrow within the KPI's base filter.
    kpi = Kpi(
        kpi_id="kpi_manual_rate", dataset_id="ds1", operation="ratio",
        filter=KpiFilter(column="renewal_type", value="MANUAL"),
        zero_denominator_policy="return_null_with_warning",
        numerator=KpiOperand(operation="count",
                             filter=KpiFilter(column="is_renewed", value="1")),
        denominator=KpiOperand(operation="count"),  # no filter of its own
    )
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    base_filter = _by_id(plan.nodes, "op_kpi_manual_rate_base_filter")
    assert base_filter.template == "filter_equals"
    assert base_filter.parameters == {"column": "renewal_type", "value": "MANUAL"}
    assert base_filter.depends_on == []

    num_filter = _by_id(plan.nodes, "op_kpi_manual_rate_numerator_filter")
    assert num_filter.depends_on == ["op_kpi_manual_rate_base_filter"]
    num_count = _by_id(plan.nodes, "op_kpi_manual_rate_numerator_count")
    assert num_count.depends_on == ["op_kpi_manual_rate_numerator_filter"]

    # Denominator has no operand-level filter — it must depend on the BASE
    # filter directly, not compile to an unfiltered count_rows.
    den_count = _by_id(plan.nodes, "op_kpi_manual_rate_denominator_count")
    assert den_count.depends_on == ["op_kpi_manual_rate_base_filter"]


def test_ratio_kpi_without_a_top_level_filter_is_unaffected() -> None:
    kpi = Kpi(kpi_id="kpi_r", dataset_id="ds1", operation="ratio",
             zero_denominator_policy="return_null_with_warning",
             numerator=KpiOperand(operation="count"), denominator=KpiOperand(operation="count"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    assert not any(n.node_id == "op_kpi_r_base_filter" for n in plan.nodes)
    num_count = _by_id(plan.nodes, "op_kpi_r_numerator_count")
    assert num_count.depends_on == []


def test_ratio_kpi_defaults_zero_policy_when_unset() -> None:
    kpi = Kpi(kpi_id="kpi_r", dataset_id="ds1", operation="percentage",
             numerator=KpiOperand(operation="count"), denominator=KpiOperand(operation="count"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    ratio = _by_id(plan.nodes, "op_kpi_r_ratio")
    assert ratio.parameters["zero_policy"] == "return_null_with_warning"


def test_ratio_kpi_with_numeric_operand_operation_is_rejected() -> None:
    # KpiOperand has no measure/column field — "sum"/"average"/"median" as a
    # numerator/denominator op has no column to bind and used to silently
    # compile against an empty column name (fabricating 0.0) instead of
    # being rejected.
    kpi = Kpi(kpi_id="kpi_bad", dataset_id="ds1", operation="ratio",
             numerator=KpiOperand(operation="sum"), denominator=KpiOperand(operation="count"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    assert plan.compilation_status == "rejected"
    assert any(i.code == "unsupported_ratio_operand_operation" for i in plan.issues)


# ── analysis (grouped) compilation ────────────────────────────────────────

def test_grouped_analysis_referencing_ratio_kpi() -> None:
    kpi = Kpi(
        kpi_id="kpi_renewal_rate", dataset_id="ds1", operation="ratio",
        numerator=KpiOperand(operation="count",
                             filter=KpiFilter(column="renewal_status", value="Renewed")),
        denominator=KpiOperand(operation="count",
                               filter=KpiFilter(column="renewal_status",
                                                values=["Renewed", "Not Renewed"])),
    )
    analysis = Analysis(analysis_id="analysis_by_region", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_renewal_rate")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_by_region_grouped")
    assert grouped.template == "grouped_safe_ratio"
    assert grouped.parameters == {
        "group_column": "region", "status_column": "renewal_status",
        "numerator_values": ["Renewed"], "denominator_values": ["Renewed", "Not Renewed"],
        "zero_policy": "return_null_with_warning",
    }
    assert plan.analysis_node["analysis_by_region"] == "op_analysis_by_region_grouped"
    assert plan.kpi_final_node["kpi_renewal_rate"] == "op_kpi_renewal_rate_ratio"


def test_quartiles_kpi_compiles_to_quartiles_numeric() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id="ds1", operation="quartiles", measure="deal_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    node = _by_id(plan.nodes, "op_kpi_deal_size_quartiles")
    assert node.template == "quartiles_numeric"
    assert node.parameters == {"column": "deal_value", "null_policy": "exclude"}


def test_grouped_analysis_referencing_quartiles_kpi() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id="ds1", operation="quartiles", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_deal_size_by_region", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_deal_size")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_deal_size_by_region_grouped")
    assert grouped.template == "grouped_quartiles_numeric"
    assert grouped.parameters == {"group_column": "region", "column": "deal_value",
                                  "null_policy": "exclude"}


def test_grouped_analysis_referencing_sum_kpi() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id="ds1", operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="analysis_value_by_region", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_value_by_region_grouped")
    assert grouped.template == "grouped_sum_numeric"
    assert grouped.parameters == {"group_column": "region", "column": "contract_value",
                                  "null_policy": "exclude"}


def test_grouped_analysis_threads_the_metric_kpis_own_filter() -> None:
    # Regression: grouped_count_rows/grouped_sum_numeric/grouped_quartiles_numeric
    # and crosstab's non-ratio variants used to ignore metric_kpi.filter
    # entirely — a KPI correctly defined as "sum(estimated_amount) WHERE
    # is_at_risk=1" charted as total value by category, not at-risk value,
    # the moment an Analysis grouped it by anything.
    kpi = Kpi(kpi_id="kpi_at_risk_value", dataset_id="ds1", operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="is_at_risk", value="1"))
    analysis = Analysis(analysis_id="an_risk_by_type", operation="group_by",
                        dataset_id="ds1", group_by=["contract_type"], metric="kpi_at_risk_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    filt = _by_id(plan.nodes, "op_an_risk_by_type_filter")
    assert filt.template == "filter_equals"
    assert filt.parameters == {"column": "is_at_risk", "value": "1"}
    node = _by_id(plan.nodes, "op_an_risk_by_type_grouped")
    assert node.template == "grouped_sum_numeric"
    assert node.depends_on == ["op_an_risk_by_type_filter"]


def test_grouped_analysis_without_a_kpi_filter_has_no_filter_dependency() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id="ds1", operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="an_value_by_region", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_an_value_by_region_grouped")
    assert node.depends_on == []


def test_crosstab_analysis_threads_the_metric_kpis_own_filter() -> None:
    kpi = Kpi(kpi_id="kpi_at_risk_value", dataset_id="ds1", operation="sum",
             measure="estimated_amount", filter=KpiFilter(column="is_at_risk", value="1"))
    analysis = Analysis(analysis_id="an_risk_crosstab", operation="crosstab", dataset_id="ds1",
                        group_by=["contract_type", "renewal_type"], metric="kpi_at_risk_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    filt = _by_id(plan.nodes, "op_an_risk_crosstab_filter")
    assert filt.parameters == {"column": "is_at_risk", "value": "1"}
    node = _by_id(plan.nodes, "op_an_risk_crosstab_grouped")
    assert node.template == "grouped2d_sum_numeric"
    assert node.depends_on == ["op_an_risk_crosstab_filter"]


def test_grouped_analysis_with_unknown_metric_falls_back_to_count() -> None:
    analysis = Analysis(analysis_id="analysis_ghost", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_nonexistent")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_ghost_grouped")
    assert grouped.template == "grouped_count_rows"
    assert grouped.parameters == {"group_column": "region"}


# ── new chart-type shapes (crosstab/row_points/date_span/survival/histogram) ──

def test_crosstab_analysis_referencing_sum_kpi() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id="ds1", operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="analysis_flow", operation="crosstab", dataset_id="ds1",
                        group_by=["region", "product"], metric="kpi_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_analysis_flow_grouped")
    assert node.template == "grouped2d_sum_numeric"
    assert node.parameters == {"group_column": "region", "group_column_2": "product",
                               "column": "contract_value", "null_policy": "exclude"}


def test_crosstab_analysis_without_metric_falls_back_to_count() -> None:
    analysis = Analysis(analysis_id="analysis_flow", operation="crosstab", dataset_id="ds1",
                        group_by=["region", "product"])
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    node = _by_id(plan.nodes, "op_analysis_flow_grouped")
    assert node.template == "grouped2d_count_rows"
    assert node.parameters == {"group_column": "region", "group_column_2": "product"}


def test_row_points_analysis_compiles_directly_with_no_metric() -> None:
    analysis = Analysis(analysis_id="analysis_scatter", operation="row_points", dataset_id="ds1",
                        group_by=["account_name"], x_column="deal_value", y_column="tenure_months")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    node = _by_id(plan.nodes, "op_analysis_scatter_grouped")
    assert node.template == "row_points"
    assert node.parameters == {"label_column": "account_name", "x_column": "deal_value",
                               "y_column": "tenure_months", "size_column": ""}


def test_date_span_analysis_compiles_directly() -> None:
    analysis = Analysis(analysis_id="analysis_gantt", operation="date_span", dataset_id="ds1",
                        group_by=["contract_id"], start_column="start_date", end_column="end_date")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    node = _by_id(plan.nodes, "op_analysis_gantt_grouped")
    assert node.template == "row_date_spans"
    assert node.parameters == {"label_column": "contract_id", "start_column": "start_date",
                               "end_column": "end_date"}


def test_survival_analysis_compiles_directly() -> None:
    analysis = Analysis(analysis_id="analysis_survival", operation="survival", dataset_id="ds1",
                        start_column="signup_date", end_column="churn_date")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    node = _by_id(plan.nodes, "op_analysis_survival_grouped")
    assert node.template == "survival_curve"
    assert node.parameters == {"group_column": "", "start_column": "signup_date",
                               "end_column": "churn_date"}


def test_graph_relation_analysis_compiles_with_no_dataset_id() -> None:
    analysis = Analysis(analysis_id="analysis_by_manager", operation="graph_relation",
                        dataset_id="ds1", graph_path_id="path_contract_manager")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    node = _by_id(plan.nodes, "op_analysis_by_manager_grouped")
    assert node.template == "graph_relation_count"
    assert node.dataset_id == ""  # never fetches dataset rows for this node
    assert node.parameters == {"path_id": "path_contract_manager"}
    assert plan.compilation_status == "success"  # registered template, valid bindings


def test_histogram_kpi_compiles_to_histogram_buckets_numeric() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id="ds1", operation="histogram", measure="deal_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    node = _by_id(plan.nodes, "op_kpi_deal_size_histogram")
    assert node.template == "histogram_buckets_numeric"
    assert node.parameters == {"column": "deal_value", "null_policy": "exclude"}


def test_grouped_analysis_referencing_histogram_kpi() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id="ds1", operation="histogram", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_hist_by_region", operation="histogram",
                        dataset_id="ds1", group_by=["region"], metric="kpi_deal_size")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_analysis_hist_by_region_grouped")
    assert node.template == "grouped_histogram_buckets_numeric"
    assert node.parameters == {"group_column": "region", "column": "deal_value",
                               "null_policy": "exclude"}


def test_ungrouped_histogram_analysis_compiles_to_ungrouped_template() -> None:
    kpi = Kpi(kpi_id="kpi_deal_size", dataset_id="ds1", operation="histogram", measure="deal_value")
    analysis = Analysis(analysis_id="analysis_hist_all", operation="histogram",
                        dataset_id="ds1", metric="kpi_deal_size")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_analysis_hist_all_grouped")
    assert node.template == "histogram_buckets_numeric"
    assert node.parameters == {"column": "deal_value", "null_policy": "exclude"}


_SEVERITY_BUCKETS = [
    BucketDef(label="Low (<=60d)", max=60), BucketDef(label="Medium (60-180d)", max=180),
    BucketDef(label="High (180-365d)", max=365), BucketDef(label="Critical (>365d)"),
]


def test_named_buckets_kpi_compiles_to_named_buckets_numeric() -> None:
    kpi = Kpi(kpi_id="kpi_draft_severity", dataset_id="ds1", operation="named_buckets",
             measure="draft_age_days", buckets=_SEVERITY_BUCKETS,
             filter=KpiFilter(column="renewal_status", value="DRAFT"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    filt = _by_id(plan.nodes, "op_kpi_draft_severity_filter")
    assert filt.template == "filter_equals"
    node = _by_id(plan.nodes, "op_kpi_draft_severity_named_buckets")
    assert node.template == "named_buckets_numeric"
    assert node.depends_on == ["op_kpi_draft_severity_filter"]
    assert node.parameters == {
        "column": "draft_age_days", "date_diff_from": "", "value_column": "",
        "null_policy": "exclude",
        "buckets": [
            {"label": "Low (<=60d)", "max": 60.0}, {"label": "Medium (60-180d)", "max": 180.0},
            {"label": "High (180-365d)", "max": 365.0}, {"label": "Critical (>365d)", "max": None},
        ],
    }


def test_named_buckets_kpi_with_date_diff_from_and_no_measure() -> None:
    kpi = Kpi(kpi_id="kpi_lapsed", dataset_id="ds1", operation="named_buckets",
             date_diff_from="end_date", bucket_value_column="estimated_amount",
             buckets=[BucketDef(label="Lapsed <=30d", max=30), BucketDef(label="Lapsed >30d")],
             filter=KpiFilter(column="is_at_risk", value="1"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    node = _by_id(plan.nodes, "op_kpi_lapsed_named_buckets")
    assert node.parameters["column"] == ""
    assert node.parameters["date_diff_from"] == "end_date"
    assert node.parameters["value_column"] == "estimated_amount"


def test_named_buckets_analysis_threads_the_metric_kpis_own_filter() -> None:
    # Unlike the (pre-existing) histogram analysis dispatch, named_buckets
    # must apply the metric KPI's own filter — a severity/lapsed-bucket
    # breakdown is meaningless over the whole unfiltered table.
    kpi = Kpi(kpi_id="kpi_draft_severity", dataset_id="ds1", operation="named_buckets",
             measure="draft_age_days", buckets=_SEVERITY_BUCKETS,
             filter=KpiFilter(column="renewal_status", value="DRAFT"))
    analysis = Analysis(analysis_id="an_draft_severity", operation="named_buckets",
                        dataset_id="ds1", metric="kpi_draft_severity")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    filt = _by_id(plan.nodes, "op_an_draft_severity_filter")
    assert filt.template == "filter_equals"
    assert filt.parameters == {"column": "renewal_status", "value": "DRAFT"}
    node = _by_id(plan.nodes, "op_an_draft_severity_grouped")
    assert node.template == "named_buckets_numeric"
    assert node.depends_on == ["op_an_draft_severity_filter"]


def test_named_buckets_analysis_without_filter_has_no_dependency() -> None:
    kpi = Kpi(kpi_id="kpi_lapsed", dataset_id="ds1", operation="named_buckets",
             date_diff_from="end_date", buckets=[BucketDef(label="Any")])
    analysis = Analysis(analysis_id="an_lapsed", operation="named_buckets",
                        dataset_id="ds1", metric="kpi_lapsed")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_an_lapsed_grouped")
    assert node.depends_on == []


def test_named_buckets_analysis_with_mismatched_metric_falls_back_to_count() -> None:
    kpi = Kpi(kpi_id="kpi_a", dataset_id="ds1", operation="count")
    analysis = Analysis(analysis_id="an_a", operation="named_buckets",
                        dataset_id="ds1", group_by=["region"], metric="kpi_a")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    node = _by_id(plan.nodes, "op_an_a_grouped")
    assert node.template == "grouped_count_rows"


# ── determinism + limits ─────────────────────────────────────────────────

def test_node_ids_are_deterministic_across_runs() -> None:
    kpi = Kpi(kpi_id="kpi_a", dataset_id="ds1", operation="count")
    plan1 = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    plan2 = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    assert [n.node_id for n in plan1.nodes] == [n.node_id for n in plan2.nodes]
    assert plan1.execution_plan_id != plan2.execution_plan_id  # unique per compile


def test_row_limit_clamped_to_dataset_row_count() -> None:
    kpi = Kpi(kpi_id="kpi_a", dataset_id="ds1", operation="count")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [], row_limit=1_000_000,
                        dataset_row_count=42)
    assert plan.row_limit == 42


def test_node_limit_exceeded_rejects_the_plan() -> None:
    kpis = [Kpi(kpi_id=f"kpi_{i}", dataset_id="ds1", operation="count") for i in range(5)]
    plan = compile_plan("spec_1", "ds1", "v1", kpis, [], node_limit=3)
    assert plan.compilation_status == "rejected"
    assert any(i.code == "node_limit_exceeded" for i in plan.issues)


def test_compile_plan_for_spec_wrapper() -> None:
    from aryx.andie_planner.models import DashboardSpec

    spec = DashboardSpec(spec_id="spec_1", dataset_id="ds1", dataset_version="v1",
                         kpis=[Kpi(kpi_id="kpi_a", dataset_id="ds1", operation="count")])
    plan = compile_plan_for_spec(spec, dataset_row_count=10)
    assert plan.dataset_id == "ds1" and plan.spec_id == "spec_1"
    assert plan.row_limit == 10


# ── validate.py structural checks ─────────────────────────────────────────

def test_validate_bindings_flags_unknown_template() -> None:
    nodes = [ExecutionNode(node_id="n1", template="drop_table", parameters={})]
    issues = validate_bindings(nodes)
    assert any(i.code == "unknown_template" and i.node_id == "n1" for i in issues)


def test_validate_bindings_flags_parameter_mismatch() -> None:
    nodes = [ExecutionNode(node_id="n1", template="count_rows", parameters={"extra": 1})]
    issues = validate_bindings(nodes)
    assert any(i.code == "parameter_mismatch" and i.node_id == "n1" for i in issues)


def test_validate_bindings_flags_duplicate_node_id() -> None:
    nodes = [
        ExecutionNode(node_id="n1", template="count_rows", parameters={}),
        ExecutionNode(node_id="n1", template="count_rows", parameters={}),
    ]
    issues = validate_bindings(nodes)
    assert any(i.code == "duplicate_node_id" and i.node_id == "n1" for i in issues)


def test_validate_bindings_flags_dangling_dependency() -> None:
    nodes = [ExecutionNode(node_id="n1", template="count_rows", parameters={}, depends_on=["ghost"])]
    issues = validate_bindings(nodes)
    assert any(i.code == "dangling_dependency" and i.detail == "ghost" for i in issues)


def test_is_acyclic_true_for_valid_dag() -> None:
    nodes = [
        ExecutionNode(node_id="a", template="filter_equals", parameters={"column": "x", "value": 1}),
        ExecutionNode(node_id="b", template="count_rows", parameters={}, depends_on=["a"]),
    ]
    assert is_acyclic(nodes) is True


def test_is_acyclic_false_for_a_cycle() -> None:
    nodes = [
        ExecutionNode(node_id="a", template="count_rows", parameters={}, depends_on=["b"]),
        ExecutionNode(node_id="b", template="count_rows", parameters={}, depends_on=["a"]),
    ]
    assert is_acyclic(nodes) is False


def test_check_resource_limits_pass_and_fail() -> None:
    nodes = [ExecutionNode(node_id="a", template="count_rows", parameters={})]
    assert check_resource_limits(nodes, node_limit=1) == []
    issues = check_resource_limits(nodes, node_limit=0)
    assert len(issues) == 1 and issues[0].code == "node_limit_exceeded"

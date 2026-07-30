"""Tests for the Execution Compiler (C11) — pure, no DB, no LLM."""
from __future__ import annotations

from aryx.andie_planner.models import Analysis, Kpi, KpiFilter, KpiOperand
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


def test_ratio_kpi_defaults_zero_policy_when_unset() -> None:
    kpi = Kpi(kpi_id="kpi_r", dataset_id="ds1", operation="percentage",
             numerator=KpiOperand(operation="count"), denominator=KpiOperand(operation="count"))
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [])
    ratio = _by_id(plan.nodes, "op_kpi_r_ratio")
    assert ratio.parameters["zero_policy"] == "return_null_with_warning"


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


def test_grouped_analysis_referencing_sum_kpi() -> None:
    kpi = Kpi(kpi_id="kpi_value", dataset_id="ds1", operation="sum", measure="contract_value")
    analysis = Analysis(analysis_id="analysis_value_by_region", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_value")
    plan = compile_plan("spec_1", "ds1", "v1", [kpi], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_value_by_region_grouped")
    assert grouped.template == "grouped_sum_numeric"
    assert grouped.parameters == {"group_column": "region", "column": "contract_value",
                                  "null_policy": "exclude"}


def test_grouped_analysis_with_unknown_metric_falls_back_to_count() -> None:
    analysis = Analysis(analysis_id="analysis_ghost", operation="group_by",
                        dataset_id="ds1", group_by=["region"], metric="kpi_nonexistent")
    plan = compile_plan("spec_1", "ds1", "v1", [], [analysis])
    grouped = _by_id(plan.nodes, "op_analysis_ghost_grouped")
    assert grouped.template == "grouped_count_rows"
    assert grouped.parameters == {"group_column": "region"}


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

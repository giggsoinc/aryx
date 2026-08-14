"""Tests for ask-to-visualize (C08 extension) — pure, no LLM, no DB.

Mirrors test_andie_planner.py's style: ground.py/delta.py are pure and
deterministic, tested with hand-built raw JSON and a fake complete_json_fn.
confirm_delta's DB-touching orchestration (persist + C10 + C11 + C12 + C14)
is not unit-tested here — same convention this codebase already uses for
run_planner/run_planner_workspace (only assemble_spec/assemble_workspace_spec
are unit-tested; the DB glue is exercised live).
"""
from __future__ import annotations

from types import SimpleNamespace

from aryx.andie_planner.delta import _merge_spec, _preview_text, draft_delta
from aryx.andie_planner.ground import ground_delta
from aryx.andie_planner.models import (
    Analysis, BusinessQuestion, DashboardSpec, DeltaSpecItems, Kpi, KpiFilter, KpiOperand, Visualization,
)
from aryx.andie_planner.prompt import build_delta_prompt

DATASET = "dataset_contracts"
APPROVED_COLUMNS = [
    {"name": "contract_id", "type": "identifier", "sample_values": []},
    {"name": "region", "type": "categorical", "sample_values": ["North", "South"]},
    {"name": "contract_value", "type": "numeric", "sample_values": ["100.0", "200.0"]},
    {"name": "renewal_status", "type": "categorical", "sample_values": ["Renewed", "Not Renewed"]},
]
APPROVED_OPS = ["count", "sum", "average", "ratio", "group_by"]
APPROVED_CHARTS = ["kpi_card", "bar", "donut"]


def _existing_spec() -> DashboardSpec:
    return DashboardSpec(
        spec_id="dashboard_spec_dataset_contracts_v1", dataset_id=DATASET, dataset_version="v1",
        business_questions=[BusinessQuestion(question_id="bq_1", text="What is the renewal rate?")],
        kpis=[Kpi(
            kpi_id="kpi_renewal_rate", name="Renewal Rate", dataset_id=DATASET, operation="ratio",
            numerator=KpiOperand(operation="count", filter=KpiFilter(column="renewal_status", value="Renewed")),
            denominator=KpiOperand(operation="count",
                                   filter=KpiFilter(column="renewal_status", values=["Renewed", "Not Renewed"])),
            zero_denominator_policy="return_null_with_warning", format="percentage",
        )],
        analyses=[Analysis(analysis_id="analysis_renewal_by_region", operation="group_by", dataset_id=DATASET,
                           group_by=["region"], metric="kpi_renewal_rate")],
        visualizations=[Visualization(chart_id="chart_kpi_card", chart_type="kpi_card",
                                      source_ref="kpi_renewal_rate")],
    )


def _planning_context():
    return SimpleNamespace(
        dataset_id=DATASET, dataset_version="v1", domain="contract_management",
        approved_columns=[SimpleNamespace(name=c["name"], type=c["type"], sample_values=c["sample_values"])
                          for c in APPROVED_COLUMNS],
        datasets=[],
        approved_graph_paths=[],
        supported_operations=APPROVED_OPS, supported_charts=APPROVED_CHARTS,
    )


class _FakeBroker:
    def choose(self, tier):
        return SimpleNamespace(name="fake-model")


def _fake_complete_json(payload: dict):
    def fn(broker, tier, system, user, schema):
        return payload
    return fn


def _sequential_complete_json(payloads: list[dict]):
    """A different response per call — for exercising the one-repair-retry
    path, which needs the SECOND call to see a repair-constraints prompt."""
    calls = iter(payloads)

    def fn(broker, tier, system, user, schema):
        return next(calls)
    return fn


# ── draft_delta — single-dataset mode ─────────────────────────────────────

def test_draft_delta_reuses_existing_analysis_directly() -> None:
    payload = {
        "new_visualization": {"chart_id": "chart_new", "chart_type": "bar",
                              "source_ref": "analysis_renewal_by_region"},
    }
    result = draft_delta(_existing_spec(), _planning_context(), "show renewal rate by region as a bar chart",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_kpi is None and result.items.new_analysis is None
    assert result.items.new_visualization.source_ref == "analysis_renewal_by_region"
    assert result.would_validate is True


def test_draft_delta_creates_new_kpi_and_analysis_when_needed() -> None:
    payload = {
        "new_kpi": {"kpi_id": "kpi_avg_value", "name": "Average Contract Value", "operation": "average",
                   "measure": "contract_value", "format": "currency"},
        "new_analysis": {"analysis_id": "analysis_avg_value_by_region", "operation": "group_by",
                        "group_by": ["region"], "metric": "kpi_avg_value"},
        "new_visualization": {"chart_id": "chart_avg", "chart_type": "bar",
                              "source_ref": "analysis_avg_value_by_region"},
    }
    result = draft_delta(_existing_spec(), _planning_context(), "average contract value by region",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_kpi.kpi_id == "kpi_avg_value"
    assert result.items.new_analysis.metric == "kpi_avg_value"
    assert result.items.new_visualization.source_ref == "analysis_avg_value_by_region"


def test_draft_delta_drops_invented_chart_type() -> None:
    payload = {"new_visualization": {"chart_id": "chart_new", "chart_type": "3d_globe",
                                     "source_ref": "kpi_renewal_rate"}}
    result = draft_delta(_existing_spec(), _planning_context(), "show a 3d globe of renewals",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "invalid"
    assert result.items.new_visualization is None
    assert any(w.code == "unsupported_chart_type" for w in result.items.warnings)


def test_draft_delta_rejects_incoherent_new_kpi() -> None:
    # A ratio KPI with no numerator/denominator grounds fine (KpiFilter is
    # optional structurally) but must be REJECTED by the merged-spec
    # validation check, same as the batch planner path.
    payload = {
        "new_kpi": {"kpi_id": "kpi_bad_ratio", "operation": "ratio"},
        "new_visualization": {"chart_id": "c1", "chart_type": "kpi_card", "source_ref": "kpi_bad_ratio"},
    }
    result = draft_delta(_existing_spec(), _planning_context(), "renewal percentage",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "invalid"
    assert result.would_validate is False
    assert any("formula_incoherent" in e for e in result.validation_errors)


def test_draft_delta_repairs_validation_rejection_on_retry() -> None:
    # Regression: draft_delta originally had no repair chance at all — a
    # single fixable model mistake (forgetting `measure`) failed immediately
    # instead of getting one correction attempt, unlike the batch planner.
    bad = {
        "new_kpi": {"kpi_id": "kpi_avg_value", "operation": "average", "format": "currency"},  # no measure
        "new_visualization": {"chart_id": "c1", "chart_type": "kpi_card", "source_ref": "kpi_avg_value"},
    }
    fixed = {
        "new_kpi": {"kpi_id": "kpi_avg_value", "operation": "average", "measure": "contract_value",
                   "format": "currency"},
        "new_visualization": {"chart_id": "c1", "chart_type": "kpi_card", "source_ref": "kpi_avg_value"},
    }
    result = draft_delta(_existing_spec(), _planning_context(), "average contract value",
                         broker=_FakeBroker(), complete_json_fn=_sequential_complete_json([bad, fixed]))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_kpi.measure == "contract_value"
    assert result.attempts == 2


def test_draft_delta_repairs_grounding_level_drop_on_retry() -> None:
    # A dropped new_visualization (invented chart type) has no merged spec
    # to validate — the repair hint must come from ground_delta's own
    # warnings instead, and still get the one retry.
    bad = {"new_visualization": {"chart_id": "c1", "chart_type": "3d_globe", "source_ref": "kpi_renewal_rate"}}
    fixed = {"new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_renewal_rate"}}
    result = draft_delta(_existing_spec(), _planning_context(), "renewal rate",
                         broker=_FakeBroker(), complete_json_fn=_sequential_complete_json([bad, fixed]))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_visualization.chart_type == "bar"


def test_draft_delta_gives_up_after_one_retry() -> None:
    still_bad = {"new_visualization": {"chart_id": "c1", "chart_type": "3d_globe", "source_ref": "kpi_renewal_rate"}}
    result = draft_delta(_existing_spec(), _planning_context(), "renewal rate",
                         broker=_FakeBroker(),
                         complete_json_fn=_sequential_complete_json([still_bad, still_bad]))
    assert result.status == "invalid"
    assert result.items.new_visualization is None


def test_draft_delta_malformed_response_is_controlled_error() -> None:
    result = draft_delta(_existing_spec(), _planning_context(), "anything",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json({}))
    assert result.status == "controlled_error"
    assert result.error_code == "malformed_json"


# ── ground_delta — cross-reference to a newly-drafted item ───────────────

def test_ground_delta_allows_visualization_to_cite_newly_drafted_kpi() -> None:
    raw = {
        "new_kpi": {"kpi_id": "kpi_new", "operation": "count"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_new"},
    }
    items = ground_delta(raw, existing_kpi_ids=set(), existing_analysis_ids=set(), existing_chart_ids=set(),
                         approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
                         approved_charts=APPROVED_CHARTS)
    assert items.new_kpi is not None and items.new_kpi.kpi_id == "kpi_new"
    assert items.new_visualization is not None
    assert items.new_visualization.source_ref == "kpi_new"


def test_ground_delta_drops_dangling_reference_to_unknown_kpi() -> None:
    raw = {"new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_does_not_exist"}}
    items = ground_delta(raw, existing_kpi_ids={"kpi_renewal_rate"}, existing_analysis_ids=set(),
                         existing_chart_ids=set(),
                         approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
                         approved_charts=APPROVED_CHARTS)
    assert items.new_visualization is None
    assert any(w.code == "dangling_reference" for w in items.warnings)


# ── id-collision safety net ───────────────────────────────────────────────
# Regression: the model re-using a generic id (e.g. "chart1") that already
# exists in the spec being extended used to silently produce TWO components
# sharing one chart_id, corrupting composition (duplicate_component_id).

def test_ground_delta_dedupes_colliding_chart_id() -> None:
    raw = {"new_visualization": {"chart_id": "chart_kpi_card", "chart_type": "bar",
                                 "source_ref": "analysis_renewal_by_region"}}
    items = ground_delta(raw, existing_kpi_ids={"kpi_renewal_rate"},
                         existing_analysis_ids={"analysis_renewal_by_region"},
                         existing_chart_ids={"chart_kpi_card"},  # collides with the existing spec's chart
                         approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
                         approved_charts=APPROVED_CHARTS)
    assert items.new_visualization is not None
    assert items.new_visualization.chart_id == "chart_kpi_card_2"


def test_ground_delta_dedupes_colliding_kpi_id_and_keeps_references_consistent() -> None:
    # The model reuses "kpi_renewal_rate" (an EXISTING kpi_id) for its NEW
    # kpi — the rename must also follow through to new_analysis.metric and
    # new_visualization.source_ref, or the reference breaks.
    raw = {
        "new_kpi": {"kpi_id": "kpi_renewal_rate", "operation": "average", "measure": "contract_value"},
        "new_analysis": {"analysis_id": "analysis_avg", "operation": "group_by",
                        "group_by": ["region"], "metric": "kpi_renewal_rate"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_renewal_rate"},
    }
    items = ground_delta(raw, existing_kpi_ids={"kpi_renewal_rate"},
                         existing_analysis_ids={"analysis_renewal_by_region"}, existing_chart_ids=set(),
                         approved_columns=APPROVED_COLUMNS, approved_operations=APPROVED_OPS,
                         approved_charts=APPROVED_CHARTS)
    assert items.new_kpi is not None
    new_id = items.new_kpi.kpi_id
    assert new_id != "kpi_renewal_rate"  # renamed, not overwriting the existing one
    assert items.new_analysis.metric == new_id  # reference followed the rename
    assert items.new_visualization.source_ref == new_id  # reference followed the rename


def test_dedupe_delta_items_used_by_confirm_keeps_references_consistent() -> None:
    from aryx.andie_planner.delta import _dedupe_delta_items
    existing = _existing_spec()
    items = DeltaSpecItems(
        new_kpi=Kpi(kpi_id="kpi_renewal_rate", operation="average", measure="contract_value"),
        new_analysis=Analysis(analysis_id="analysis_avg", operation="group_by", group_by=["region"],
                              metric="kpi_renewal_rate"),
        new_visualization=Visualization(chart_id="chart_kpi_card", chart_type="bar",
                                        source_ref="kpi_renewal_rate"),
    )
    deduped = _dedupe_delta_items(items, existing)
    assert deduped.new_kpi.kpi_id != "kpi_renewal_rate"
    assert deduped.new_analysis.metric == deduped.new_kpi.kpi_id
    assert deduped.new_visualization.source_ref == deduped.new_kpi.kpi_id
    assert deduped.new_visualization.chart_id != "chart_kpi_card"


# ── workspace-scope mode ──────────────────────────────────────────────────

def _workspace_planning_context():
    return SimpleNamespace(
        dataset_id="workspace_1", dataset_version="v1", domain="mixed",
        datasets=[SimpleNamespace(
            dataset_id="dataset_a",
            approved_columns=[
                SimpleNamespace(name="region", type="categorical", sample_values=["North", "South"]),
                SimpleNamespace(name="amount", type="numeric", sample_values=["100.0"]),
            ],
        )],
        approved_graph_paths=[], supported_operations=APPROVED_OPS, supported_charts=APPROVED_CHARTS,
    )


def _existing_workspace_spec() -> DashboardSpec:
    return DashboardSpec(
        spec_id="dashboard_spec_workspace_1_v1", dataset_id="workspace_1", dataset_version="v1",
        business_questions=[BusinessQuestion(question_id="bq_1", text="What is total amount?")],
        kpis=[Kpi(kpi_id="kpi_total_amount", dataset_id="dataset_a", operation="sum", measure="amount")],
        analyses=[],
        visualizations=[Visualization(chart_id="c0", chart_type="kpi_card", source_ref="kpi_total_amount")],
    )


def test_draft_delta_workspace_mode_requires_dataset_id_on_new_items() -> None:
    payload = {
        "new_analysis": {"analysis_id": "analysis_amount_by_region", "dataset_id": "dataset_a",
                        "operation": "group_by", "group_by": ["region"], "metric": "kpi_total_amount"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "analysis_amount_by_region"},
    }
    result = draft_delta(_existing_workspace_spec(), _workspace_planning_context(), "amount by region",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_analysis.dataset_id == "dataset_a"


def test_draft_delta_workspace_mode_drops_analysis_with_unknown_dataset() -> None:
    payload = {
        "new_analysis": {"analysis_id": "analysis_amount_by_region", "dataset_id": "dataset_ghost",
                        "operation": "group_by", "group_by": ["region"], "metric": "kpi_total_amount"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "kpi_total_amount"},
    }
    result = draft_delta(_existing_workspace_spec(), _workspace_planning_context(), "amount by region",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.items.new_analysis is None
    assert any(w.code == "unknown_dataset" for w in result.items.warnings)


# ── graph_relation (ask-to-visualize parity with the batch planner) ───────

def test_build_delta_prompt_offers_graph_path_id_for_new_analysis() -> None:
    # Regression: build_delta_prompt gained graph_path_hints/graph_quality_notes
    # as RESOURCES, but its own "Return a JSON object" schema text initially
    # forgot to list graph_path_id as an available new_analysis field — the
    # model had no signal it could actually use graph_relation here, even
    # though ground_delta already supports grounding it. Asserting on the
    # exact field-list substring (not just "graph_path_id" anywhere in the
    # prompt) so this can't pass on a stray mention in unrelated prose.
    _, user = build_delta_prompt(
        existing_kpis=[], existing_analyses=[], approved_columns=APPROVED_COLUMNS,
        approved_graph_paths=["path_contract_manager"], supported_operations=APPROVED_OPS,
        supported_charts=APPROVED_CHARTS, request_text="contracts by manager",
    )
    assert "new_analysis: {analysis_id, operation, " in user
    assert "start_column?, end_column?, graph_path_id?}" in user


def test_build_delta_prompt_ends_with_sample_values_self_check() -> None:
    _, user = build_delta_prompt(
        existing_kpis=[], existing_analyses=[], approved_columns=APPROVED_COLUMNS,
        approved_graph_paths=[], supported_operations=APPROVED_OPS,
        supported_charts=APPROVED_CHARTS, request_text="renewed value by region",
    )
    assert "re-check that its column actually has sample_values" in user


def test_build_delta_prompt_states_the_only_implemented_zero_denominator_policy() -> None:
    _, user = build_delta_prompt(
        existing_kpis=[], existing_analyses=[], approved_columns=APPROVED_COLUMNS,
        approved_graph_paths=[], supported_operations=APPROVED_OPS,
        supported_charts=APPROVED_CHARTS, request_text="renewal rate by region",
    )
    assert "MUST be exactly the string 'return_null_with_warning'" in user


def test_build_delta_prompt_workspace_mode_notes_graph_relation_dataset_id_exception() -> None:
    _, user = build_delta_prompt(
        existing_kpis=[], existing_analyses=[], datasets=[{"dataset_id": "dataset_a", "approved_columns": []}],
        approved_graph_paths=["path_contract_manager"], supported_operations=APPROVED_OPS,
        supported_charts=APPROVED_CHARTS, request_text="contracts by manager",
    )
    assert "start_column?, end_column?, graph_path_id?}" in user
    assert "graph_relation, which spans the whole workspace graph" in user


def test_draft_delta_grounds_graph_relation_new_analysis() -> None:
    ctx = _planning_context()
    ctx.approved_graph_paths = ["path_contract_manager"]
    ctx.supported_operations = [*APPROVED_OPS, "graph_relation"]
    payload = {
        "new_analysis": {"analysis_id": "analysis_by_manager", "operation": "graph_relation",
                        "graph_path_id": "path_contract_manager"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "analysis_by_manager"},
    }
    result = draft_delta(_existing_spec(), ctx, "contracts by manager",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.status == "valid", result.validation_errors
    assert result.items.new_analysis.graph_path_id == "path_contract_manager"
    assert result.items.new_analysis.group_by == [] and result.items.new_analysis.metric is None


def test_draft_delta_rejects_invented_graph_path_id() -> None:
    ctx = _planning_context()
    ctx.approved_graph_paths = ["path_contract_manager"]
    ctx.supported_operations = [*APPROVED_OPS, "graph_relation"]
    payload = {
        "new_analysis": {"analysis_id": "analysis_by_manager", "operation": "graph_relation",
                        "graph_path_id": "path_invented"},
        "new_visualization": {"chart_id": "c1", "chart_type": "bar", "source_ref": "analysis_by_manager"},
    }
    result = draft_delta(_existing_spec(), ctx, "contracts by manager",
                         broker=_FakeBroker(), complete_json_fn=_fake_complete_json(payload))
    assert result.items.new_analysis is None
    assert any(w.code == "invalid_graph_path" for w in result.items.warnings)


# ── merge / preview helpers ───────────────────────────────────────────────

def test_merge_spec_appends_without_mutating_original() -> None:
    existing = _existing_spec()
    items = DeltaSpecItems(new_visualization=Visualization(
        chart_id="chart_new", chart_type="bar", source_ref="analysis_renewal_by_region"))
    merged = _merge_spec(existing, items)
    assert len(merged.visualizations) == 2
    assert len(existing.visualizations) == 1  # original untouched


def test_preview_text_reads_naturally_for_existing_reference() -> None:
    existing = _existing_spec()
    items = DeltaSpecItems(new_visualization=Visualization(
        chart_id="chart_new", chart_type="bar", source_ref="analysis_renewal_by_region"))
    text = _preview_text(items, existing)
    assert "bar" in text and "region" in text


def test_preview_text_explains_an_unsupportable_request() -> None:
    from aryx.andie_planner.models import SpecWarning
    items = DeltaSpecItems(warnings=[SpecWarning(code="unsupported_chart_type", detail="c1: '3d_globe'")])
    text = _preview_text(items, _existing_spec())
    assert "Could not draft a chart" in text

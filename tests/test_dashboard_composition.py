"""Tests for Dashboard Composition (C14) — pure, no DB, no real LLM.

compose.py is exercised directly against real DashboardSpec/ExecutionRun
objects (not mocked). narrate.py's LLM call is stubbed with a fake
complete_json_fn — what's under test is the strict validation/fallback
around it, not any real provider.
"""
from __future__ import annotations

from aryx.analysis_execution.models import AnalysisResult, AnalysisResultRow, ExecutionRun, KpiResult
from aryx.andie_planner.models import Analysis, DashboardSpec, Kpi, Visualization
from aryx.dashboard_composition.compose import (
    _KPI_CARD_TYPE, _attach_warnings, _build_components, _group_into_sections,
    _prioritize, compose, revalidate,
)
from aryx.dashboard_composition.narrate import apply_titles, suggest_titles

DATASET = "dataset_contracts"


def _spec() -> DashboardSpec:
    return DashboardSpec(
        spec_id="spec_1", dataset_id=DATASET, dataset_version="v1",
        kpis=[
            Kpi(kpi_id="kpi_renewal_rate", dataset_id=DATASET, operation="ratio"),
            Kpi(kpi_id="kpi_renewed_value", dataset_id=DATASET, operation="sum", measure="contract_value"),
        ],
        analyses=[
            Analysis(analysis_id="analysis_renewal_by_region", operation="group_by",
                     dataset_id=DATASET, group_by=["region"], metric="kpi_renewal_rate"),
        ],
        visualizations=[
            Visualization(chart_id="chart_1", chart_type="kpi_card", source_ref="kpi_renewal_rate"),
            Visualization(chart_id="chart_2", chart_type="kpi_card", source_ref="kpi_renewed_value"),
            Visualization(chart_id="chart_3", chart_type="bar_chart",
                         source_ref="analysis_renewal_by_region"),
        ],
    )


def _run(with_warnings: bool = False) -> ExecutionRun:
    validation = None
    if with_warnings:
        validation = {
            "warnings": [
                {"code": "small_sample_size", "reference": "analysis_renewal_by_region:West",
                 "details": {"sample_size": 15, "threshold": 30}},
            ],
            "eligible_for_dashboard": True,
        }
    return ExecutionRun(
        execution_run_id="run_1", execution_plan_id="plan_1", spec_id="spec_1",
        dataset_id=DATASET, dataset_version="v1", status="completed",
        kpi_results=[
            KpiResult(kpi_id="kpi_renewal_rate", value=0.62, display_value="62%", sample_size=340),
            KpiResult(kpi_id="kpi_renewed_value", value=4500.0, display_value="$4,500", sample_size=3),
        ],
        analysis_results=[
            AnalysisResult(analysis_id="analysis_renewal_by_region", group_column="region", rows=[
                AnalysisResultRow(group_value="West", value=0.4, sample_size=15),
                AnalysisResultRow(group_value="East", value=0.6, sample_size=80),
            ]),
        ],
        validation=validation,
    )


# ── step 1-2: build components ────────────────────────────────────────────

def test_build_components_binds_only_computed_results() -> None:
    spec = _spec()
    spec.visualizations.append(Visualization(chart_id="chart_ghost", chart_type="bar_chart",
                                              source_ref="analysis_nonexistent"))
    components, issues = _build_components(spec, _run())
    assert {c.source_ref for c in components} == {
        "kpi_renewal_rate", "kpi_renewed_value", "analysis_renewal_by_region"}
    assert any(i.code == "missing_computed_result" and i.reference == "analysis_nonexistent"
              for i in issues)


def test_kpi_card_must_bind_to_a_kpi() -> None:
    spec = _spec()
    spec.visualizations.append(Visualization(chart_id="chart_bad", chart_type="kpi_card",
                                              source_ref="analysis_renewal_by_region"))
    components, issues = _build_components(spec, _run())
    assert not any(c.source_ref == "analysis_renewal_by_region" and c.type == _KPI_CARD_TYPE
                  for c in components)
    assert any(i.code == "chart_type_mismatch" and i.reference == "chart_bad" for i in issues)


# ── step 3-4: layout + prioritization ──────────────────────────────────────

def test_layout_constraint_caps_charts_never_kpi_cards() -> None:
    from aryx.dashboard_composition.compose import _apply_layout_constraints
    from aryx.dashboard_composition.models import DashboardComponent
    components = [
        DashboardComponent(component_id="c1", type=_KPI_CARD_TYPE, source_ref="k1", position=1),
        DashboardComponent(component_id="c2", type="bar_chart", source_ref="a1", position=2),
        DashboardComponent(component_id="c3", type="bar_chart", source_ref="a2", position=3),
    ]
    kept, issues = _apply_layout_constraints(components, maximum_primary_charts=1)
    assert [c.component_id for c in kept] == ["c1", "c2"]
    assert any(i.code == "layout_limit_exceeded" and i.reference == "c3" for i in issues)


def test_prioritize_orders_kpi_cards_before_charts() -> None:
    from aryx.dashboard_composition.models import DashboardComponent
    components = [
        DashboardComponent(component_id="chart", type="bar_chart", source_ref="a1", position=0),
        DashboardComponent(component_id="card", type=_KPI_CARD_TYPE, source_ref="k1", position=0),
    ]
    ordered = _prioritize(components)
    assert [c.component_id for c in ordered] == ["card", "chart"]
    assert [c.position for c in ordered] == [1, 2]


# ── step 5: grouping ───────────────────────────────────────────────────────

def test_group_into_sections_groups_charts_by_analysis_group_column() -> None:
    spec = _spec()
    components, _issues = _build_components(spec, _run())
    components = _prioritize(components)
    sections = _group_into_sections(components, spec)
    by_id = {s.section_id: s for s in sections}
    assert "section_summary" in by_id
    assert {c.source_ref for c in by_id["section_summary"].components} == \
        {"kpi_renewal_rate", "kpi_renewed_value"}
    assert "section_region" in by_id
    assert by_id["section_region"].title == "By Region"
    assert [c.source_ref for c in by_id["section_region"].components] == ["analysis_renewal_by_region"]


# ── warnings + revalidation ────────────────────────────────────────────────

def test_attach_warnings_pulls_c13_warning_onto_the_right_component() -> None:
    spec = _spec()
    run = _run(with_warnings=True)
    components, _issues = _build_components(spec, run)
    components = _prioritize(components)
    sections = _group_into_sections(components, spec)
    _attach_warnings(sections, run)
    region_component = next(c for s in sections for c in s.components
                            if c.source_ref == "analysis_renewal_by_region")
    assert region_component.warning_refs == ["small_sample_size:West"]
    kpi_component = next(c for s in sections for c in s.components if c.source_ref == "kpi_renewal_rate")
    assert kpi_component.warning_refs == []


def test_revalidate_flags_duplicate_component_id() -> None:
    from aryx.dashboard_composition.models import DashboardComponent, DashboardSection
    sections = [
        DashboardSection(section_id="s1", title="A", components=[
            DashboardComponent(component_id="dup", type=_KPI_CARD_TYPE, source_ref="k1", position=1)]),
        DashboardSection(section_id="s2", title="B", components=[
            DashboardComponent(component_id="dup", type="bar_chart", source_ref="a1", position=2)]),
    ]
    issues = revalidate(sections)
    assert any(i.code == "duplicate_component_id" and i.reference == "dup" for i in issues)


def test_revalidate_flags_empty_section_title() -> None:
    from aryx.dashboard_composition.models import DashboardSection
    issues = revalidate([DashboardSection(section_id="s1", title="  ", components=[])])
    assert any(i.code == "empty_section_title" and i.reference == "s1" for i in issues)


# ── end-to-end compose() ──────────────────────────────────────────────────

def test_compose_end_to_end_matches_doc_shape() -> None:
    spec = _spec()
    sections, issues = compose(spec, _run(with_warnings=True))
    assert issues == []
    assert [s.section_id for s in sections] == ["section_summary", "section_region"]
    summary = sections[0]
    assert [c.component_id for c in summary.components] == \
        ["component_kpi_renewal_rate", "component_kpi_renewed_value"]
    region = sections[1]
    assert region.components[0].component_id == "component_analysis_renewal_by_region"
    assert region.components[0].warning_refs == ["small_sample_size:West"]


# ── narrate.py: strict LLM-suggestion validation ──────────────────────────

def _sections_for_narration():
    spec = _spec()
    sections, _issues = compose(spec, _run())
    return sections


def test_suggest_titles_returns_none_when_llm_call_raises() -> None:
    def _boom(*_a, **_kw):
        raise RuntimeError("provider down")
    result = suggest_titles(_sections_for_narration(), "sales leadership", "",
                            broker=object(), complete_json_fn=_boom)
    assert result is None


def test_suggest_titles_returns_none_on_section_id_mismatch() -> None:
    def _fake(*_a, **_kw):
        return {"dashboard_title": "Contract Renewal Performance",
               "section_titles": {"section_summary": "Renewal Summary",
                                  "section_invented": "Made Up"}}
    result = suggest_titles(_sections_for_narration(), "sales leadership", "",
                            broker=object(), complete_json_fn=_fake)
    assert result is None


def test_suggest_titles_accepts_a_valid_response() -> None:
    def _fake(*_a, **_kw):
        return {"dashboard_title": "Contract Renewal Performance",
               "section_titles": {"section_summary": "Renewal Summary",
                                  "section_region": "Regional Performance"}}
    result = suggest_titles(_sections_for_narration(), "sales leadership", "",
                            broker=object(), complete_json_fn=_fake)
    assert result == ("Contract Renewal Performance",
                      {"section_summary": "Renewal Summary", "section_region": "Regional Performance"})


def test_apply_titles_only_changes_title_never_components() -> None:
    sections = _sections_for_narration()
    original_components = sections[0].components
    renamed = apply_titles(sections, {"section_summary": "Renewal Summary",
                                      "section_region": "Regional Performance"})
    assert renamed[0].title == "Renewal Summary"
    assert renamed[0].components == original_components
    assert renamed[0].section_id == sections[0].section_id

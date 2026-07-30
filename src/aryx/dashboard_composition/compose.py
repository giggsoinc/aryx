"""C14 — Dashboard Composition: arrange an approved spec's validated results
into an ordered dashboard model.

Can arrange artifacts — order, grouping, section titles — but can NEVER
alter a governed value, formula, axis, or ID. Every component's
`source_ref` is one of the spec's own kpi_id/analysis_id (never invented),
and every value it renders comes from the already-validated ExecutionRun
(C12/C13) — this module never computes anything itself. The one optional
LLM step (narrate.py) may only rename sections and reorder within the
structure this module already built; it cannot add, remove, or rebind a
component (see narrate.py's own module docstring for the enforcement).
"""
from __future__ import annotations

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.dashboard_composition.models import CompositionIssue, DashboardComponent, DashboardSection

DEFAULT_MAX_COLUMNS = 3
DEFAULT_MAX_PRIMARY_CHARTS = 6
_KPI_CARD_TYPE = "kpi_card"


def _has_computed_result(run: ExecutionRun, source_ref: str) -> bool:
    return (any(k.kpi_id == source_ref for k in run.kpi_results)
           or any(a.analysis_id == source_ref for a in run.analysis_results))


def _build_components(
    spec: DashboardSpec, run: ExecutionRun,
) -> tuple[list[DashboardComponent], list[CompositionIssue]]:
    """Steps 1-2: one component per approved visualization, bound only if
    its source_ref actually has a computed result — never fabricated."""
    components: list[DashboardComponent] = []
    issues: list[CompositionIssue] = []
    kpi_ids = {k.kpi_id for k in spec.kpis}
    for viz in spec.visualizations:
        if viz.source_ref not in kpi_ids and viz.chart_type == _KPI_CARD_TYPE:
            issues.append(CompositionIssue(code="chart_type_mismatch", reference=viz.chart_id,
                                           detail="kpi_card must bind to a kpi_id"))
            continue
        if not _has_computed_result(run, viz.source_ref):
            issues.append(CompositionIssue(code="missing_computed_result", reference=viz.source_ref))
            continue
        components.append(DashboardComponent(
            component_id=f"component_{viz.source_ref}", type=viz.chart_type,
            source_ref=viz.source_ref, position=0))
    return components, issues


def _apply_layout_constraints(
    components: list[DashboardComponent], maximum_primary_charts: int,
) -> tuple[list[DashboardComponent], list[CompositionIssue]]:
    """Step 3: KPI cards are never capped (they're the mandatory summary);
    non-card "primary charts" are capped, keeping the first N in their
    approved order — dropped ones are reported, never silently discarded."""
    cards = [c for c in components if c.type == _KPI_CARD_TYPE]
    charts = [c for c in components if c.type != _KPI_CARD_TYPE]
    kept, dropped = charts[:maximum_primary_charts], charts[maximum_primary_charts:]
    issues = [CompositionIssue(code="layout_limit_exceeded", reference=c.component_id,
                               detail=f"maximum_primary_charts={maximum_primary_charts}")
             for c in dropped]
    return [*cards, *kept], issues


def _prioritize(components: list[DashboardComponent]) -> list[DashboardComponent]:
    """Step 4: mandatory KPI cards first, charts after — positions renumbered."""
    ordered = [c for c in components if c.type == _KPI_CARD_TYPE] + \
        [c for c in components if c.type != _KPI_CARD_TYPE]
    return [c.model_copy(update={"position": i + 1}) for i, c in enumerate(ordered)]


def _analysis_group_column(spec: DashboardSpec, analysis_id: str) -> str:
    return next((a.group_by[0] for a in spec.analyses if a.analysis_id == analysis_id and a.group_by), "")


def _group_into_sections(
    components: list[DashboardComponent], spec: DashboardSpec,
) -> list[DashboardSection]:
    """Step 5: KPI cards share one summary section; each remaining chart is
    grouped by the group_by column of the analysis it renders (charts
    bound directly to a KPI, not an analysis, fall back to the summary
    section too). Deterministic, mechanical titles — narrate.py (step 6,
    optional) may improve them, never restructure the grouping itself."""
    cards = [c for c in components if c.type == _KPI_CARD_TYPE]
    sections: list[DashboardSection] = []
    if cards:
        sections.append(DashboardSection(section_id="section_summary", title="KPI Summary",
                                         components=cards))

    by_group_column: dict[str, list[DashboardComponent]] = {}
    ungrouped: list[DashboardComponent] = []
    for c in components:
        if c.type == _KPI_CARD_TYPE:
            continue
        col = _analysis_group_column(spec, c.source_ref)
        if col:
            by_group_column.setdefault(col, []).append(c)
        else:
            ungrouped.append(c)

    for col in sorted(by_group_column):
        section_id = f"section_{col}"
        sections.append(DashboardSection(section_id=section_id, title=f"By {col.title()}",
                                         components=by_group_column[col]))
    if ungrouped:
        sections.append(DashboardSection(section_id="section_charts", title="Additional Charts",
                                         components=ungrouped))
    return sections


def _attach_warnings(sections: list[DashboardSection], run: ExecutionRun) -> None:
    """Pull C13's warnings forward onto the component that owns them —
    mutates in place. A per-group analysis warning (e.g. small_sample_size
    on one region) attaches only to that component, not the whole section."""
    validation = run.validation or {}
    warnings = validation.get("warnings", [])
    by_source_ref: dict[str, list[str]] = {}
    for w in warnings:
        code, reference = w.get("code", ""), w.get("reference", "")
        source_ref = reference.split(":", 1)[0] if reference else ""
        suffix = reference.split(":", 1)[1] if ":" in reference else ""
        by_source_ref.setdefault(source_ref, []).append(f"{code}:{suffix}" if suffix else code)
    for section in sections:
        for component in section.components:
            component.warning_refs = by_source_ref.get(component.source_ref, [])


def revalidate(model_sections: list[DashboardSection]) -> list[CompositionIssue]:
    """Step 7: structural self-check — duplicate component IDs, empty
    titles, and (defense-in-depth) a source_ref this composition never
    actually built a component for. Runs again after narrate.py (step 6)
    since that's the one step that could otherwise corrupt the structure."""
    issues: list[CompositionIssue] = []
    seen_ids: set[str] = set()
    for section in model_sections:
        if not section.title.strip():
            issues.append(CompositionIssue(code="empty_section_title", reference=section.section_id))
        for component in section.components:
            if component.component_id in seen_ids:
                issues.append(CompositionIssue(code="duplicate_component_id",
                                               reference=component.component_id))
            seen_ids.add(component.component_id)
    return issues


def compose(
    spec: DashboardSpec, run: ExecutionRun, *,
    maximum_primary_charts: int = DEFAULT_MAX_PRIMARY_CHARTS,
) -> tuple[list[DashboardSection], list[CompositionIssue]]:
    """Steps 1-5 + 7: the full deterministic composition. Always runs, even
    when the optional LLM step (narrate.py) is also used — it's the
    fallback structure, not a first draft to be discarded.

    `maximum_columns` (a layout hint for the frontend, not a grouping rule)
    is stored directly on the DashboardModel by run.py's glue rather than
    threaded through here — it doesn't change WHICH components/sections
    exist, only how the caller renders them."""
    components, issues = _build_components(spec, run)
    components, layout_issues = _apply_layout_constraints(components, maximum_primary_charts)
    issues.extend(layout_issues)
    components = _prioritize(components)
    sections = _group_into_sections(components, spec)
    _attach_warnings(sections, run)
    issues.extend(revalidate(sections))
    if not components and not spec.visualizations:
        # Not a structural defect (nothing here is corrupted), but silently
        # returning a "valid" model with zero sections reads as broken to
        # anyone downstream — surface WHY it's empty instead.
        issues.append(CompositionIssue(
            code="no_visualizations",
            detail="the approved spec declared no visualizations to compose "
                   "(KPIs/analyses may still have real computed results — see the execution run)"))
    return sections, issues

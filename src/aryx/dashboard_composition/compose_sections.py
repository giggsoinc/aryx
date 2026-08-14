"""Dashboard Composition (C14) — sections: steps 5 and 7.

Groups bound components into sections with deterministic, mechanical titles
(narrate.py may improve them, never restructure the grouping itself), and
provides the structural self-check (revalidate) run both before and after
any optional LLM narration. See compose.py's module docstring for the full
C14 contract this serves.
"""
from __future__ import annotations

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.dashboard_composition.compose_components import _KPI_CARD_TYPE
from aryx.dashboard_composition.models import CompositionIssue, DashboardComponent, DashboardSection


def _analysis_group_column(spec: DashboardSpec, analysis_id: str) -> str:
    """The analysis's first group_by column, "" if it has none."""
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

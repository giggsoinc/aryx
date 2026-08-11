"""Dashboard Composition (C14) — components: steps 1-4.

Binds one DashboardComponent per approved visualization to its real computed
result (never fabricated), then caps and orders the result deterministically.
See compose.py's module docstring for the full C14 contract this serves.
"""
from __future__ import annotations

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.dashboard_composition.models import CompositionIssue, DashboardComponent

DEFAULT_MAX_PRIMARY_CHARTS = 12
_KPI_CARD_TYPE = "kpi_card"


def _has_computed_result(run: ExecutionRun, source_ref: str) -> bool:
    """True if `source_ref` has a real computed KPI or analysis result in
    this run — a component with no result is dropped, never shown empty."""
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
            # Keyed on chart_id, not source_ref: a spec legitimately renders
            # the same kpi_id/analysis_id through more than one
            # visualization (e.g. a chart AND a table for the same
            # analysis) — chart_id is the field C09/the planner author as
            # the per-visualization identifier, so it's the correct
            # uniqueness key here, not the thing being visualized.
            component_id=f"component_{viz.chart_id}", type=viz.chart_type,
            source_ref=viz.source_ref, position=0, compare_ref=viz.compare_ref,
            axis_refs=viz.axis_refs))
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

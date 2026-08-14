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

Split across three files for readability: this module is the step 1-5/7
orchestrator; compose_components.py builds and caps components (steps 1-4);
compose_sections.py groups them into sections and self-checks the result
(steps 5/7).
"""
from __future__ import annotations

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.dashboard_composition.compose_components import (
    DEFAULT_MAX_PRIMARY_CHARTS,
    _apply_layout_constraints,
    _build_components,
    _prioritize,
)
from aryx.dashboard_composition.compose_sections import _attach_warnings, _group_into_sections, revalidate
from aryx.dashboard_composition.models import CompositionIssue, DashboardSection

DEFAULT_MAX_COLUMNS = 3


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

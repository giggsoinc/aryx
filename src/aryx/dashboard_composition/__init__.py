"""Dashboard Composition (C14).

Arranges an approved spec's C12/C13-validated results into an ordered,
readable dashboard model. Can arrange artifacts — order, grouping, section
titles — but can NEVER alter a governed value, formula, axis, or ID. Hybrid:
an optional LLM step (narrate.py) may suggest better titles, strictly
validated and always falling back to the deterministic composition if
unavailable or invalid. On-demand only (POST /dashboard-model/run), gated
on C13's eligible_for_dashboard.
"""

from aryx.dashboard_composition.compose import compose
from aryx.dashboard_composition.models import (
    CompositionIssue, DashboardComponent, DashboardModel, DashboardSection,
)
from aryx.dashboard_composition.run import compose_dashboard

__all__ = [
    "compose_dashboard", "compose",
    "DashboardModel", "DashboardSection", "DashboardComponent", "CompositionIssue",
]

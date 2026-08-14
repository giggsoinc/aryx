"""Andie Jr Planning Orchestrator (C08).

Translates business intent + grounded context (C07's planning_context) into a
strict, NON-EXECUTABLE dashboard specification: business questions, KPI
definitions, analyses, and visualizations. Andie decides WHAT to ask and HOW to
visualize it — it never computes a KPI value and never emits executable code.

LLM policy: Yes, narrowly scoped. The model drafts candidate JSON; `ground.py`
is the actual enforcement of "no invention" — every column, operation, chart
type, and cross-reference is verified against the given planning_context in
plain code, and anything unsupported is stripped with a recorded warning. The
LLM's output is never trusted directly.
"""

from aryx.andie_planner.generate import assemble_spec
from aryx.andie_planner.ground import ground_spec
from aryx.andie_planner.models import DashboardSpec, PlannerResult

__all__ = ["assemble_spec", "ground_spec", "DashboardSpec", "PlannerResult"]

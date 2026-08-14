"""Frontend Dashboard Renderer (C15).

The actual rendering (KPI cards, bar charts, warning banners, accessible
markup) lives in apps/web — Frontend Engineering, no LLM, no server-side
compute, and it never recomputes a governed KPI formula client-side. This
package holds only the render-telemetry record the frontend reports after
each render (step 7 of the component's procedure).
"""

from aryx.dashboard_render.models import AccessibilityChecks, RenderTelemetry

__all__ = ["RenderTelemetry", "AccessibilityChecks"]

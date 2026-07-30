"""Data contracts for the Frontend Dashboard Renderer (C15).

The renderer itself lives entirely in apps/web (Frontend Engineering, no
LLM, no server-side compute) — it merges the persisted DashboardModel (C14)
with the already-computed ExecutionRun (C12/C13) into UI-ready values and
never recomputes a governed KPI formula client-side. This module is just the
telemetry record (step 7: "Capture render and interaction telemetry") the
frontend reports after each render — the only piece of C15 that touches
the backend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AccessibilityChecks(BaseModel):
    keyboard_navigation: Literal["passed", "failed"] = "passed"
    contrast: Literal["passed", "failed"] = "passed"
    text_alternatives: Literal["passed", "failed"] = "passed"


class RenderTelemetry(BaseModel):
    """One render event, as reported by the frontend after rendering a
    DashboardModel — an audit trail, not a gate; nothing here blocks or
    alters what was already rendered."""

    render_id: str
    dashboard_model_id: str
    schema_version: str = SCHEMA_VERSION
    render_status: Literal["success", "partial", "failed"] = "success"
    rendered_component_count: int = 0
    warning_count: int = 0
    unsupported_component_types: list[str] = Field(default_factory=list)
    accessibility_checks: AccessibilityChecks = Field(default_factory=AccessibilityChecks)
    created_at: datetime = Field(default_factory=_utcnow)

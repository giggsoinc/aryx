"""Data contracts for User Intent Capture (C01).

`UserIntentRequest` is the raw form input; `UserIntent` is the validated,
versioned output carrying a correlation id, validation status, warnings, and
completeness errors.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# Bumped whenever the shape of UserIntent changes so downstream components can
# reason about compatibility (safety guard: versioned schema).
# 1.1 — carries the customer brief's scope / objectives / proof questions so
#       planning and dashboard composition see the whole brief, not just
#       domain + aim. Previously these were dropped in intent/from_brief.py.
SCHEMA_VERSION = "1.1"


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class DateRange(BaseModel):
    """Optional analysis window. Values are normalized to ISO `YYYY-MM-DD`."""

    start: str = ""
    end: str = ""


class IntentPreferences(BaseModel):
    """Optional dashboard preferences — never block, only shape the request."""

    preferred_kpis: list[str] = Field(default_factory=list)
    preferred_dimensions: list[str] = Field(default_factory=list)
    preferred_chart_types: list[str] = Field(default_factory=list)
    target_audience: str = ""
    date_range: DateRange | None = None


class BriefContext(BaseModel):
    """The customer brief fields that have no scalar home on UserIntent.

    Captured BEFORE upload and carried through unchanged so planning and
    dashboard composition can honour what the customer actually asked for.
    """

    scope: str = Field(default="", description="IN/OUT boundary from the brief.")
    objectives: list[str] = Field(default_factory=list)
    questions: list[str] = Field(
        default_factory=list,
        description="Proof questions the dashboard must be able to answer.",
    )
    roles: list[str] = Field(
        default_factory=list, description="All participant roles from the brief."
    )


class UserIntentRequest(BaseModel):
    """Raw capture request as submitted by the intake form."""

    uploaded_file: str = Field(default="", description="Uploaded file reference.")
    domain: str = Field(default="", description="Business domain (required).")
    objective: str = Field(default="", description="Plain-language objective (required).")
    brief_context: BriefContext | None = Field(
        default=None, description="Full customer brief context, when intent came from a Brief."
    )
    preferred_kpis: list[str] = Field(default_factory=list)
    preferred_dimensions: list[str] = Field(default_factory=list)
    preferred_chart_types: list[str] = Field(default_factory=list)
    target_audience: str = ""
    date_range: DateRange | None = None
    request_id: str = Field(
        default="",
        description="Optional caller-supplied correlation id; generated if blank.",
    )


class UserIntent(BaseModel):
    """Validated, versioned intent handed to the next component."""

    request_id: str = Field(description="Correlation id for this request.")
    schema_version: str = Field(default=SCHEMA_VERSION)
    uploaded_file: str = ""
    domain: str
    objective: str
    brief_context: BriefContext = Field(default_factory=BriefContext)
    preferences: IntentPreferences
    validation_status: Literal["valid", "invalid"]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(
        default_factory=list,
        description="Completeness errors — non-empty means the request is blocked.",
    )
    created_at: datetime = Field(default_factory=_utcnow)

    def brief_context_text(self) -> str:
        """The customer brief MINUS the objective, as prompt-ready prose.

        Kept separate from `objective` on purpose. `objective` is persisted
        on the dashboard spec and rendered as the dashboard title, so it must
        stay a short human line. Scope, objectives, proof questions, and the
        full audience list steer planning instead, via the planner prompt's
        own `brief_context` input.

        Returns "" when no brief context was captured (pre-1.1 records, or a
        manual non-brief capture).
        """
        bc = self.brief_context
        lines: list[str] = []
        if bc.scope.strip():
            lines.append(f"Scope: {bc.scope.strip()}")
        if bc.objectives:
            lines.append("Customer objectives:")
            lines.extend(f"  - {o}" for o in bc.objectives)
        if bc.questions:
            lines.append("Proof questions the dashboard must answer:")
            lines.extend(f"  - {q}" for q in bc.questions)
        if len(bc.roles) > 1:
            lines.append(f"Audiences: {', '.join(bc.roles)}")
        return "\n".join(lines)

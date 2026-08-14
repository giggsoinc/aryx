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
SCHEMA_VERSION = "1.0"


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


class UserIntentRequest(BaseModel):
    """Raw capture request as submitted by the intake form."""

    uploaded_file: str = Field(default="", description="Uploaded file reference.")
    domain: str = Field(default="", description="Business domain (required).")
    objective: str = Field(default="", description="Plain-language objective (required).")
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
    preferences: IntentPreferences
    validation_status: Literal["valid", "invalid"]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(
        default_factory=list,
        description="Completeness errors — non-empty means the request is blocked.",
    )
    created_at: datetime = Field(default_factory=_utcnow)

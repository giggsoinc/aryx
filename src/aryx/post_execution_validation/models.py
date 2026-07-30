"""Data contracts for Post-Execution Validation (C13).

Confirms an ExecutionRun (C12) produced exactly what the approved spec (C08/
C09) and plan (C11) requested — result identity, recomputed arithmetic,
sample-size reconciliation, evidence lineage, no invented references, and
result shape. A structurally valid but numerically incorrect result is still
blocked (see checks.py's aggregation-correctness check). No LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

# Fixed threshold (not an authoring surface) — a sample below this size gets
# a warning, never a rejection; small samples are still real results.
SMALL_SAMPLE_THRESHOLD = 30


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CheckResult(BaseModel):
    check: str
    status: Literal["passed", "failed"]
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationWarning(BaseModel):
    code: str
    reference: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationError(BaseModel):
    code: str
    reference: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class PostExecutionReport(BaseModel):
    """The C13 verdict on one ExecutionRun."""

    validation_id: str
    stage: Literal["post_execution"] = "post_execution"
    schema_version: str = SCHEMA_VERSION
    status: Literal["approved", "approved_with_warnings", "rejected"] = "approved"
    checks: list[CheckResult] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)
    errors: list[ValidationError] = Field(default_factory=list)
    eligible_for_dashboard: bool = True
    created_at: datetime = Field(default_factory=_utcnow)

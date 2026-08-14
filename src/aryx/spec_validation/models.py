"""Data contracts for Pre-Execution Specification Validation (C09).

C09 sits parallel to C08's grounding (ground.py): it takes the already-grounded
DashboardSpec (and the warnings ground.py recorded while stripping unapproved
content) and decides whether the spec is safe to hand to a (not-yet-built)
compilation/execution stage. Where C08's philosophy is "strip and keep going,
warn", C09's is "reject and report" — a formal pass/fail gate with a bounded
single-retry repair loop back to the orchestrator.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

MAX_VALIDATION_ATTEMPTS = 2  # one initial pass + exactly one repair retry


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CheckResult(BaseModel):
    """Pass/fail outcome of one named C09 check."""

    check: str
    status: Literal["passed", "failed"]


class ValidationError(BaseModel):
    """One concrete defect found in the candidate spec."""

    code: str
    path: str = Field(default="", description="e.g. 'kpi:kpi_bad.measure'.")
    reference: str = ""


class ValidationWarning(BaseModel):
    """A non-blocking observation (e.g. small-group risk)."""

    code: str
    scope: str = ""


class RetryInfo(BaseModel):
    allowed: bool
    remaining_attempts: int
    target: str = "andie_orchestrator"


class ValidationReport(BaseModel):
    """The C09 verdict for one validation attempt on one candidate spec."""

    validation_id: str
    stage: Literal["pre_execution"] = "pre_execution"
    status: Literal["approved", "rejected"]
    checks: list[CheckResult] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)
    errors: list[ValidationError] = Field(default_factory=list)
    eligible_for_compilation: bool = False
    retry: RetryInfo | None = None
    attempt: int = 1
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = Field(default_factory=_utcnow)


class RepairErrorConstraint(BaseModel):
    """One error's correction constraints, handed back to the orchestrator."""

    path: str
    code: str
    invalid_value: str = Field(
        default="", description="The exact invented/invalid token the model "
        "used (e.g. a hallucinated column name) — echoed inline in the "
        "repair prompt so a weak model can find-and-replace it precisely, "
        "rather than re-guessing from a bare allowed-list.")
    allowed_columns: list[str] | None = None
    allowed_operations: list[str] | None = None
    allowed_replacements: list[str] | None = None


class RepairRequest(BaseModel):
    """Structured correction constraints sent to Andie for the one retry."""

    spec_id: str
    errors: list[RepairErrorConstraint] = Field(default_factory=list)


class ControlledFailure(BaseModel):
    """Terminal outcome once the single retry is exhausted. Never a raised
    exception, never an indefinite retry loop — this is the last word."""

    status: Literal["controlled_failure"] = "controlled_failure"
    code: str = "planner_validation_retry_exhausted"
    execution_started: bool = False
    validation_id: str = ""

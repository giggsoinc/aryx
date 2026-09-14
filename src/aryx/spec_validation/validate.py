"""Orchestrates the 10 C09 checks into one ValidationReport, and builds the
structured repair_request Andie needs for its one allowed correction attempt.

Pure and deterministic — no LLM, no I/O. The attempt-count/persistence/cap
enforcement lives in run.py; this module only knows how to grade ONE candidate.
"""
from __future__ import annotations

from aryx.andie_planner.models import DashboardSpec
from aryx.spec_validation.checks import ALL_CHECKS, ValidationContext
from aryx.spec_validation.models import (
    MAX_VALIDATION_ATTEMPTS,
    RepairErrorConstraint,
    RepairRequest,
    RetryInfo,
    ValidationError,
    ValidationReport,
)
from aryx.spec_validation.repair_messages import render_repair_line


def validate_spec(
    spec: DashboardSpec, ctx: ValidationContext, *, validation_id: str, attempt: int,
) -> tuple[ValidationReport, RepairRequest | None]:
    """Run all 10 checks and return (report, repair_request-or-None).

    `repair_request` is only produced when rejected; it is None for an
    approved report and (per the cap) also None once attempts are exhausted —
    the caller (run.py) is responsible for not requesting a repair beyond the
    allowed retry.
    """
    checks = []
    errors: list[ValidationError] = []
    warnings = []
    for fn in ALL_CHECKS:
        result, errs, warns = fn(spec, ctx)
        checks.append(result)
        errors.extend(errs)
        warnings.extend(warns)

    approved = not errors
    remaining = MAX_VALIDATION_ATTEMPTS - attempt
    report = ValidationReport(
        validation_id=validation_id,
        status="approved" if approved else "rejected",
        checks=checks, warnings=warnings, errors=errors,
        eligible_for_compilation=approved,
        retry=None if approved else RetryInfo(allowed=remaining > 0, remaining_attempts=max(remaining, 0)),
        attempt=attempt,
    )
    if approved or remaining <= 0:
        return report, None
    return report, _build_repair_request(spec, errors, ctx)


def _approved_column_names(ctx: ValidationContext) -> list[str]:
    if ctx.columns_by_dataset:
        names: set[str] = set()
        for cols in ctx.columns_by_dataset.values():
            names.update(cols)
        return sorted(names)
    return sorted(ctx.approved_columns)


def _build_repair_request(spec: DashboardSpec, errors: list[ValidationError],
                          ctx: ValidationContext) -> RepairRequest:
    approved_cols = _approved_column_names(ctx)
    approved_ops = sorted(ctx.approved_operations)
    safe_chart_replacements = sorted(c for c in ctx.approved_charts if c in ("bar", "table", "kpi_card"))

    constraints: list[RepairErrorConstraint] = []
    for err in errors:
        constraint = RepairErrorConstraint(path=err.path, code=err.code, invalid_value=err.reference)
        if err.code == "column_not_found":
            constraint.allowed_columns = approved_cols
        elif err.code == "unsupported_operation":
            constraint.allowed_operations = approved_ops
        elif err.code == "incompatible_chart_axes":
            constraint.allowed_replacements = safe_chart_replacements
        # formula_incoherent / missing_zero_denominator_policy /
        # unsupported_zero_denominator_policy get no allowed_* list — they're
        # rendered with a dedicated, structure-specific instruction below
        # instead of a bare "pick one of these operations" hint that doesn't
        # actually explain what's missing.
        constraints.append(constraint)
    return RepairRequest(spec_id=spec.spec_id, errors=constraints)


def repair_constraints_text(repair: RepairRequest) -> str:
    """Render a RepairRequest as plain-text constraints to append to the
    planner prompt for the one allowed correction attempt."""
    lines = [
        f"Your previous candidate (spec_id={repair.spec_id}) was REJECTED by "
        "pre-execution validation. Fix EXACTLY these problems — copy every "
        "replacement value verbatim, character-for-character, from the list "
        "given, never a close guess — and return a corrected JSON object "
        "with the same required keys:",
    ]
    lines.extend(render_repair_line(err) for err in repair.errors)
    return "\n".join(lines)

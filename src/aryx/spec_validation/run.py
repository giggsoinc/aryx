"""Glue: run C09 for one candidate spec, enforcing the attempt cap server-side.

Shared by both single-dataset and workspace-scope planning runs (see
andie_planner/run.py). Counts prior attempts for this validation_id BEFORE
running checks; once MAX_VALIDATION_ATTEMPTS is reached, short-circuits to a
rejected report with no further retry allowed — regardless of how many times
the caller calls this, the cap holds.
"""
from __future__ import annotations

import logging

from aryx.andie_planner.models import DashboardSpec
from aryx.spec_validation.checks import ValidationContext
from aryx.spec_validation.models import (
    MAX_VALIDATION_ATTEMPTS,
    RepairRequest,
    RetryInfo,
    ValidationReport,
)
from aryx.spec_validation.validate import validate_spec
from aryx.store.spec_validation_store import SpecValidationStore

logger = logging.getLogger(__name__)


def run_spec_validation(
    dsn: str, workspace_id: int, validation_id: str, spec: DashboardSpec,
    ctx: ValidationContext,
) -> tuple[ValidationReport, RepairRequest | None]:
    """Validate `spec` against `ctx`, capped at MAX_VALIDATION_ATTEMPTS server-side.

    Returns (report, repair_request). `repair_request` is non-None only when
    rejected AND a retry is still allowed.
    """
    store = SpecValidationStore(dsn, workspace_id)
    try:
        prior = store.count_attempts(validation_id)
        attempt = prior + 1
        if prior >= MAX_VALIDATION_ATTEMPTS:
            report = ValidationReport(
                validation_id=validation_id, status="rejected", checks=[], warnings=[],
                errors=[], eligible_for_compilation=False,
                retry=RetryInfo(allowed=False, remaining_attempts=0), attempt=attempt,
            )
            store.save(report, spec.spec_id)
            logger.warning("spec validation cap exceeded ws=%s validation_id=%s attempt=%d",
                           workspace_id, validation_id, attempt)
            return report, None

        report, repair = validate_spec(spec, ctx, validation_id=validation_id, attempt=attempt)
        store.save(report, spec.spec_id)
        logger.info("spec validation ws=%s validation_id=%s attempt=%d status=%s errors=%d",
                    workspace_id, validation_id, attempt, report.status, len(report.errors))
        return report, repair
    finally:
        store.close()

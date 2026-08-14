"""Glue: recompute + validate an ExecutionRun (C13). Chained onto C12,
right after `run_analysis_execution` produces a run — no separate trigger,
same convention as C09 chaining onto C08.
"""
from __future__ import annotations

import logging

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.execution_compiler.models import ExecutionPlan
from aryx.post_execution_validation.models import PostExecutionReport, ValidationError
from aryx.post_execution_validation.recompute import recompute
from aryx.post_execution_validation.validate import validate_execution
from aryx.profiler.models import DatasetProfile
from aryx.store.profile_store import ProfileStore

logger = logging.getLogger(__name__)


def run_post_execution_validation(
    dsn: str, workspace_id: int, plan: ExecutionPlan, spec: DashboardSpec,
    run: ExecutionRun, *, row_cap: int = 1_000_000,
) -> PostExecutionReport:
    """Recompute `plan` fresh and validate `run` against it.

    Never raises — a recomputation failure surfaces as a rejected report
    (code "recomputation_failed"), not an unhandled exception, so C12's own
    result is never lost even if C13 itself hits trouble.
    """
    dataset_ids = sorted({n.dataset_id for n in plan.nodes if n.dataset_id})
    profile_by_dataset: dict[str, DatasetProfile] = {}
    for did in dataset_ids:
        pstore = ProfileStore(dsn, workspace_id)
        try:
            profile = pstore.latest(did)
        finally:
            pstore.close()
        if profile is not None:
            profile_by_dataset[did] = profile

    try:
        recomputed_nodes, recompute_errors = recompute(dsn, workspace_id, plan, spec, row_cap)
    except Exception:  # noqa: BLE001 — must still yield a typed, rejected report
        logger.warning("C13 recompute failed ws=%s run=%s", workspace_id, run.execution_run_id,
                       exc_info=True)
        recomputed_nodes, recompute_errors = {}, ["recomputation raised an exception"]

    report = validate_execution(spec, plan, run, recomputed_nodes, profile_by_dataset)
    if recompute_errors:
        report.errors.append(ValidationError(code="recomputation_failed",
                                             details={"errors": recompute_errors}))
        report.status = "rejected"
        report.eligible_for_dashboard = False

    logger.info("post_execution_validation ws=%s run=%s status=%s",
               workspace_id, run.execution_run_id, report.status)
    return report

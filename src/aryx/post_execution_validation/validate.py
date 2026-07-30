"""Orchestrates the 7 named C13 checks into one PostExecutionReport.

Pure and deterministic — no LLM, no I/O (recomputation/data loading already
happened in recompute.py before this runs). Mirrors spec_validation.validate's
role for C09, one stage later in the pipeline: C09 grades a candidate SPEC
before execution, this grades the RESULTS after execution.
"""
from __future__ import annotations

import uuid
from typing import Any

from aryx.analysis_execution.models import ExecutionRun
from aryx.andie_planner.models import DashboardSpec
from aryx.execution_compiler.models import ExecutionPlan
from aryx.post_execution_validation.checks import (
    check_aggregation_correctness, check_evidence_lineage, check_no_invented_columns,
    check_no_invented_kpis, check_result_identity, check_result_shape,
    check_sample_size_reconciliation, null_exclusion_warnings, small_sample_warnings,
)
from aryx.post_execution_validation.models import PostExecutionReport
from aryx.profiler.models import DatasetProfile


def validate_execution(
    spec: DashboardSpec, plan: ExecutionPlan, run: ExecutionRun,
    recomputed_nodes: dict[str, Any], profile_by_dataset: dict[str, DatasetProfile],
) -> PostExecutionReport:
    """Run all 7 C13 checks (A-G) against one ExecutionRun and grade it.

    `errors` block the dashboard (`eligible_for_dashboard=False`);
    `warnings` (small sample, excluded nulls) never do — a valid result on
    a thin sample is still a valid result, just flagged.
    """
    checks = []
    errors = []
    warnings = []

    result, errs, warns = check_result_identity(spec, run)
    checks.append(result)
    errors.extend(errs)
    warnings.extend(warns)

    result, errs = check_aggregation_correctness(run, recomputed_nodes, plan)
    checks.append(result)
    errors.extend(errs)

    result, errs = check_sample_size_reconciliation(run)
    checks.append(result)
    errors.extend(errs)

    result, errs = check_evidence_lineage(plan, run)
    checks.append(result)
    errors.extend(errs)

    result, errs = check_no_invented_columns(plan, run, profile_by_dataset)
    checks.append(result)
    errors.extend(errs)

    result, errs = check_no_invented_kpis(plan, run)
    checks.append(result)
    errors.extend(errs)

    result, errs = check_result_shape(run)
    checks.append(result)
    errors.extend(errs)

    warnings.extend(small_sample_warnings(run))
    warnings.extend(null_exclusion_warnings(run))

    status = "rejected" if errors else ("approved_with_warnings" if warnings else "approved")
    return PostExecutionReport(
        validation_id=f"validation_post_{run.execution_run_id}_{uuid.uuid4().hex[:8]}",
        status=status, checks=checks, warnings=warnings, errors=errors,
        eligible_for_dashboard=not errors,
    )

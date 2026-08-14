"""Zero-click pipeline sequencing engine: C03-C07 -> C08-C11 -> C12/C13 ->
C14, chained end to end with no button clicks in between.

This deliberately extends the auto-chain past C07 (where it previously
stopped) through C12 (analysis execution) and C14 (dashboard composition) —
both of those components' own docstrings used to say "on-demand only, never
auto-chained"; that discipline is intentionally overridden here. The only
thing that still pauses the chain is a genuine blocker: C09 spec validation
rejected (after its own bounded repair retry), C13 marking the execution
results ineligible for a dashboard, or C14 dropping every visualization.
Everything else proceeds automatically.

A separate module from `run_downstream`/`run_planner` because:
  - `run_downstream`'s discipline is "one failure never blocks the rest"
    (best-effort, never raises) — the opposite of stop-on-blocker semantics.
  - `run_planner`/`run_planner_workspace` are still called directly by the
    manual "Generate spec" button for per-dataset iteration; auto-appending
    C12/C14 inside them would silently turn every manual click into a full
    execution+dashboard run too.

Job creation/debounce and the three real trigger entry points (Brief save,
intent capture, file ingest) live in the sibling `chain_jobs` module — kept
apart so this file, the stage-sequencing engine, stays under the 150-line
style cap.
"""
from __future__ import annotations

import logging

from aryx.andie_planner.models import PlannerResult
from aryx.andie_planner.run import run_planner_workspace
from aryx.analysis_execution.models import ExecutionRun
from aryx.analysis_execution.run import run_analysis_execution
from aryx.dashboard_composition.run import compose_dashboard
from aryx.llm import complete_json
from aryx.pipeline.downstream import run_downstream
from aryx.store.dataset_store import DatasetStore
from aryx.store.job_store import JobStore

logger = logging.getLogger(__name__)


def _dataset_ids_for(dsn: str, workspace_id: int) -> list[str]:
    """Every dataset already sitting in the workspace, sorted."""
    dstore = DatasetStore(dsn, workspace_id)
    try:
        return sorted({v.dataset_id for v in dstore.list_versions(500)})
    finally:
        dstore.close()


def _run_planner_stage(dsn: str, workspace_id: int, jobs: JobStore, job_id: str, *,
                       tier: str, broker) -> PlannerResult | None:
    """C08-C11. Returns the approved PlannerResult, or None once the job has
    already been finished (idle — no planning context yet — or blocked on
    C09's validation rejecting both the original spec and its retry)."""
    jobs.update_stage(job_id, "planner", 45, "Generating dashboard spec")
    result = run_planner_workspace(dsn, workspace_id, tier=tier, broker=broker)
    approved = bool(result.validation and result.validation.get("status") == "approved")
    if approved:
        return result
    if result.status == "controlled_error" and result.error_code == "no_planning_context":
        jobs.update_stage(job_id, "planner", 100, "No planning context yet")
        jobs.finish(job_id, None, "complete")
        return None
    jobs.finish(job_id, None, "blocked", error=f"planner: {result.error_code or result.status}")
    return None


def _run_execution_stage(dsn: str, workspace_id: int, jobs: JobStore,
                         job_id: str) -> ExecutionRun | None:
    """C12/C13. Returns the ExecutionRun once its results are eligible for a
    dashboard, or None once the job has already been finished (blocked)."""
    jobs.update_stage(job_id, "execution", 70, "Running analysis")
    run = run_analysis_execution(dsn, workspace_id, f"workspace_{workspace_id}")
    eligible = bool((run.validation or {}).get("eligible_for_dashboard"))
    if run.status == "failed" or not eligible:
        reason = ("; ".join(run.errors) if run.errors
                  else f"C13 status={(run.validation or {}).get('status')}")
        jobs.finish(job_id, None, "blocked", error=f"execution: {reason}")
        return None
    return run


def _run_dashboard_stage(dsn: str, workspace_id: int, jobs: JobStore, job_id: str, *,
                         use_llm_for_dashboard: bool, broker) -> bool:
    """C14. Returns True on success (caller finishes the job as complete),
    False once the job has already been finished as blocked.

    A per-visualization issue (e.g. a KPI card bound to the wrong ref type)
    makes compose_dashboard DROP that one component — it is never included
    with wrong data (see compose_components._build_components). So
    composition_status="invalid" does not mean nothing is safe to show; it
    only means every visualization got dropped. Block only on that — a
    dashboard with real, if partial, sections is a success.
    """
    jobs.update_stage(job_id, "dashboard", 90, "Composing dashboard")
    model = compose_dashboard(
        dsn, workspace_id, f"workspace_{workspace_id}",
        use_llm=use_llm_for_dashboard,
        broker=broker if use_llm_for_dashboard else None,
        complete_json_fn=complete_json if use_llm_for_dashboard else None,
    )
    if not model.sections:
        detail = ", ".join(i.code for i in model.issues) or "composition invalid"
        jobs.finish(job_id, None, "blocked", error=f"dashboard: {detail}")
        return False
    if model.issues:
        logger.info("auto_chain dashboard composed with dropped components ws=%s job=%s issues=%s",
                   workspace_id, job_id, [i.code for i in model.issues])
    return True


def run_auto_chain(dsn: str, workspace_id: int, job_id: str, *,
                   tier: str = "frontier", use_llm_for_dashboard: bool = False,
                   broker=None) -> None:
    """Run C03-C07 -> C08-C11 -> C12/C13 -> C14 in sequence for a workspace,
    reporting progress on `job_id` and stopping on the first genuine
    blocker. Caller must have already created the job row.
    """
    jobs = JobStore(dsn)
    try:
        dataset_ids = _dataset_ids_for(dsn, workspace_id)
        if not dataset_ids:
            jobs.update_stage(job_id, "waiting_for_data", 100, "Brief saved; no datasets yet")
            jobs.finish(job_id, None, "complete")
            return

        jobs.update_stage(job_id, "context", 25, f"Profiling {len(dataset_ids)} dataset(s)")
        run_downstream(dsn, workspace_id, dataset_ids, broker=broker)

        if _run_planner_stage(dsn, workspace_id, jobs, job_id, tier=tier, broker=broker) is None:
            return
        if _run_execution_stage(dsn, workspace_id, jobs, job_id) is None:
            return
        if not _run_dashboard_stage(dsn, workspace_id, jobs, job_id,
                                    use_llm_for_dashboard=use_llm_for_dashboard, broker=broker):
            return

        jobs.finish(job_id, None, "complete")
    except Exception as exc:  # noqa: BLE001 — a real bug, distinct from a designed "blocked" pause
        logger.exception("auto_chain failed ws=%s job=%s", workspace_id, job_id)
        jobs.finish(job_id, None, "failed", error=str(exc))
    finally:
        jobs.close()

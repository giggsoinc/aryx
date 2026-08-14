"""Job bookkeeping and trigger entry points for the zero-click pipeline
(see `aryx.pipeline.auto_chain` for the stage-sequencing engine itself).

Owns "when/how the chain starts": creating or reusing the `auto_chain`
JobStore row, and the three real call sites that kick it off — a Brief
save, an intent capture turning valid, and file ingest once intent is
already valid. Split out from auto_chain.py so that module, the actual
C03-C14 sequencing, stays under the 150-line style cap.
"""
from __future__ import annotations

import uuid
from typing import Any

from aryx.config import get_settings
from aryx.intent.capture import capture_intent
from aryx.intent.from_brief import brief_to_intent_request
from aryx.pipeline.auto_chain import run_auto_chain
from aryx.store.intent_store import IntentStore
from aryx.store.job_store import JobStore

_ACTIVE_STATUSES = ("queued", "running")
_DISABLED_ERROR = ("auto-chain disabled (set ARYX_AUTO_CHAIN_ENABLED=true to turn it on) — "
                   "use the manual Re-run buttons on the Pipeline tab instead.")


def _find_active_chain_job(jobs: JobStore, workspace_id: int) -> str | None:
    """The job_id of an already-queued/running auto_chain job for this
    workspace, if one exists — so a burst of triggers (e.g. a batch upload
    landing file by file) coalesces onto one chain run instead of firing a
    fresh LLM planning + execution + dashboard run per trigger."""
    for row in jobs.list_recent(workspace_id):
        if row.get("source_system") == "auto_chain" and row.get("status") in _ACTIVE_STATUSES:
            return row["job_id"]
    return None


def _create_or_reuse_job(dsn: str, workspace_id: int) -> tuple[str, bool]:
    """Return (job_id, is_new) — reusing an active job's id instead of
    creating a duplicate."""
    jobs = JobStore(dsn)
    try:
        existing = _find_active_chain_job(jobs, workspace_id)
        if existing is not None:
            return existing, False
        job_id = f"auto_chain_{uuid.uuid4().hex[:12]}"
        jobs.create(job_id, "auto_chain", f"workspace_{workspace_id}", workspace_id)
        return job_id, True
    finally:
        jobs.close()


def start_chain(dsn: str, workspace_id: int, background_tasks: Any, *, broker=None) -> str:
    """Enqueue `run_auto_chain` via FastAPI `BackgroundTasks` — for use
    inside a live request handler. Reuses an already-running chain job
    instead of enqueueing a duplicate. No-ops (job finishes as "blocked"
    with an explanatory error) when ARYX_AUTO_CHAIN_ENABLED is off — see
    that setting's docstring for why this defaults to disabled.
    """
    job_id, is_new = _create_or_reuse_job(dsn, workspace_id)
    if not is_new:
        return job_id
    if not get_settings().auto_chain_enabled:
        _finish_disabled(dsn, job_id)
        return job_id
    background_tasks.add_task(run_auto_chain, dsn, workspace_id, job_id, broker=broker)
    return job_id


def run_chain_now(dsn: str, workspace_id: int, *, broker=None) -> str:
    """Run the chain inline — for callers already executing off the request
    lifecycle (e.g. file_ingest_api._run_files, which itself runs as a
    background task, so it has no `BackgroundTasks` of its own to enqueue
    onto). Reuses an already-running chain job instead of enqueueing a
    duplicate. No-ops when ARYX_AUTO_CHAIN_ENABLED is off — see start_chain.
    """
    job_id, is_new = _create_or_reuse_job(dsn, workspace_id)
    if not is_new:
        return job_id
    if not get_settings().auto_chain_enabled:
        _finish_disabled(dsn, job_id)
        return job_id
    run_auto_chain(dsn, workspace_id, job_id, broker=broker)
    return job_id


def _finish_disabled(dsn: str, job_id: str) -> None:
    """Mark a just-created chain job blocked because the feature is
    globally off, without ever reaching run_auto_chain (no LLM call, no
    execution) — the actual security fix, not just a UI label."""
    jobs = JobStore(dsn)
    try:
        jobs.finish(job_id, None, "blocked", error=_DISABLED_ERROR)
    finally:
        jobs.close()


def trigger_chain_from_brief(dsn: str, workspace_id: int, brief: dict,
                             background_tasks: Any) -> str:
    """Derive a C01 intent from a just-saved Brief, persist it, and start
    (or reuse) the auto-chain. Returns the chain job's id.

    An invalid derived intent (missing domain/aim) is itself one of the
    named blocker cases — the job is created and immediately finished as
    "blocked" rather than silently doing nothing, so the frontend has
    something to poll and show the user what's missing.
    """
    request = brief_to_intent_request(brief, workspace_id)
    result = capture_intent(request)
    istore = IntentStore(dsn, workspace_id)
    try:
        istore.save(result)
    finally:
        istore.close()

    if result.validation_status != "valid":
        jobs = JobStore(dsn)
        try:
            job_id = f"auto_chain_{uuid.uuid4().hex[:12]}"
            jobs.create(job_id, "auto_chain", f"workspace_{workspace_id}", workspace_id)
            jobs.finish(job_id, None, "blocked", error="; ".join(result.errors))
        finally:
            jobs.close()
        return job_id

    return start_chain(dsn, workspace_id, background_tasks)

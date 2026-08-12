"""Jobs API: live ingestion progress + retention controls (observability)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from aryx.config import get_settings
from aryx.store.job_store import JobStore

logger = logging.getLogger(__name__)

# False-fail window: long ER heartbeats every ~40s; allow long Resolve.
_STALE_MINUTES = 30


def _store() -> JobStore:
    return JobStore(get_settings().rdb_dsn)


def _resume_meta(run_id: int) -> dict[str, Any]:
    """Load ontology_type / match_keys / workspace from discover or resolve stage."""
    from aryx.store.checkpoint_store import StageTracker
    tracker = StageTracker(get_settings().rdb_dsn)
    rows = tracker.rows(run_id)
    meta: dict[str, Any] = {}
    for r in rows:
        detail = r.get("detail") or {}
        if isinstance(detail, dict) and detail.get("ontology_type"):
            meta = detail
            break
    return meta


def _do_resume(old_job_id: str, new_job_id: str, run_id: int,
               workspace_id: int, meta: dict[str, Any]) -> None:
    """Background: continue pipeline from stage checkpoints for run_id."""
    from aryx.api.admin_api import _local_broker
    from aryx.connectors.records_source import RecordsConnector
    from aryx.pipeline.orchestrate import run_pipeline

    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    otype = str(meta.get("ontology_type") or "Record")
    keys = meta.get("match_keys") or ["name"]
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",") if k.strip()]
    system = str(meta.get("system") or "resume")
    dataset = str(meta.get("dataset") or f"run-{run_id}")
    try:
        jobs.update_stage(
            new_job_id, "Resume", 40,
            f"Resuming run {run_id} from last checkpoint (skip done stages)",
        )
        jobs.attach_run(new_job_id, run_id)

        def _progress(s: str, p: int, d: str) -> None:
            if "still working" in (d or ""):
                jobs.heartbeat(new_job_id, s, p, d)
            else:
                jobs.update_stage(new_job_id, s, p, d)

        summary = run_pipeline(
            connector=RecordsConnector([]),  # discover skipped on resume
            dsn=settings.rdb_dsn,
            system=system,
            dataset=dataset,
            ontology_type=otype,
            match_keys=list(keys),
            graph_url=settings.graph_url,
            broker=_local_broker(),
            workspace_id=workspace_id,
            resume_run_id=run_id,
            on_progress=_progress,
            on_run_id=lambda rid: jobs.attach_run(new_job_id, rid),
        )
        jobs.finish(new_job_id, run_id=summary.get("run_id") or run_id,
                    status="complete")
        logger.info("resume job %s (from %s) complete %s",
                    new_job_id, old_job_id, summary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resume job %s failed: %s", new_job_id, exc, exc_info=True)
        jobs.finish(new_job_id, run_id=run_id, status="failed", error=str(exc))
    finally:
        jobs.close()


def jobs_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/jobs")
    def list_jobs(workspace_id: int = 1) -> list[dict[str, Any]]:
        jobs = _store()
        try:
            # Truth before display: fail any "running" job whose process died
            # (no checkpoint for 30+ minutes) so the UI never shows a zombie.
            jobs.reap_stale(minutes=_STALE_MINUTES)
            return jobs.list_recent(workspace_id)
        finally:
            jobs.close()

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        jobs = _store()
        try:
            # Heartbeat path: only reap this job if truly stale (same window).
            jobs.reap_stale(minutes=_STALE_MINUTES)
            job = jobs.get(job_id)
        finally:
            jobs.close()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @router.get("/jobs/{job_id}/events")
    def get_job_events(job_id: str) -> list[dict[str, Any]]:
        """Live progress events for a job, newest first (≤80 rows)."""
        jobs = _store()
        try:
            return jobs.events(job_id)
        finally:
            jobs.close()

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        """Mark a job cancelled so the UI frees up.

        Note: a background ingest thread blocked on an LLM call can't be
        force-killed; this stops the row from showing as running and lets
        the user retry. Any later progress write from a still-alive thread
        is ignored because the row is terminal — unless resume is used on
        the attached run_id.
        """
        jobs = _store()
        try:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            jobs.finish(job_id, run_id=job.get("run_id"), status="cancelled",
                        error="Cancelled by user")
        finally:
            jobs.close()
        return {"status": "cancelled", "job_id": job_id}

    @router.post("/jobs/{job_id}/resume")
    def resume_status(job_id: str) -> dict[str, Any]:
        """Stage-checkpoint status for a job's run (G5) — inspect only."""
        from aryx.store.checkpoint_store import StageTracker
        jobs = _store()
        try:
            job = jobs.get(job_id)
        finally:
            jobs.close()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        run_id = job.get("run_id")
        if not run_id:
            return {
                "job_id": job_id, "run_id": None, "resumable": False,
                "stages": [],
                "reason": "No run_id on this job — data was never landed, "
                          "or this is an old job before resume support. "
                          "Re-upload the file.",
            }
        tracker = StageTracker(get_settings().rdb_dsn)
        stages = tracker.rows(int(run_id))
        # Treat leftover 'running' as not done (crash mid-stage).
        resumable = any(
            (s.get("status") or "") not in ("done",)
            for s in stages
        ) or not stages
        # If all stages done, nothing to resume
        if stages and all((s.get("status") or "") == "done" for s in stages):
            resumable = False
        return {
            "job_id": job_id, "run_id": int(run_id),
            "resumable": resumable, "stages": stages,
            "meta": _resume_meta(int(run_id)),
        }

    @router.post("/jobs/{job_id}/resume-run")
    def resume_run(job_id: str,
                   background_tasks: BackgroundTasks) -> dict[str, Any]:
        """Actually continue a failed/cancelled job from stage checkpoints.

        Requires run_id (attached after Discover). Skips stages already
        marked done. Does not re-read the original upload bytes.
        """
        jobs = _store()
        try:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            run_id = job.get("run_id")
            if not run_id:
                raise HTTPException(
                    400,
                    "Cannot resume: no landed run on this job. Re-upload the "
                    "file (Resolve never finished Discover, or job is pre-1.7.1).",
                )
            if job.get("status") == "running":
                raise HTTPException(
                    409,
                    "Job is still marked running. Wait for progress, or Cancel "
                    "first if you are sure the worker died.",
                )
            workspace_id = int(job.get("workspace_id") or 1)
            meta = _resume_meta(int(run_id))
            if not meta.get("ontology_type"):
                # Fallback: still try with defaults
                meta.setdefault("ontology_type", "Record")
                meta.setdefault("match_keys", ["name"])
                meta.setdefault("workspace_id", workspace_id)
            new_id = uuid.uuid4().hex
            jobs.create(new_id, "resume", f"from {job_id[:8]}…", workspace_id)
        finally:
            jobs.close()

        background_tasks.add_task(
            _do_resume, job_id, new_id, int(run_id), workspace_id, meta,
        )
        return {
            "status": "queued",
            "job_id": new_id,
            "resume_of": job_id,
            "run_id": int(run_id),
            "message": "Resuming from checkpoints — Discover is skipped if done.",
        }

    @router.post("/jobs/archive")
    def archive_jobs(days: int = 30) -> dict[str, int]:
        jobs = _store()
        try:
            return {"purged": jobs.archive_old(days)}
        finally:
            jobs.close()

    return router

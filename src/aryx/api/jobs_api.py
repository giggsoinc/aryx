"""Jobs API: live ingestion progress + retention controls (observability)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from aryx.config import get_settings
from aryx.store.job_store import JobStore


def _store() -> JobStore:
    return JobStore(get_settings().rdb_dsn)


def jobs_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/jobs")
    def list_jobs(workspace_id: int = 1) -> list[dict[str, Any]]:
        jobs = _store()
        try:
            return jobs.list_recent(workspace_id)
        finally:
            jobs.close()

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        jobs = _store()
        try:
            job = jobs.get(job_id)
        finally:
            jobs.close()
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @router.post("/jobs/{job_id}/resume")
    def resume_job(job_id: str) -> dict[str, Any]:
        """Stage-checkpoint status for a job's run (G5).

        Returns the durable per-stage rows so callers can re-submit the
        ingest with ``resume_run_id`` set; done stages will be skipped.
        """
        from aryx.store.checkpoint_store import StageTracker
        jobs = _store()
        try:
            job = jobs.get(job_id)
        finally:
            jobs.close()
        if job is None or not job.get("run_id"):
            raise HTTPException(status_code=404,
                                detail="job not found or has no run yet")
        tracker = StageTracker(get_settings().rdb_dsn)
        stages = tracker.rows(int(job["run_id"]))
        return {"job_id": job_id, "run_id": job["run_id"],
                "resumable": any(s["status"] != "done" for s in stages),
                "stages": stages}

    @router.post("/jobs/archive")
    def archive_jobs(days: int = 30) -> dict[str, int]:
        jobs = _store()
        try:
            return {"purged": jobs.archive_old(days)}
        finally:
            jobs.close()

    return router

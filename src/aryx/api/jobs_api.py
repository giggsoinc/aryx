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
    def list_jobs() -> list[dict[str, Any]]:
        jobs = _store()
        try:
            return jobs.list_recent()
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

    @router.post("/jobs/archive")
    def archive_jobs(days: int = 30) -> dict[str, int]:
        jobs = _store()
        try:
            return {"purged": jobs.archive_old(days)}
        finally:
            jobs.close()

    return router

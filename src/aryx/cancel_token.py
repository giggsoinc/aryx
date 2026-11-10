"""Cancellation state for one background job (see ``aryx.job_cancel``).

``CancelToken`` decides whether a job must stop: either this process was told
to (the cancel endpoint / a workspace delete), or the durable state says so —
the job row is ``cancelled`` or gone, or the workspace row it was started in
is gone or was re-created (same id, new ``created_at``): the id-reuse case.

``JobCancelled`` derives from ``BaseException`` on purpose: this code base has
many best-effort ``except Exception`` blocks (dimension materialisation,
snapshotting, ...) that would otherwise swallow a cancel and carry on.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from aryx.queries import load
from aryx.raven_log_config import log as raven_log

logger = logging.getLogger(__name__)

_SERVICE = "aryx-api"
_POLL_SEC = 2.0


class JobCancelled(BaseException):
    """Raised inside a background job when it has been cancelled or orphaned."""


class CancelToken:
    """Cancellation state for one running job."""

    def __init__(self, dsn: str, job_id: str, workspace_id: int,
                 workspace_created_at: Any) -> None:
        self.dsn = dsn
        self.job_id = job_id
        self.workspace_id = int(workspace_id)
        self.workspace_created_at = workspace_created_at
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.reason = ""
        self._last_poll = 0.0

    def cancel(self, reason: str = "cancelled by user") -> None:
        """Signal this job (in-process) to stop at its next checkpoint."""
        self.reason = reason
        self.cancelled.set()

    def check(self, force: bool = False) -> None:
        """Raise JobCancelled if this job should stop. ``force`` skips throttling."""
        if not self.cancelled.is_set():
            now = time.monotonic()
            if not force and now - self._last_poll < _POLL_SEC:
                return
            self._last_poll = now
            reason = self._db_reason()
            if reason:
                self.cancel(reason)
        if self.cancelled.is_set():
            raven_log(
                "WARN", "background job stopped at a cancel checkpoint",
                criticality="P3", service=_SERVICE, error_code="JOB_CANCELLED",
                context={"object_id": self.job_id, "previous_state": "running",
                         "requested_state": "cancelled", "final_state": "cancelled",
                         "trigger": self.reason, "result": "stopped",
                         "reason_code": "JOB_CANCELLED",
                         "workspace_id": self.workspace_id})
            raise JobCancelled(f"job {self.job_id}: {self.reason}")

    def _db_reason(self) -> str:
        """Why the durable state says to stop, or '' to keep going.

        Fails open: if the database cannot be read, the writes that follow
        will fail on their own, and a flaky poll must not kill a healthy run.
        """
        try:
            from aryx.store.job_store import JobStore
            job = JobStore(self.dsn).get(self.job_id)
            if job is None:
                return "job row no longer exists"
            if job.get("status") == "cancelled":
                return "job was cancelled"
            if self.workspace_created_at is not None:
                current = workspace_created_at(self.dsn, self.workspace_id)
                if current is None:
                    return f"workspace {self.workspace_id} was deleted"
                if current != self.workspace_created_at:
                    return (f"workspace {self.workspace_id} was re-created "
                            "while this job was running")
        except Exception as exc:  # noqa: BLE001 — fail open, see docstring
            logger.warning("cancel poll failed job=%s: %s", self.job_id, exc)
        return ""


def workspace_created_at(dsn: str, workspace_id: int) -> Any:
    """``created_at`` of a workspace row, or None if the row does not exist."""
    # Imported here, not at module level: aryx.store's package __init__ imports
    # entity_store, which imports job_cancel — a top-level import is circular.
    from aryx.store.pool import get_pool
    with get_pool(dsn).connection() as conn:
        row = conn.execute(load("select_workspace_created_at"),
                           (int(workspace_id),)).fetchone()
    return row[0] if row else None


def workspace_identity(dsn: str, workspace_id: int) -> Any:
    """Workspace identity for the id-reuse guard; None when it can't be read."""
    try:
        return workspace_created_at(dsn, workspace_id)
    except Exception as exc:  # noqa: BLE001 — identity guard is best-effort
        logger.warning("cancel_scope: workspace identity unavailable ws=%s: %s",
                       workspace_id, exc)
        return None

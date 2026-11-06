"""Cooperative cancellation for background ingest jobs.

Why this exists: ``POST /admin/jobs/{id}/cancel`` used to only write a terminal
status to the job row. The pipeline thread never looked at it, so a cancelled
ingest kept running for tens of minutes and then committed entities — in one
incident into a *different* workspace that had been handed the same id.

Model
-----
* A background runner opens ``cancel_scope(dsn, job_id, workspace_id)``. That
  registers a ``CancelToken`` for the job and publishes it through a
  ``ContextVar`` visible to every function the runner calls on its thread.
* Pipeline stages and hot loops call ``checkpoint()``. With no scope open it is
  a no-op, so CLI / test callers are unaffected.
* ``checkpoint()`` raises ``JobCancelled`` when (a) the cancel endpoint
  signalled this process, (b) the job row is now ``cancelled`` or gone, or
  (c) the workspace row is gone or was re-created (same id, new ``created_at``)
  since the run started — the id-reuse case.
* Database polling is throttled; ``checkpoint(force=True)`` always re-reads and
  is used immediately before every write that could land in a workspace.

``JobCancelled`` derives from ``BaseException`` on purpose: this code base has
many best-effort ``except Exception`` blocks (dimension materialisation,
snapshotting, ...) that would otherwise swallow a cancel and carry on.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from config import log as raven_log
from aryx.queries import load

logger = logging.getLogger(__name__)

_SERVICE = "aryx-api"
_POLL_SEC = 2.0
_WAIT_POLL_SEC = 0.25


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


_lock = threading.Lock()
_active: dict[str, CancelToken] = {}
_current: ContextVar[CancelToken | None] = ContextVar("aryx_cancel_token", default=None)


def workspace_created_at(dsn: str, workspace_id: int) -> Any:
    """``created_at`` of a workspace row, or None if the row does not exist."""
    # Imported here, not at module level: aryx.store's package __init__ imports
    # entity_store, which imports this module — a top-level import is circular.
    from aryx.store.pool import get_pool
    with get_pool(dsn).connection() as conn:
        row = conn.execute(load("select_workspace_created_at"),
                           (int(workspace_id),)).fetchone()
    return row[0] if row else None


def _identity(dsn: str, workspace_id: int) -> Any:
    """Workspace identity for the id-reuse guard; None when it can't be read."""
    try:
        return workspace_created_at(dsn, workspace_id)
    except Exception as exc:  # noqa: BLE001 — identity guard is best-effort
        logger.warning("cancel_scope: workspace identity unavailable ws=%s: %s",
                       workspace_id, exc)
        return None


@contextmanager
def cancel_scope(dsn: str, job_id: str, workspace_id: int,
                 swallow: bool = False) -> Iterator[CancelToken]:
    """Make the current thread's work cancellable via ``job_id``.

    Captures the workspace identity (``created_at``) now so a later checkpoint
    can tell that the workspace id has since been handed to someone else.
    With ``swallow=True`` a JobCancelled raised inside the block ends the block
    quietly (the job row is already 'cancelled', nothing more to record).
    """
    token = CancelToken(dsn, job_id, workspace_id, _identity(dsn, workspace_id))
    with _lock:
        _active[job_id] = token
    marker = _current.set(token)
    try:
        yield token
    except JobCancelled as stop:
        if not swallow:
            raise
        logger.info("job %s stopped: %s", job_id, stop)
    finally:
        _current.reset(marker)
        with _lock:
            _active.pop(job_id, None)
        token.finished.set()


def run_cancellable(fn: Callable[..., Any], dsn: str, job_id: str,
                    workspace_id: int, *args: Any, **kwargs: Any) -> Any:
    """Run ``fn(*args, **kwargs)`` inside a swallowing cancel scope.

    The background-task entry point for ingest runners: it lets
    ``_run_files`` / ``_run_db`` / ``_run_multi`` stay unchanged while a
    cancel (or a deleted / re-created workspace) stops them at the next
    checkpoint instead of letting them run on.
    """
    with cancel_scope(dsn, job_id, workspace_id, swallow=True):
        return fn(*args, **kwargs)


def checkpoint(force: bool = False) -> None:
    """Raise JobCancelled if the job running on this thread must stop.

    No-op when no ``cancel_scope`` is open on this thread.
    """
    token = _current.get()
    if token is not None:
        token.check(force)


def request_cancel(job_id: str, reason: str = "cancelled by user") -> bool:
    """Signal a running job in this process. True if one was found."""
    with _lock:
        token = _active.get(job_id)
    if token is None:
        return False
    token.cancel(reason)
    return True


def wait_until_stopped(job_ids: list[str], timeout: float) -> list[str]:
    """Wait up to ``timeout`` s for these jobs to leave their scope.

    Returns the job ids still running when the wait ended (empty = all
    stopped, or they were never running in this process).
    """
    deadline = time.monotonic() + timeout
    while True:
        with _lock:
            alive = [_active[j] for j in job_ids if j in _active]
        if not alive:
            return []
        if time.monotonic() >= deadline:
            return [t.job_id for t in alive]
        time.sleep(_WAIT_POLL_SEC)

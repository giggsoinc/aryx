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
* ``checkpoint()`` raises ``JobCancelled`` when the cancel endpoint signalled
  this process, the job row is now ``cancelled`` or gone, or the workspace was
  deleted / re-created since the run started (see ``aryx.cancel_token``).
* Database polling is throttled; ``checkpoint(force=True)`` always re-reads and
  is used immediately before every write that could land in a workspace.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from aryx.cancel_token import (  # noqa: F401  (re-exported public API)
    CancelToken, JobCancelled, workspace_created_at, workspace_identity,
)

logger = logging.getLogger(__name__)

_WAIT_POLL_SEC = 0.25
_lock = threading.Lock()
_active: dict[str, CancelToken] = {}
_current: ContextVar[CancelToken | None] = ContextVar("aryx_cancel_token", default=None)


@contextmanager
def cancel_scope(dsn: str, job_id: str, workspace_id: int,
                 swallow: bool = False) -> Iterator[CancelToken]:
    """Make the current thread's work cancellable via ``job_id``.

    Captures the workspace identity (``created_at``) now so a later checkpoint
    can tell that the workspace id has since been handed to someone else.
    With ``swallow=True`` a JobCancelled raised inside the block ends the block
    quietly (the job row is already 'cancelled', nothing more to record).
    """
    token = CancelToken(dsn, job_id, workspace_id, workspace_identity(dsn, workspace_id))
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

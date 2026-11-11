"""Unit tests for cooperative job cancellation (no database needed).

Covers Bug 2 of the "Cancel Doesn't Stop Ingest & Duplicate Records" report:
cancel must actually stop the pipeline thread, not just flip a job-row status.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

import pytest

from aryx import cancel_token
from aryx.job_cancel import (
    JobCancelled, cancel_scope, checkpoint, request_cancel,
    run_cancellable, wait_until_stopped,
)

_CREATED = dt.datetime(2026, 11, 4, 8, 0, tzinfo=dt.timezone.utc)


class _FakeJobs:
    """Stand-in for JobStore: returns whatever row the test configures."""

    row: dict[str, Any] | None = {"status": "running"}

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def get(self, job_id: str) -> dict[str, Any] | None:
        return type(self).row


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the two DB reads job_cancel performs."""
    import aryx.store.job_store as job_store
    _FakeJobs.row = {"status": "running"}
    monkeypatch.setattr(job_store, "JobStore", _FakeJobs)
    monkeypatch.setattr(cancel_token, "workspace_created_at",
                        lambda dsn, wid: _FakeWs.created)
    _FakeWs.created = _CREATED


class _FakeWs:
    created: Any = _CREATED


def test_checkpoint_is_noop_outside_a_scope() -> None:
    checkpoint()
    checkpoint(force=True)


def test_cancel_signal_stops_the_job_at_next_checkpoint() -> None:
    with cancel_scope("dsn", "job-1", 4):
        checkpoint(force=True)  # healthy
        assert request_cancel("job-1") is True
        with pytest.raises(JobCancelled):
            checkpoint()


def test_request_cancel_unknown_job_returns_false() -> None:
    assert request_cancel("no-such-job") is False


def test_cancelled_job_row_stops_the_job() -> None:
    with cancel_scope("dsn", "job-2", 4):
        _FakeJobs.row = {"status": "cancelled"}
        with pytest.raises(JobCancelled):
            checkpoint(force=True)


def test_deleted_job_row_stops_the_job() -> None:
    with cancel_scope("dsn", "job-3", 4):
        _FakeJobs.row = None
        with pytest.raises(JobCancelled):
            checkpoint(force=True)


def test_workspace_deleted_stops_the_job() -> None:
    with cancel_scope("dsn", "job-4", 4):
        _FakeWs.created = None
        with pytest.raises(JobCancelled, match="deleted"):
            checkpoint(force=True)


def test_workspace_id_reused_by_new_workspace_stops_the_job() -> None:
    """The id-reuse bug: same id, different created_at => orphaned run."""
    with cancel_scope("dsn", "job-5", 4):
        _FakeWs.created = _CREATED + dt.timedelta(minutes=2)
        with pytest.raises(JobCancelled, match="re-created"):
            checkpoint(force=True)


def test_db_poll_is_throttled_unless_forced() -> None:
    with cancel_scope("dsn", "job-6", 4):
        checkpoint(force=True)  # primes the throttle timestamp
        _FakeJobs.row = {"status": "cancelled"}
        checkpoint()  # inside the poll window: not re-read
        with pytest.raises(JobCancelled):
            checkpoint(force=True)


def test_db_read_failure_fails_open() -> None:
    class _Boom(_FakeJobs):
        def get(self, job_id: str) -> Any:
            raise RuntimeError("db down")

    import aryx.store.job_store as job_store
    job_store.JobStore = _Boom  # type: ignore[assignment]
    with cancel_scope("dsn", "job-7", 4):
        checkpoint(force=True)  # must not raise


def test_job_cancelled_is_not_swallowed_by_except_exception() -> None:
    """Best-effort `except Exception` blocks must not eat a cancel."""
    assert not issubclass(JobCancelled, Exception)
    with pytest.raises(JobCancelled):
        with cancel_scope("dsn", "job-8", 4):
            request_cancel("job-8")
            try:
                checkpoint()
            except Exception:  # noqa: BLE001 — the very pattern under test
                pytest.fail("JobCancelled was swallowed by except Exception")


def test_run_cancellable_swallows_cancel_and_unregisters() -> None:
    def work() -> str:
        request_cancel("job-9")
        checkpoint()
        return "should not get here"

    assert run_cancellable(work, "dsn", "job-9", 4) is None
    assert request_cancel("job-9") is False  # scope exited, token removed


def test_run_cancellable_passes_arguments_and_result() -> None:
    assert run_cancellable(lambda a, b=0: a + b, "dsn", "job-10", 4, 2, b=3) == 5


def test_cancel_stops_resolution_loop_before_any_pair_is_scored() -> None:
    """Mid-resolve cancel: the pair loop checkpoints, so no work is finished."""
    from aryx.models import ResolutionRecord
    from aryx.resolution.run import resolve

    records = [ResolutionRecord(record_id=i, text="Acme Corporation Ltd",
                                payload={}, source_system="csv",
                                cleaned_at=_CREATED) for i in range(1, 6)]
    with pytest.raises(JobCancelled):
        with cancel_scope("dsn", "job-11", 4):
            request_cancel("job-11")
            resolve(records, broker=None, ontology_type="Company")  # type: ignore[arg-type]


def test_wait_until_stopped_returns_when_job_leaves_scope() -> None:
    started, release = threading.Event(), threading.Event()

    def runner() -> None:
        with cancel_scope("dsn", "job-12", 4, swallow=True):
            started.set()
            release.wait(5)

    thread = threading.Thread(target=runner)
    thread.start()
    assert started.wait(5)
    assert wait_until_stopped(["job-12"], timeout=0.3) == ["job-12"]  # still inside
    release.set()
    thread.join(5)
    assert wait_until_stopped(["job-12"], timeout=2) == []


def test_wait_until_stopped_ignores_jobs_not_in_this_process() -> None:
    started = time.monotonic()
    assert wait_until_stopped(["not-running-here"], timeout=5) == []
    assert time.monotonic() - started < 1

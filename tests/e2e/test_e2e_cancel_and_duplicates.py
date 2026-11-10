"""Regression tests for "Cancel Doesn't Stop Ingest & Duplicate Records".

Real Postgres (+ FalkorDB for the duplicate-upload test); no LLM — entity
types are pinned and match keys are per-row identifiers, so resolution is
bypassed (DEC-011) and nothing calls a model.

  1. A cancelled job must not write entity rows for its run.
  2. Deleting workspace N, then running migrations, then creating a new
     workspace must give the new one an id greater than N.
  3. Uploading the same file twice into one workspace must not double the
     entity count.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

pytestmark = pytest.mark.e2e

_CSV = (b"contract_id,customer,amount\n"
        + b"".join(f"CT{1000 + i},Cust{i},{i * 10}\n".encode() for i in range(5)))


def _entity_count(dsn: str, workspace_id: int) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return conn.execute(
            "SELECT count(*) FROM aryx_entity WHERE workspace_id = %s",
            (workspace_id,)).fetchone()[0]


def test_cancelled_job_writes_no_entities(workspace, e2e_dsn) -> None:
    """Bug 2: cancel must stop the run before it saves anything."""
    from aryx.job_cancel import JobCancelled, cancel_scope
    from aryx.models import EntityMember, ResolvedEntity
    from aryx.store.entity_store import EntityStore
    from aryx.store.job_store import JobStore

    wid = workspace["id"]
    job_id = uuid.uuid4().hex
    jobs = JobStore(e2e_dsn)
    jobs.create(job_id, "upload", "1 file(s)", wid)

    estore = EntityStore(e2e_dsn, wid)
    results = [(ResolvedEntity(ontology_type="Contract",
                               attributes={"contract_id": "CT1"}, confidence=0.5),
                [EntityMember(landed_record_id=1)])]
    try:
        with pytest.raises(JobCancelled):
            with cancel_scope(e2e_dsn, job_id, wid):
                jobs.finish(job_id, run_id=None, status="cancelled",
                            error="Cancelled by user")
                estore.save(results)  # the write guard must refuse this
    finally:
        estore.close()
    assert _entity_count(e2e_dsn, wid) == 0


def test_job_marked_cancelled_cannot_be_overwritten_by_its_own_thread(
        workspace, e2e_dsn) -> None:
    """Bug 2: a still-running thread finishing later must not flip the status."""
    from aryx.store.job_store import JobStore

    job_id = uuid.uuid4().hex
    jobs = JobStore(e2e_dsn)
    jobs.create(job_id, "upload", "1 file(s)", workspace["id"])
    jobs.finish(job_id, run_id=None, status="cancelled", error="Cancelled by user")
    jobs.finish(job_id, run_id=None, status="complete")
    assert jobs.get(job_id)["status"] == "cancelled"


def test_orphaned_run_cannot_write_into_a_recreated_workspace(e2e_dsn) -> None:
    """Bugs 2+3: same workspace id re-used by a new workspace => write refused."""
    from aryx.job_cancel import JobCancelled, cancel_scope
    from aryx.models import EntityMember, ResolvedEntity
    from aryx.store.entity_store import EntityStore
    from aryx.store.job_store import JobStore
    from aryx.workspaces import WorkspaceStore

    store = WorkspaceStore(e2e_dsn)
    old = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    job_id = uuid.uuid4().hex
    jobs = JobStore(e2e_dsn)
    jobs.create(job_id, "upload", "1 file(s)", old["id"])
    estore = EntityStore(e2e_dsn, old["id"])
    results = [(ResolvedEntity(ontology_type="Contract",
                               attributes={"contract_id": "CT1"}, confidence=0.5),
                [EntityMember(landed_record_id=1)])]
    try:
        with pytest.raises(JobCancelled):
            with cancel_scope(e2e_dsn, job_id, old["id"]):
                # Simulate the incident: the workspace is deleted and another
                # one is created that happens to carry the same id.
                with psycopg.connect(e2e_dsn, autocommit=True) as conn:
                    conn.execute("UPDATE aryx_workspace SET created_at = "
                                 "created_at + interval '1 minute' WHERE id = %s",
                                 (old["id"],))
                estore.save(results)
    finally:
        estore.close()
        store.delete(old["id"])
        store.close()
    assert _entity_count(e2e_dsn, old["id"]) == 0


def test_workspace_id_is_never_reused_after_delete(e2e_dsn) -> None:
    """Bug 3: delete N -> migrations re-run -> create next => id > N."""
    from aryx.store import migrate
    from aryx.workspaces import WorkspaceStore

    store = WorkspaceStore(e2e_dsn)
    first = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    store.delete(first["id"])

    # Force the exact trigger from the incident: every migration, 0009
    # included, running again (force=True ignores the recorded files).
    migrate.apply_migrations(e2e_dsn, force=True)

    second = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    try:
        assert second["id"] > first["id"], (
            f"workspace id {first['id']} was handed out again as {second['id']}")
    finally:
        store.delete(second["id"])
        store.close()


def test_delete_workspace_cancels_its_running_job(e2e_dsn) -> None:
    """Bug 3: delete must cancel (not orphan) a workspace's running jobs."""
    from aryx.store.job_store import JobStore
    from aryx.workspaces import WorkspaceStore

    store = WorkspaceStore(e2e_dsn)
    ws = store.create(f"e2e_{uuid.uuid4().hex[:10]}")
    job_id = uuid.uuid4().hex
    jobs = JobStore(e2e_dsn)
    jobs.create(job_id, "upload", "1 file(s)", ws["id"])
    jobs.update_stage(job_id, "Resolve", 50, "running")
    try:
        store.delete(ws["id"])  # nothing runs in this process: must not hang
    finally:
        store.close()
    assert jobs.get(job_id) is None  # job rows are purged with the workspace


def test_same_file_uploaded_twice_does_not_double_entities(workspace, e2e_dsn) -> None:
    """Bug 3: a duplicate upload into one workspace must not re-ingest."""
    from aryx.api.file_ingest_api import _run_files
    from aryx.store.job_store import JobStore

    wid = workspace["id"]
    jobs = JobStore(e2e_dsn)

    def upload() -> str:
        job_id = uuid.uuid4().hex
        jobs.create(job_id, "upload", "1 file(s)", wid)
        _run_files([(_CSV, "contracts.csv")], "Contract", ["contract_id"], [],
                   job_id, wid)
        return job_id

    first = upload()
    assert jobs.get(first)["status"] == "complete"
    after_first = _entity_count(e2e_dsn, wid)
    assert after_first == 5

    second = upload()
    assert jobs.get(second)["status"] == "complete"
    assert _entity_count(e2e_dsn, wid) == after_first, (
        "re-uploading the same file must not add a second copy of every entity")

"""Regression tests for two bugs found while removing FalkorDB.

1. ``WorkspaceStore.purge_data`` always failed: ``purge_workspace_data.sql`` selected
   ``aryx_run.id`` / ``aryx_job.id`` (the keys are ``run_id`` / ``job_id``), the first
   DELETE was skipped because its chunk began with a comment header, and the tables
   that reference ``aryx_run`` without a cascade (field profile, field tag, schema
   mapping) were not cleared before the runs were deleted.
2. ``ActionStore.set_attribute`` passed ``Json`` where ``attributes || %s`` needs
   ``Jsonb``, which Postgres rejects.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

from aryx.models import ResolvedEntity
from aryx.store.action_store import ActionStore
from aryx.store.entity_store import EntityStore
from aryx.workspaces import WorkspaceStore

pytestmark = pytest.mark.e2e

# Tables the purge must empty for a workspace, keyed by how they link to it.
_BY_WORKSPACE = ("aryx_entity", "aryx_action", "aryx_run", "aryx_job")
_BY_RUN = ("aryx_field_profile", "aryx_field_tag", "aryx_schema_mapping")


def _seed_workspace(dsn: str, wid: int) -> dict:
    """Give a workspace an entity, an action, a run with its children, and a job."""
    job_id = f"purge-{uuid.uuid4().hex[:10]}"
    store = EntityStore(dsn, wid)
    try:
        store.save([(ResolvedEntity(ontology_type="Company",
                                    attributes={"name": f"Acme {wid}"}), [])])
    finally:
        store.close()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("INSERT INTO aryx_action (workspace_id, name, definition)"
                     " VALUES (%s, 'first-delete-probe', '{}'::jsonb)", (wid,))
        run_id = conn.execute(
            "INSERT INTO aryx_run (source_system, source_dataset, workspace_id)"
            " VALUES ('crm', 'accounts', %s) RETURNING run_id", (wid,)).fetchone()[0]
        conn.execute("INSERT INTO aryx_field_profile (run_id, field, non_null,"
                     " distinct_count, samples) VALUES (%s, 'name', 1, 1, '[]'::jsonb)",
                     (run_id,))
        conn.execute("INSERT INTO aryx_field_tag (run_id, field, semantic_type)"
                     " VALUES (%s, 'name', 'text')", (run_id,))
        conn.execute("INSERT INTO aryx_schema_mapping (run_id, source_system,"
                     " source_dataset, ontology_type) VALUES (%s, 'crm', 'accounts',"
                     " 'Company')", (run_id,))
        conn.execute("INSERT INTO aryx_job (job_id, source_system, source_dataset,"
                     " workspace_id) VALUES (%s, 'crm', 'accounts', %s)", (job_id, wid))
        conn.execute("INSERT INTO aryx_job_event (job_id, stage) VALUES (%s, 'start')",
                     (job_id,))
    return {"run_id": run_id, "job_id": job_id}


def _rows(dsn: str, wid: int, ids: dict) -> dict[str, int]:
    """Row counts for everything _seed_workspace created."""
    out: dict[str, int] = {}
    with psycopg.connect(dsn, autocommit=True) as conn:
        for table in _BY_WORKSPACE:
            out[table] = conn.execute(
                f"SELECT count(*) FROM {table} WHERE workspace_id = %s", (wid,)
            ).fetchone()[0]
        for table in _BY_RUN:
            out[table] = conn.execute(
                f"SELECT count(*) FROM {table} WHERE run_id = %s", (ids["run_id"],)
            ).fetchone()[0]
        out["aryx_job_event"] = conn.execute(
            "SELECT count(*) FROM aryx_job_event WHERE job_id = %s", (ids["job_id"],)
        ).fetchone()[0]
    return out


def test_purge_clears_the_workspace_and_keeps_others(e2e_dsn: str, workspace: dict) -> None:
    wid = workspace["id"]
    other = WorkspaceStore(e2e_dsn)
    other_ws = other.create(f"e2e_purge_other_{uuid.uuid4().hex[:8]}")
    try:
        mine = _seed_workspace(e2e_dsn, wid)
        theirs = _seed_workspace(e2e_dsn, other_ws["id"])
        assert all(n == 1 for n in _rows(e2e_dsn, wid, mine).values())

        ws_store = WorkspaceStore(e2e_dsn)
        try:
            assert ws_store.purge_data(wid)["status"] == "purged"
        finally:
            ws_store.close()

        # aryx_action is the first DELETE in the file (it used to be skipped); the
        # run children are the no-cascade foreign keys that used to block the purge.
        assert all(n == 0 for n in _rows(e2e_dsn, wid, mine).values())
        assert all(n == 1 for n in _rows(e2e_dsn, other_ws["id"], theirs).values())
    finally:
        other.delete(other_ws["id"])
        other.close()


def test_set_attribute_merges_into_the_entity(e2e_dsn: str, workspace: dict) -> None:
    wid = workspace["id"]
    estore = EntityStore(e2e_dsn, wid)
    try:
        estore.save([(ResolvedEntity(ontology_type="Company",
                                     attributes={"name": "Acme"}), [])])
    finally:
        estore.close()
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        eid = conn.execute("SELECT id FROM aryx_entity WHERE workspace_id = %s",
                           (wid,)).fetchone()[0]
    actions = ActionStore(e2e_dsn, wid)
    try:
        actions.set_attribute(eid, "tier", "gold")
        actions.set_attribute(eid, "region", "emea")
        assert actions.get_attribute(eid, "tier") == "gold"
        assert actions.get_attribute(eid, "region") == "emea"
        assert actions.get_attribute(eid, "name") == "Acme"
    finally:
        actions.close()

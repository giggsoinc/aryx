"""Regression tests for two bugs found while removing FalkorDB.

1. ``WorkspaceStore.purge_data`` always failed: ``purge_workspace_data.sql`` selected
   ``aryx_run.id`` / ``aryx_job.id`` (the keys are ``run_id`` / ``job_id``), and the
   first DELETE was skipped because its chunk began with a comment header.
2. ``ActionStore.set_attribute`` passed ``Json`` where ``attributes || %s`` needs
   ``Jsonb``, which Postgres rejects.
"""
from __future__ import annotations

import psycopg
import pytest

from aryx.models import ResolvedEntity
from aryx.store.action_store import ActionStore
from aryx.store.entity_store import EntityStore
from aryx.workspaces import WorkspaceStore

pytestmark = pytest.mark.e2e


def _count(dsn: str, table: str, wid: int) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return conn.execute(
            f"SELECT count(*) FROM {table} WHERE workspace_id = %s", (wid,)
        ).fetchone()[0]


def test_purge_clears_the_workspace_and_keeps_others(e2e_dsn: str, workspace: dict) -> None:
    wid = workspace["id"]
    other = WorkspaceStore(e2e_dsn)
    other_ws = other.create("e2e_purge_other")
    try:
        for ws_id in (wid, other_ws["id"]):
            store = EntityStore(e2e_dsn, ws_id)
            try:
                store.save([(ResolvedEntity(ontology_type="Company",
                                            attributes={"name": f"Acme {ws_id}"}), [])])
            finally:
                store.close()
        with psycopg.connect(e2e_dsn, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO aryx_action (workspace_id, name, definition)"
                " VALUES (%s, 'first-delete-probe', '{}'::jsonb)", (wid,))
        assert _count(e2e_dsn, "aryx_entity", wid) == 1
        assert _count(e2e_dsn, "aryx_action", wid) == 1

        ws_store = WorkspaceStore(e2e_dsn)
        try:
            assert ws_store.purge_data(wid)["status"] == "purged"
        finally:
            ws_store.close()

        assert _count(e2e_dsn, "aryx_entity", wid) == 0
        # aryx_action is the first DELETE in the file; it used to be skipped.
        assert _count(e2e_dsn, "aryx_action", wid) == 0
        assert _count(e2e_dsn, "aryx_entity", other_ws["id"]) == 1
    finally:
        other.delete(other_ws["id"])
        other.close()


def test_set_attribute_merges_into_the_entity(e2e_dsn: str, workspace: dict) -> None:
    wid = workspace["id"]
    estore = EntityStore(e2e_dsn, wid)
    try:
        ids = estore.save([(ResolvedEntity(ontology_type="Company",
                                           attributes={"name": "Acme"}), [])])
    finally:
        estore.close()
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        eid = conn.execute("SELECT id FROM aryx_entity WHERE workspace_id = %s",
                           (wid,)).fetchone()[0]
    actions = ActionStore(e2e_dsn, wid)
    try:
        actions.set_attribute(eid, "tier", "gold")
        assert actions.get_attribute(eid, "tier") == "gold"
        actions.set_attribute(eid, "region", "emea")
        assert actions.get_attribute(eid, "tier") == "gold"
    finally:
        actions.close()
    assert ids is not None

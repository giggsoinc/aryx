"""Real-Postgres coverage for EntityStore.match_keys_by_type().

Regression for the microsft_new incident: a SupportTicket ingested with
match_keys=["ticket_id"] displayed "customer_name" (a foreign Customer
reference) instead of "TK101" because display_name()'s type-prefix guess
(supportticket_id) never matched the real column (ticket_id). Fixed by
reading the actual match_keys the ingest declared, persisted in
aryx_run_stage's checkpoint detail — this test proves the real query reads
it back correctly for a fresh run, not just a hand-built dict.
"""
from __future__ import annotations

import psycopg
import pytest

from aryx.store.entity_store import EntityStore

pytestmark = pytest.mark.e2e


def _seed_run_with_match_keys(dsn: str, workspace_id: int, ontology_type: str,
                              match_keys: list[str]) -> None:
    import json

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_run (workspace_id, source_system, "
                "source_dataset, status) VALUES (%s, 'test', 'test', 'done') "
                "RETURNING run_id", (workspace_id,))
            run_id = cur.fetchone()[0]
            detail = {"ontology_type": ontology_type, "match_keys": match_keys,
                      "workspace_id": workspace_id, "system": "test", "dataset": "test"}
            cur.execute(
                "INSERT INTO aryx_run_stage (run_id, stage, status, detail) "
                "VALUES (%s, 'discover', 'done', %s)",
                (run_id, json.dumps(detail)))


def test_match_keys_by_type_reads_the_real_ingest_decision(workspace, e2e_dsn) -> None:
    wid = workspace["id"]
    _seed_run_with_match_keys(e2e_dsn, wid, "SupportTicket", ["ticket_id"])
    _seed_run_with_match_keys(e2e_dsn, wid, "Order", ["order_id"])

    store = EntityStore(e2e_dsn, wid)
    result = store.match_keys_by_type()

    assert result["SupportTicket"] == ["ticket_id"]
    assert result["Order"] == ["order_id"]


def test_match_keys_by_type_uses_the_most_recent_run_per_type(workspace, e2e_dsn) -> None:
    """A type re-ingested with different match_keys must show the latest
    decision, not the first one ever recorded."""
    wid = workspace["id"]
    _seed_run_with_match_keys(e2e_dsn, wid, "SupportTicket", ["subject"])
    _seed_run_with_match_keys(e2e_dsn, wid, "SupportTicket", ["ticket_id"])

    store = EntityStore(e2e_dsn, wid)
    result = store.match_keys_by_type()

    assert result["SupportTicket"] == ["ticket_id"]


def test_match_keys_by_type_empty_workspace_returns_empty_dict(workspace, e2e_dsn) -> None:
    store = EntityStore(e2e_dsn, workspace["id"])
    assert store.match_keys_by_type() == {}

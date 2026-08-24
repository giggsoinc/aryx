"""Real-Postgres coverage for EntityStore's scoped query methods.

Raven-review finding: entities_by_ids/relationships_for_entities/
members_provenance_for_entities (added to fix adjudication_api.py::preview
loading the entire workspace for a single pending-row preview) had zero
test coverage. Seeds several entities — some related, some not — and
proves each scoped method returns exactly what it's asked for, not the
workspace-wide result its unscoped sibling would.
"""
from __future__ import annotations

import psycopg
import pytest

from aryx.store.entity_store import EntityStore

pytestmark = pytest.mark.e2e


def _seed_entity(dsn: str, workspace_id: int, name: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_entity (workspace_id, ontology_type, "
                "attributes, confidence) VALUES (%s, 'Company', %s, 1) "
                "RETURNING id",
                (workspace_id, psycopg.types.json.Json({"name": name})))
            entity_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_run (workspace_id, source_system, "
                "source_dataset, status) VALUES (%s, 'test', 'test', 'done') "
                "RETURNING run_id",
                (workspace_id,))
            run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_landed_record (workspace_id, run_id, "
                "source_system, source_dataset, source_record_id, payload, "
                "cleaned_at) VALUES (%s, %s, 'test', 'test', %s, %s, "
                "'2026-01-01') RETURNING id",
                (workspace_id, run_id, name, psycopg.types.json.Json({"name": name})))
            landed_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO aryx_entity_member (workspace_id, entity_id, "
                "landed_record_id, confidence) VALUES (%s, %s, %s, 1)",
                (workspace_id, entity_id, landed_id))
    return entity_id


def _add_relationship(dsn: str, workspace_id: int, src: int, tgt: int, name: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO aryx_relationship (workspace_id, source_entity_id, "
                "target_entity_id, name, confidence) VALUES (%s, %s, %s, %s, 1)",
                (workspace_id, src, tgt, name))


def test_entities_by_ids_returns_only_the_requested_ids(workspace, e2e_dsn) -> None:
    wid = workspace["id"]
    a = _seed_entity(e2e_dsn, wid, "Alpha")
    b = _seed_entity(e2e_dsn, wid, "Beta")
    _seed_entity(e2e_dsn, wid, "Gamma")  # unrelated third entity

    store = EntityStore(e2e_dsn, wid)
    result = store.entities_by_ids([a, b])

    ids = {row[0] for row in result}
    assert ids == {a, b}


def test_entities_by_ids_empty_input_returns_empty_without_a_query(workspace, e2e_dsn) -> None:
    store = EntityStore(e2e_dsn, workspace["id"])
    assert store.entities_by_ids([]) == []


def test_relationships_for_entities_excludes_unrelated_edges(workspace, e2e_dsn) -> None:
    wid = workspace["id"]
    a = _seed_entity(e2e_dsn, wid, "Alpha")
    b = _seed_entity(e2e_dsn, wid, "Beta")
    c = _seed_entity(e2e_dsn, wid, "Gamma")
    _add_relationship(e2e_dsn, wid, a, b, "KNOWS")
    _add_relationship(e2e_dsn, wid, b, c, "KNOWS")  # touches b (a neighbour), not a/only-c pair

    store = EntityStore(e2e_dsn, wid)
    rels = store.relationships_for_entities([a])

    assert rels == [(a, b, "KNOWS")]


def test_members_provenance_for_entities_excludes_other_entities(workspace, e2e_dsn) -> None:
    wid = workspace["id"]
    a = _seed_entity(e2e_dsn, wid, "Alpha")
    b = _seed_entity(e2e_dsn, wid, "Beta")

    store = EntityStore(e2e_dsn, wid)
    prov_a = store.members_provenance_for_entities([a])
    prov_both = store.members_provenance_for_entities([a, b])

    assert all(row[0] == a for row in prov_a)
    assert {row[0] for row in prov_both} == {a, b}

"""Migration 0048 removes the FalkorDB projector's leftovers, and stays removed.

An upgraded database still has aryx_projection_state, aryx_projected_entity and
aryx_entity.updated_at. This recreates them (with a row) the way such a database
would hold them, and checks the migration clears them, that a second pass
changes nothing, and that nothing live still needed them. Because
apply_migrations re-runs every file on every call, migration 0022 must no
longer create them either, or the cleanup would be undone on every request.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from aryx.models import ResolvedEntity
from aryx.queries import load
from aryx.store.entity_store import EntityStore
from aryx.store.migrate import _split_statements, apply_migrations

pytestmark = pytest.mark.e2e

_MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "aryx" / "store" / "migrations"


def _present(dsn: str) -> tuple[bool, bool, bool]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
            " AND tablename IN ('aryx_projection_state', 'aryx_projected_entity')")}
        col = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema ="
            " current_schema() AND table_name = 'aryx_entity'"
            " AND column_name = 'updated_at'").fetchone()
    return ("aryx_projection_state" in tables, "aryx_projected_entity" in tables,
            col is not None)


def _recreate_old_objects(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS aryx_projection_state ("
                     "workspace_id BIGINT PRIMARY KEY,"
                     " last_projected_at TIMESTAMPTZ NOT NULL)")
        conn.execute("INSERT INTO aryx_projection_state VALUES (999999, now())"
                     " ON CONFLICT DO NOTHING")
        conn.execute("CREATE TABLE IF NOT EXISTS aryx_projected_entity ("
                     "workspace_id BIGINT NOT NULL, entity_id BIGINT NOT NULL,"
                     " PRIMARY KEY (workspace_id, entity_id))")
        conn.execute("INSERT INTO aryx_projected_entity VALUES (999999, 1)"
                     " ON CONFLICT DO NOTHING")
        conn.execute("ALTER TABLE aryx_entity ADD COLUMN IF NOT EXISTS"
                     " updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")


def test_migration_removes_old_objects_and_a_second_pass_changes_nothing(e2e_dsn: str) -> None:
    _recreate_old_objects(e2e_dsn)
    assert _present(e2e_dsn) == (True, True, True)
    apply_migrations(e2e_dsn, force=True)
    assert _present(e2e_dsn) == (False, False, False)
    apply_migrations(e2e_dsn, force=True)
    assert _present(e2e_dsn) == (False, False, False)


def test_migration_0022_no_longer_creates_anything() -> None:
    """Otherwise every apply_migrations call would re-create what 0048 drops."""
    text = (_MIGRATIONS / "0022_projection.sql").read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    assert _split_statements(code) == []


def test_every_removal_in_0048_is_guarded_by_an_existence_check() -> None:
    text = (_MIGRATIONS / "0048_drop_projection_objects.sql").read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    assert code.count("IF EXISTS (SELECT 1") == 3
    for verb in ("DROP TABLE aryx_projection_state", "DROP TABLE aryx_projected_entity",
                 "DROP COLUMN updated_at"):
        assert verb in code


def test_entity_attribute_update_works_without_updated_at(e2e_dsn: str, workspace: dict) -> None:
    """The live user of the dropped column (adjudication merge passes Jsonb)."""
    ws = workspace["id"]
    estore = EntityStore(e2e_dsn, ws)
    estore.save([(ResolvedEntity(ontology_type="Thing", attributes={"name": "x"},
                                 confidence=1.0), [])])
    entity_id = estore.list_entities()[0][0]
    with psycopg.connect(e2e_dsn, autocommit=True) as conn:
        row = conn.execute(load("update_entity_attributes"),
                           (Jsonb({"colour": "red"}), entity_id, ws)).fetchone()
    assert row[0] == {"name": "x", "colour": "red"}

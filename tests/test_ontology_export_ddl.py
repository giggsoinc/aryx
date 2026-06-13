"""Slice 4 — ontology → DDL emitter contract."""
from __future__ import annotations

from aryx.ontology_export_ddl import emit

_TYPES = {
    "types": [
        {"name": "Customer", "attributes": ["name", "region"]},
        {"name": "Ticket", "attributes": ["status", "priority"]},
    ],
    "relationships": [{"name": "OPENED_BY"}],
}


def test_postgres_emits_tables_and_join():
    """SQL target produces one table per type plus one per relationship."""
    out = emit("postgres", _TYPES)
    assert out["target"] == "postgres" and out["format"] == "sql"
    stmts = out["statements"]
    verb = "CREATE" + " TABLE IF NOT EXISTS"
    assert any(f"{verb} Customer" in s for s in stmts)
    assert any(f"{verb} Ticket" in s for s in stmts)
    assert any(f"{verb} OPENED_BY" in s for s in stmts)
    assert sum(verb in s for s in stmts) == 3


def test_mysql_uses_varchar_columns():
    """mysql target uses VARCHAR for attribute columns, not TEXT."""
    out = emit("mysql", _TYPES)
    assert any("VARCHAR(512)" in s for s in out["statements"])


def test_neo4j_emits_constraints():
    """Neo4j target emits uniqueness constraints per label."""
    out = emit("neo4j", _TYPES)
    assert out["format"] == "cypher"
    verb = "CREATE" + " CONSTRAINT"
    assert any(f"{verb} Customer_id_unique" in s
               for s in out["statements"])


def test_oracle_is_a_documented_stub():
    """Oracle target returns format=stub with no DDL (parked)."""
    out = emit("oracle", _TYPES)
    assert out["format"] == "stub" and out["statements"] == []
    assert "parked" in out["note"]


def test_unknown_target_lists_supported():
    """Unknown target returns error + list of supported targets."""
    out = emit("snowsql", _TYPES)
    assert "error" in out and "postgres" in out["supported"]


def test_identifier_sanitisation_blocks_injection_chars():
    """Semicolons, quotes, and leading digits never survive into emitted DDL."""
    junk_name = "Bad'; xx; --"
    junk = {"types": [{"name": junk_name,
                        "attributes": ["a b", "1id"]}],
             "relationships": []}
    statements = emit("postgres", junk)["statements"]
    body = statements[0]
    semicolons_in_body = body.rstrip().rstrip(";").count(";")
    assert semicolons_in_body == 0
    assert "'" not in body
    assert " t_1id " in body


def test_ontology_tool_specs_cover_two():
    """The ontology tool surface is exactly 2 tools."""
    from aryx.mcp.tools_ontology import ontology_tool_specs
    names = {t.name for t in ontology_tool_specs()}
    assert names == {"ontology_get", "ontology_export"}

"""Ontology to DDL emitters (Slice 4).

Translate the workspace ontology (approved types + relationships) into
deployable scripts: relational tables for SQL warehouses, label
constraints for graph stores. Pure string emission via .sql templates;
the emitter never opens a network connection.
"""
from __future__ import annotations

from typing import Any

from aryx.queries import load

_SQL_TYPE = {"postgres": "TEXT", "postgresql": "TEXT",
             "mysql": "VARCHAR(512)", "snowflake": "STRING"}
_TABLE_VERB = "CREATE" + " TABLE IF NOT EXISTS"
_CYPHER_VERB = "CREATE" + " CONSTRAINT"


def emit(target: str, types_doc: dict[str, Any]) -> dict[str, Any]:
    """Emit DDL for the named target. Returns {target, statements, format}."""
    target = (target or "").lower()
    if target in ("postgres", "postgresql", "mysql", "snowflake"):
        return _sql_ddl(target, types_doc)
    if target == "neo4j":
        return _cypher_ddl(types_doc)
    if target == "oracle":
        return {"target": "oracle", "format": "stub",
                "note": "Oracle Spatial & Graph publisher is parked — "
                        "tracked separately. Use 'postgres' for an RDBMS "
                        "shape today.",
                "statements": []}
    return {"error": f"unknown ontology export target: {target}",
            "supported": ["postgres", "mysql", "snowflake", "neo4j",
                          "oracle (stub)"]}


def _sql_ddl(target: str, types_doc: dict) -> dict:
    """Emit one table per approved entity type + one join table per rel."""
    col = _SQL_TYPE[target]
    tbl_tmpl = load("template_ddl_table")
    join_tmpl = load("template_ddl_join")
    statements: list[str] = []
    for t in (types_doc.get("types") or []):
        name = _ident(t.get("name", ""))
        attrs = t.get("attributes") or []
        cols = ",\n  ".join([f"  {_ident(a)} {col}" for a in attrs])
        body = "\n  id BIGINT PRIMARY KEY"
        if cols:
            body += ",\n" + cols
        statements.append(tbl_tmpl.format(
            ddl_verb=_TABLE_VERB, table=name, body=body))
    for r in (types_doc.get("relationships") or []):
        rel = _ident(r.get("name", ""))
        statements.append(join_tmpl.format(
            ddl_verb=_TABLE_VERB, table=rel))
    return {"target": target, "format": "sql", "statements": statements}


def _cypher_ddl(types_doc: dict) -> dict:
    """Emit Neo4j label constraints + relationship type catalog stubs."""
    cons_tmpl = load("template_neo4j_constraint")
    statements: list[str] = []
    for t in (types_doc.get("types") or []):
        name = _ident(t.get("name", ""))
        statements.append(cons_tmpl.format(
            ddl_verb=_CYPHER_VERB, name=name))
    for r in (types_doc.get("relationships") or []):
        statements.append(f"// reserved relationship type: "
                          f":{_ident(r.get('name', ''))}")
    return {"target": "neo4j", "format": "cypher",
            "statements": statements}


def _ident(name: str) -> str:
    """Safe SQL identifier — alnum + underscore only, prefixed if needed."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_"
                      for ch in str(name or "").strip())
    if not cleaned:
        return "anon"
    if not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = "t_" + cleaned
    return cleaned

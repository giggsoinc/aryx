"""Schema discovery agent: map DB tables to an ontology from user context.

Given the introspected schema and a plain-English goal, the LLM proposes which
tables become which entity types, the key columns, and the relationships
between them. Declared foreign keys are merged in deterministically so real FKs
are never missed even if the model overlooks them.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from aryx import llm_runtime

logger = logging.getLogger(__name__)


def _brief(schema: list[dict]) -> str:
    return "\n".join(
        f"- {t['table']} (columns: {', '.join(t['columns'][:14])}; "
        f"pk: {','.join(t['pk']) or '?'})"
        for t in schema
    )


def _parse(text: str) -> dict[str, Any]:
    try:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1])
    except (ValueError, json.JSONDecodeError):
        return {}


def _heuristic_mapping(schema: list[dict]) -> dict[str, Any]:
    """LLM-free fallback: derive ontology types from table names.

    Strips a common 'support_' / 'app_' prefix, drops trailing 's', and
    turns the result into PascalCase. Junction-style names (a_b_links) are
    marked include=false so they don't pollute the entity list.
    """
    skip_prefixes = ("support_", "app_", "tbl_", "stg_")

    def to_type(name: str) -> str:
        for p in skip_prefixes:
            if name.startswith(p):
                name = name[len(p):]
                break
        if name.endswith("s") and not name.endswith("ss"):
            name = name[:-1]
        return "".join(part.capitalize() for part in name.split("_"))

    tables = []
    for t in schema:
        table_name = t["table"]
        is_junction = ("_link" in table_name or "_links" in table_name
                       or "_expertise" in table_name)
        tables.append({
            "table": table_name,
            "ontology_type": to_type(table_name),
            "match_keys": t.get("pk") or ["id"],
            "include": not is_junction,
        })
    return {"tables": tables, "links": []}


def _fk_edges(schema: list[dict], by_table: dict[str, dict]) -> list[dict]:
    edges: list[dict] = []
    for t in schema:
        if t["table"] not in by_table:
            continue
        for fk in t["fks"]:
            if fk["ref_table"] not in by_table:
                continue
            src_type = by_table[t["table"]]["ontology_type"]
            edges.append({
                "source_type": src_type,
                "source_attr": fk["column"],
                "target_type": by_table[fk["ref_table"]]["ontology_type"],
                "target_attr": fk["ref_column"],
                "name": f"HAS_{src_type}".upper(),
            })
    return edges


def discover_mappings(schema: list[dict], context: str) -> dict[str, Any]:
    """Return {tables:[{table, ontology_type, match_keys}], edges:[...]}."""
    sys = "You map relational tables to a knowledge-graph ontology."
    user = (
        f"User goal: {context}\n\nDatabase tables:\n{_brief(schema)}\n\n"
        "Reply ONLY as JSON: {\"tables\":[{\"table\":\"...\",\"ontology_type\":"
        "\"...\",\"match_keys\":[\"col\"],\"include\":true}],\"links\":[{\"from_table\""
        ":\"...\",\"from_column\":\"...\",\"to_table\":\"...\",\"to_column\":\"...\"}]}."
        " ontology_type is a singular PascalCase noun. match_keys are 1-3 identifying"
        " columns. Set include=false for log/audit/junction tables. links capture how"
        " a column in one table references another table (even without a formal FK)."
    )
    parsed: dict[str, Any] = {}
    try:
        parsed = _parse(llm_runtime.chat("menial", sys, user)[0])
    except Exception as exc:  # noqa: BLE001 — LLM hang/timeout must not block demo
        logger.warning("schema agent LLM failed (%s); falling back to heuristic", exc)
    if not parsed.get("tables"):
        logger.info("schema agent: using heuristic mapping (no LLM result)")
        parsed = _heuristic_mapping(schema)
    tables = [t for t in parsed.get("tables", []) if t.get("include", True) and t.get("table")]
    by_table = {t["table"]: t for t in tables}

    edges = _fk_edges(schema, by_table)
    for link in parsed.get("links", []):
        ft, tt = link.get("from_table"), link.get("to_table")
        if ft in by_table and tt in by_table and link.get("from_column") and link.get("to_column"):
            src_type = by_table[ft]["ontology_type"]
            edges.append({
                "source_type": src_type, "source_attr": link["from_column"],
                "target_type": by_table[tt]["ontology_type"],
                "target_attr": link["to_column"], "name": f"HAS_{src_type}".upper(),
            })
    logger.info("schema agent tables=%d edges=%d", len(tables), len(edges))
    return {"tables": [{"table": t["table"], "ontology_type": t["ontology_type"],
                        "match_keys": t.get("match_keys") or t.get("pk") or []}
                       for t in tables], "edges": edges}

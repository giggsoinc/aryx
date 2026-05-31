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
    parsed = _parse(llm_runtime.chat("menial", sys, user)[0])
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

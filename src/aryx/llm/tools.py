"""Graph retrieval over GraphReader, with a record of which calls fired.

Small local models are unreliable at free-form tool-calling, so the Ask flow
drives retrieval deterministically here and lets the LLM interpret/answer. Each
graph call is logged so the UI can show exactly what was queried.
"""
from __future__ import annotations

from typing import Any

from aryx.graph import GraphReader


def retrieve(reader: GraphReader, terms: list[str]) -> tuple[str, list[str]]:
    """Look up each term, expand one hop, gather provenance.

    Returns a compact text context for the LLM and the list of tool calls made.
    """
    calls: list[str] = []
    seen: set[int] = set()
    blocks: list[str] = []

    for term in terms[:5]:
        calls.append(f"search_entities(name={term!r})")
        for ent in reader.find_entities(name=term, limit=5):
            eid = ent["id"]
            if eid in seen:
                continue
            seen.add(eid)
            lines = [f"{ent['name']} [{ent['type']}] (id {eid})"]

            calls.append(f"get_neighbors({eid})")
            for n in reader.neighbors(eid):
                arrow = "->" if n["direction"] == "out" else "<-"
                lines.append(f"  {arrow} {n['relationship']} {n['name']} [{n['type']}]")

            calls.append(f"get_provenance({eid})")
            prov = reader.provenance(eid)
            if prov:
                srcs = ", ".join(f"{p['system']}.{p['dataset']}" for p in prov)
                lines.append(f"  source: {srcs}")
            blocks.append("\n".join(lines))

    context = "\n\n".join(blocks) if blocks else "No matching entities in the graph."
    return context, calls


def all_types(reader: GraphReader) -> list[str]:
    """Distinct ontology types present — helps the parser pick search terms."""
    types: set[str] = set()
    for e in reader.find_entities(limit=500):
        types.add(e["type"])
    return sorted(types)


def to_rows(calls: list[str]) -> list[dict[str, Any]]:
    """Shape tool calls for JSON responses."""
    return [{"call": c} for c in calls]

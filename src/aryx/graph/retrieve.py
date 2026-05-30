"""Deterministic graph retrieval for the Ask flow.

Small local models are unreliable at free-form tool-calling, so retrieval is
driven here and the LLM only interprets the question and writes the answer.
Each graph call is recorded so the UI can show exactly what was queried.
"""
from __future__ import annotations

from aryx.graph.reader import GraphReader


def all_types(reader: GraphReader) -> list[str]:
    """Distinct ontology types present — helps the parser pick search terms."""
    return sorted({e["type"] for e in reader.find_entities(limit=500)})


def _lookup(reader: GraphReader, term: str) -> list[dict]:
    """Find entities for a term; if a phrase misses, retry on its longest words.

    Handles phrasing drift ('umbrella company' -> entity 'Umbrella Co') that a
    plain substring match would miss.
    """
    hits = reader.find_entities(name=term, limit=5)
    if not hits and " " in term:
        for word in sorted(term.split(), key=len, reverse=True):
            if len(word) > 2:
                hits = reader.find_entities(name=word, limit=5)
                if hits:
                    break
    return hits


def retrieve(reader: GraphReader, terms: list[str]) -> tuple[str, list[str]]:
    """Look up terms, expand one hop, gather provenance.

    Returns a compact text context for the LLM and the graph calls made.
    """
    calls: list[str] = []
    seen: set[int] = set()
    blocks: list[str] = []

    for term in terms[:5]:
        calls.append(f"search_entities(name={term!r})")
        for ent in _lookup(reader, term):
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

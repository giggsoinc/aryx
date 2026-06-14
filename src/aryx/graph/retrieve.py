"""Deterministic graph retrieval for the Ask flow.

Small local models are unreliable at free-form tool-calling, so retrieval is
driven here and the LLM only interprets the question and writes the answer.
Each graph call is recorded so the UI can show exactly what was queried.

Retrieval gathers *structured* entity records (``gather``); the text context
the LLM reads and the grounding record the Accuracy Lab verifies are both
projected from that same structure, so the answer and its provenance can never
drift apart.
"""
from __future__ import annotations

from typing import Any

from aryx.ask.evidence import RetrievedEntity
from aryx.graph.reader import GraphReader

__all__ = ["RetrievedEntity", "all_types", "gather", "render_context", "retrieve"]


def all_types(reader: GraphReader) -> list[str]:
    """Distinct ontology types present — helps the parser pick search terms."""
    return sorted({e["type"] for e in reader.find_entities(limit=500)})


def _lookup(reader: GraphReader, term: str) -> list[dict]:
    """Find entities for a term.

    Tries in order: (1) numeric id lookup ('378' -> entity id=378), (2) substring
    name match, (3) fallback to the longest word in a phrase. Numeric-id lookup
    is needed because pipeline-derived entity names are often a non-id column
    (e.g. ticket.status='open'), so plain name search misses 'ticket 378'.
    """
    digits = "".join(ch for ch in term if ch.isdigit())
    if digits and len(digits) <= 9:
        ent = reader.get_entity(int(digits))
        if ent:
            return [ent]
    hits = reader.find_entities(name=term, limit=5)
    if not hits and " " in term:
        for word in sorted(term.split(), key=len, reverse=True):
            if len(word) > 2 and not word.isdigit():
                hits = reader.find_entities(name=word, limit=5)
                if hits:
                    break
    return hits


def gather(reader: GraphReader, terms: list[str]) -> tuple[list[RetrievedEntity], list[str]]:
    """Look up terms, expand one hop, gather provenance — as structured records.

    Returns the deduplicated entities and the exact graph calls made.
    """
    calls: list[str] = []
    seen: set[int] = set()
    out: list[RetrievedEntity] = []

    for term in terms[:5]:
        digits = "".join(ch for ch in term if ch.isdigit())
        if digits and len(digits) <= 9:
            calls.append(f"get_entity(id={int(digits)})")
        else:
            calls.append(f"search_entities(name={term!r})")
        for ent in _lookup(reader, term):
            eid = ent["id"]
            if eid in seen:
                continue
            seen.add(eid)
            calls.append(f"get_neighbors({eid})")
            neighbors = reader.neighbors(eid)
            calls.append(f"get_provenance({eid})")
            sources = reader.provenance(eid)
            out.append(RetrievedEntity(id=eid, type=ent["type"], name=ent["name"],
                                       neighbors=neighbors, sources=sources))
    return out, calls


def render_context(entities: list[RetrievedEntity]) -> str:
    """Project structured entities into the compact text the LLM reads."""
    blocks: list[str] = []
    for ent in entities:
        lines = [f"{ent.name} [{ent.type}] (id {ent.id})"]
        for n in ent.neighbors:
            arrow = "->" if n["direction"] == "out" else "<-"
            lines.append(f"  {arrow} {n['relationship']} {n['name']} [{n['type']}]")
        if ent.sources:
            srcs = ", ".join(f"{p['system']}.{p['dataset']}" for p in ent.sources)
            lines.append(f"  source: {srcs}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "No matching entities in the graph."


def retrieve(reader: GraphReader, terms: list[str]) -> tuple[str, list[str]]:
    """Back-compat wrapper: structured gather projected to (context, calls)."""
    entities, calls = gather(reader, terms)
    return render_context(entities), calls

"""Schema diagram — entity TYPES as nodes, relationship TYPES as edges.

Distinct from the Graph canvas (which shows instances). This view is the
"diagrammatic representation of the lightweight ontology" — the type-
level schema that comes out of discovery / import, before HITL approval
turns parts of it into the heavyweight, governed ontology.
"""
from __future__ import annotations

from typing import Any

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

_NODE_COLOR_OBSERVED = "#3FB6FF"   # Lightweight observed
_NODE_COLOR_APPROVED = "#1E3A8A"   # Approved (heavyweight)
_EDGE_COLOR = "#2D7DFF"


def _node_color(status: str) -> str:
    return _NODE_COLOR_OBSERVED if status == "proposed" else _NODE_COLOR_APPROVED


def render(types: list[dict[str, Any]], rels: list[dict[str, Any]]) -> None:
    """Render the type-relationship schema diagram via streamlit-agraph.

    Uses TYPE names as node ids. Edges between types are derived from the
    list_browse rel rows when the rel.name contains both endpoints' type
    names — best effort; cleanest after relationships gain explicit
    (source_type, target_type) fields.
    """
    if not types and not rels:
        st.info("Nothing to diagram yet — run Ingest or Import.")
        return
    type_names = {t.get("name", "") for t in types if t.get("name")}
    nodes: list[Node] = []
    for t in types:
        name = t.get("name") or ""
        if not name:
            continue
        nodes.append(Node(
            id=name,
            label=f"{name}\nowl:Class",
            size=max(20, min(40, 18 + int(t.get("instance_count", 0) ** 0.5))),
            color=_node_color(str(t.get("status", "approved"))),
        ))
    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()
    for r in rels:
        rname = r.get("name", "") or ""
        # Heuristic: if rel name happens to contain a type name pair, link.
        src = next((n for n in type_names if n and n.lower() in rname.lower()),
                   None)
        tgt = next((n for n in type_names
                    if n and n != src and n.lower() in rname.lower()), None)
        if not src or not tgt:
            continue
        key = (src, tgt, rname)
        if key in seen:
            continue
        seen.add(key)
        edges.append(Edge(source=src, target=tgt, label=rname,
                          color=_EDGE_COLOR))
    config = Config(width=900, height=480, directed=True, physics=True,
                    hierarchical=False, nodeHighlightBehavior=True,
                    collapsible=False)
    agraph(nodes=nodes, edges=edges, config=config)
    st.caption("🟦 Lightweight (proposed) · 🟪 Approved (heavyweight) · "
               "🔗 Edges shown when a relationship type references two "
               "entity-type names. Add explicit source/target on "
               "relationships to enrich this view.")

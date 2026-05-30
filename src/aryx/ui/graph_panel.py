"""Graph canvas panel — all entities + relationships, filterable by type."""
from __future__ import annotations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from aryx.ui import api

TYPE_COLORS: dict[str, str] = {
    "Customer": "#4A90E2",
    "SupportTicket": "#E8775A",
    "Organization": "#50C878",
    "Person": "#9B59B6",
    "Contract": "#F1C40F",
    "Vendor": "#1ABC9C",
}
DEFAULT_COLOR = "#95A5A6"
TYPE_SIZES: dict[str, int] = {"SupportTicket": 12}
DEFAULT_SIZE = 20


def render() -> None:
    st.subheader("Knowledge Graph")

    try:
        data = api.full_graph()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return

    entities = data.get("entities", [])
    relationships = data.get("relationships", [])

    all_types = sorted({e["type"] for e in entities})
    selected = st.multiselect("Filter by type", all_types, default=all_types)

    visible_ids = {e["id"] for e in entities if e["type"] in selected}

    nodes = [
        Node(
            id=str(e["id"]),
            label=e["name"] or f"#{e['id']}",
            size=TYPE_SIZES.get(e["type"], DEFAULT_SIZE),
            color=TYPE_COLORS.get(e["type"], DEFAULT_COLOR),
            title=f"{e['type']}: {e['name']}",
        )
        for e in entities if e["id"] in visible_ids
    ]

    edges = [
        Edge(
            source=str(r["source"]),
            target=str(r["target"]),
            label=r["name"],
        )
        for r in relationships
        if r["source"] in visible_ids and r["target"] in visible_ids
    ]

    config = Config(
        width=900, height=600,
        directed=True, physics=True, hierarchical=False,
        nodeHighlightBehavior=True, highlightColor="#F7A7A6",
    )

    st.caption(f"{len(nodes)} entities · {len(edges)} relationships")
    agraph(nodes=nodes, edges=edges, config=config)

    with st.expander("Raw data"):
        col1, col2 = st.columns(2)
        col1.write("**Entities**")
        col1.dataframe([{"id": e["id"], "type": e["type"], "name": e["name"]}
                        for e in entities if e["id"] in visible_ids])
        col2.write("**Relationships**")
        col2.dataframe(relationships)

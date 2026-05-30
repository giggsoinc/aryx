"""Graph canvas — balanced layout, readable labels, click a node to explore."""
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
TYPE_SIZES: dict[str, int] = {"SupportTicket": 22}
DEFAULT_SIZE = 30
NODE_FONT = {"size": 18, "color": "#FFFFFF", "face": "Inter, sans-serif", "strokeWidth": 4,
             "strokeColor": "#0e1117"}
EDGE_FONT = {"size": 14, "color": "#C8D0DC", "strokeWidth": 4, "strokeColor": "#0e1117"}


def _legend(types: list[str]) -> None:
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;margin:0 14px 6px 0;">'
        f'<span style="width:14px;height:14px;border-radius:50%;background:'
        f'{TYPE_COLORS.get(t, DEFAULT_COLOR)};display:inline-block;margin-right:6px;"></span>'
        f'<span style="font-size:0.95rem;color:#c8d0dc">{t}</span></span>'
        for t in types
    )
    st.markdown(chips, unsafe_allow_html=True)


def _detail(entity_id: int) -> None:
    try:
        ent = api.search_entities()
        match = next((e for e in ent if str(e["id"]) == str(entity_id)), None)
        neighbors = api.get_neighbors(int(entity_id))
        prov = api.get_provenance(int(entity_id))
    except Exception as exc:
        st.warning(f"Could not load node detail: {exc}")
        return
    name = match["name"] if match else f"#{entity_id}"
    st.markdown(f"### {name}")
    if neighbors:
        st.markdown("**Connections**")
        for n in neighbors:
            arrow = "→" if n["direction"] == "out" else "←"
            st.markdown(f"- {arrow} `{n['relationship']}` **{n['name']}** ({n['type']})")
    if prov:
        srcs = ", ".join(f"{p['system']}.{p['dataset']}" for p in prov)
        st.caption(f"Source: {srcs}")


def render() -> None:
    st.title("Knowledge Graph")

    try:
        data = api.full_graph()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return

    entities = data.get("entities", [])
    relationships = data.get("relationships", [])
    all_types = sorted({e["type"] for e in entities})

    selected = st.multiselect("Filter by type", all_types, default=all_types)
    search = st.text_input("Search by name", placeholder="e.g. Acme, T-001")

    visible = {
        e["id"] for e in entities
        if e["type"] in selected
        and (not search or search.lower() in (e["name"] or "").lower())
    }

    _legend(selected)
    st.caption(f"{len(visible)} entities · "
               f"{sum(1 for r in relationships if r['source'] in visible and r['target'] in visible)} "
               f"relationships shown")

    nodes = [
        Node(
            id=str(e["id"]),
            label=e["name"] or f"#{e['id']}",
            size=TYPE_SIZES.get(e["type"], DEFAULT_SIZE),
            color=TYPE_COLORS.get(e["type"], DEFAULT_COLOR),
            title=f"{e['type']}: {e['name']}",
            font=NODE_FONT,
        )
        for e in entities if e["id"] in visible
    ]
    edges = [
        Edge(source=str(r["source"]), target=str(r["target"]), label=r["name"],
             font=EDGE_FONT, color="#5a6678", width=2)
        for r in relationships
        if r["source"] in visible and r["target"] in visible
    ]

    config = Config(
        width=1200, height=680,
        directed=True, physics=True, hierarchical=False,
        nodeHighlightBehavior=True, highlightColor="#F7A7A6",
        nodeSpacing=260, linkLength=240,
    )

    clicked = agraph(nodes=nodes, edges=edges, config=config)

    if clicked:
        with st.container(border=True):
            _detail(clicked)

    with st.expander("Raw data"):
        col1, col2 = st.columns(2)
        col1.write("**Entities**")
        col1.dataframe([{"id": e["id"], "type": e["type"], "name": e["name"]}
                        for e in entities if e["id"] in visible])
        col2.write("**Relationships**")
        col2.dataframe(relationships)

"""Graph page — interactive canvas with search, filter, drill-down, path."""
from __future__ import annotations

import streamlit as st
from streamlit_agraph import agraph

from aryx.ui import api
from aryx.ui.graph_canvas import (
    build_edges, build_nodes, canvas_config, derive_degree, legend_html,
)
from aryx.ui.graph_detail import detail, path_explorer


def _toolbar(types: list[str]) -> tuple[list[str], str, bool]:
    selected = st.multiselect("Filter by type", types, default=types,
                              label_visibility="collapsed", placeholder="Filter by type")
    col1, col2 = st.columns([3, 1])
    search = col1.text_input("Search by name", placeholder="e.g. Acme, T-001",
                             label_visibility="collapsed")
    hide_iso = col2.checkbox("Hide isolated", value=False)
    return selected, search, hide_iso


def _visible_ids(entities: list[dict], rels: list[dict], selected: list[str],
                 search: str, hide_iso: bool, focus: int | None) -> set[int]:
    """Resolve which entity ids the canvas should render right now."""
    if focus is not None:
        keep: set[int] = {focus}
        for r in rels:
            if r["source"] == focus:
                keep.add(r["target"])
            if r["target"] == focus:
                keep.add(r["source"])
        return keep
    base = {e["id"] for e in entities
            if e["type"] in selected
            and (not search or search.lower() in (e["name"] or "").lower())}
    if hide_iso:
        connected = {r["source"] for r in rels} | {r["target"] for r in rels}
        base &= connected
    return base


def render() -> None:
    st.title("Knowledge Graph")
    try:
        data = api.full_graph()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return
    entities = data.get("entities", [])
    rels = data.get("relationships", [])
    all_types = sorted({e["type"] for e in entities})

    selected, search, hide_iso = _toolbar(all_types)
    focus = st.session_state.get("focus_id")
    if focus is not None and st.button("✕ Clear focus", type="secondary"):
        st.session_state.pop("focus_id", None)
        focus = None

    visible = _visible_ids(entities, rels, selected, search, hide_iso, focus)
    st.markdown(legend_html(selected), unsafe_allow_html=True)
    st.caption(f"Showing {len(visible)} of {len(entities)} entities · "
               f"{sum(1 for r in rels if r['source'] in visible and r['target'] in visible)} "
               f"of {len(rels)} relationships")

    with st.expander("🛣 Find a path between two entities", expanded=False):
        hi_nodes, hi_pairs = path_explorer(entities)
        for hid in hi_nodes:
            visible.add(hid)

    left, right = st.columns([3, 1])
    with left:
        nodes = build_nodes(entities, visible, derive_degree(entities, rels), hi_nodes)
        edges = build_edges(rels, visible, hi_pairs)
        clicked = agraph(nodes=nodes, edges=edges, config=canvas_config())
        if clicked is not None:
            st.session_state.selected_id = clicked
    with right:
        sel = st.session_state.get("selected_id")
        if sel is None:
            st.info("Click any node to drill down.")
        else:
            detail(entities, sel)

    with st.expander("Raw data"):
        c1, c2 = st.columns(2)
        c1.write("**Entities**")
        c1.dataframe([{"id": e["id"], "type": e["type"], "name": e["name"]}
                      for e in entities if e["id"] in visible])
        c2.write("**Relationships**")
        c2.dataframe(rels)

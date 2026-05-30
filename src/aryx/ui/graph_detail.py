"""Drill-down panel and path-explorer UI for the graph page."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def detail(entities: list[dict], entity_id: int) -> None:
    """Render the right-hand drill-down for a clicked node."""
    match = next((e for e in entities if str(e["id"]) == str(entity_id)), None)
    if not match:
        st.info("Pick a node on the canvas to see its details.")
        return
    st.markdown(f"### {match['name']}")
    st.caption(f"{match['type']} · id {match['id']}")

    if st.button("Focus on this node", use_container_width=True):
        st.session_state.focus_id = int(entity_id)
        st.rerun()

    try:
        neighbors = api.get_neighbors(int(entity_id))
    except Exception as exc:
        st.warning(f"Cannot load neighbors: {exc}")
        neighbors = []
    if neighbors:
        st.markdown("**Connections**")
        by_rel: dict[str, list[dict]] = {}
        for n in neighbors:
            by_rel.setdefault(n["relationship"], []).append(n)
        for rel, items in by_rel.items():
            with st.expander(f"{rel} ({len(items)})", expanded=True):
                for n in items:
                    arrow = "→" if n["direction"] == "out" else "←"
                    st.markdown(f"{arrow} **{n['name']}** _({n['type']})_")
    else:
        st.caption("No connections recorded.")

    try:
        prov = api.get_provenance(int(entity_id))
    except Exception:
        prov = []
    if prov:
        srcs = ", ".join(f"{p['system']}.{p['dataset']}" for p in prov)
        st.caption(f"Source: {srcs}")


def path_explorer(entities: list[dict]) -> tuple[set[int], set[tuple[int, int]]]:
    """Render the path UI; return (highlighted node ids, edge pairs)."""
    if not entities:
        return set(), set()
    options = {f"{e['name']} ({e['type']}, id {e['id']})": e["id"] for e in entities}
    keys = list(options.keys())
    col1, col2 = st.columns(2)
    a_label = col1.selectbox("From", keys, index=0, key="path_from")
    b_label = col2.selectbox("To", keys, index=min(1, len(keys) - 1), key="path_to")
    if not st.button("Find shortest path", use_container_width=True):
        return set(), set()
    a_id, b_id = options[a_label], options[b_label]
    if a_id == b_id:
        st.info("Pick two different entities.")
        return set(), set()
    try:
        steps = api.get_path(a_id, b_id)
    except Exception as exc:
        st.error(f"Path lookup failed: {exc}")
        return set(), set()
    if not steps:
        st.warning("No path found within 6 hops.")
        return set(), set()
    names = " → ".join(f"**{s['name']}**" for s in steps)
    st.success(f"{len(steps) - 1} hop(s): {names}")
    ids = {s["id"] for s in steps}
    pairs = {(steps[i]["id"], steps[i + 1]["id"]) for i in range(len(steps) - 1)}
    return ids, pairs

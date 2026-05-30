"""Ask panel — query the graph with natural language-style questions."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _answer(query: str) -> str:
    entities = api.search_entities(name=query)
    if not entities:
        return f"No entities found matching '{query}'."

    lines = []
    for e in entities[:5]:
        lines.append(f"**{e['name']}** (type: {e['type']}, id: {e['id']})")
        try:
            neighbors = api.get_neighbors(e["id"])
        except Exception:
            neighbors = []
        if neighbors:
            for n in neighbors:
                direction = "→" if n["direction"] == "out" else "←"
                lines.append(f"  {direction} [{n['relationship']}] {n['name']} ({n['type']})")
        try:
            prov = api.get_provenance(e["id"])
        except Exception:
            prov = []
        if prov:
            sources = ", ".join(f"{p['system']}.{p['dataset']}" for p in prov)
            lines.append(f"  *Source: {sources}*")
        lines.append("")
    return "\n".join(lines)


def render() -> None:
    st.subheader("Ask the Graph")
    st.caption("Type a company name, ticket ref, or keyword — the graph finds all connections.")

    if "history" not in st.session_state:
        st.session_state.history = []

    query = st.text_input("Ask anything", placeholder="e.g. Acme Corp, open tickets, Globex")

    if st.button("Search", type="primary") and query:
        with st.spinner("Traversing graph…"):
            try:
                answer = _answer(query)
            except Exception as exc:
                answer = f"Error: {exc}"
        st.session_state.history.insert(0, (query, answer))

    for q, a in st.session_state.history:
        with st.container(border=True):
            st.markdown(f"**Q:** {q}")
            st.markdown(a)

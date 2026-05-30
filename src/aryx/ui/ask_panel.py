"""Ask panel — chat UX over the graph; shows which API tools were called."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _answer(query: str) -> tuple[str, list[str]]:
    tools: list[str] = [f"search_entities(name={query!r})"]
    entities = api.search_entities(name=query)
    if not entities:
        return f"No entities found matching **{query}**.", tools

    lines: list[str] = []
    for e in entities[:5]:
        lines.append(f"**{e['name']}** · _{e['type']}_ · `id {e['id']}`")
        try:
            neighbors = api.get_neighbors(e["id"])
            tools.append(f"get_neighbors({e['id']})")
        except Exception:
            neighbors = []
        for n in neighbors:
            arrow = "→" if n["direction"] == "out" else "←"
            lines.append(f"&nbsp;&nbsp;{arrow} `{n['relationship']}` {n['name']} ({n['type']})")
        try:
            prov = api.get_provenance(e["id"])
            tools.append(f"get_provenance({e['id']})")
        except Exception:
            prov = []
        if prov:
            srcs = ", ".join(f"{p['system']}.{p['dataset']}" for p in prov)
            lines.append(f"&nbsp;&nbsp;_source: {srcs}_")
        lines.append("")
    return "\n".join(lines), tools


def render() -> None:
    st.title("Ask the Graph")
    st.caption("Type a company name, ticket ref, or keyword — Aryx finds every connection.")

    if "chat" not in st.session_state:
        st.session_state.chat = []

    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["text"], unsafe_allow_html=True)
            if msg.get("tools"):
                with st.expander("Tools called"):
                    for t in msg["tools"]:
                        st.code(t, language="text")

    query = st.chat_input("e.g. Acme Corp, open tickets, Globex")
    if not query:
        return

    st.session_state.chat.append({"role": "user", "text": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Traversing graph…"):
            try:
                answer, tools = _answer(query)
            except Exception as exc:
                answer, tools = f"Error: {exc}", []
        st.markdown(answer, unsafe_allow_html=True)
        if tools:
            with st.expander("Tools called"):
                for t in tools:
                    st.code(t, language="text")

    st.session_state.chat.append({"role": "assistant", "text": answer, "tools": tools})

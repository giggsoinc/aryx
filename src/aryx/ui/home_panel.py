"""Home panel — welcome screen with a plain-English summary and how-to steps."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api

_STEPS = [
    ("Ingest", "Point Aryx at a database table (or drop a file). It reads the rows, "
               "resolves duplicates, and writes entities into the knowledge graph."),
    ("Ask", "Type a company, ticket, or keyword. Aryx traverses the graph and shows "
            "every connected entity, the relationships between them, and where each fact came from."),
    ("Graph", "See the whole picture as an interactive canvas. Filter by type, follow "
              "relationships, and click any node to explore its neighbours."),
]


def _stat_row() -> None:
    try:
        graph = api.full_graph()
        runs = api.list_runs()
        c1, c2, c3 = st.columns(3)
        c1.metric("Entities", len(graph.get("entities", [])))
        c2.metric("Relationships", len(graph.get("relationships", [])))
        c3.metric("Ingest runs", len(runs))
    except Exception:
        st.info("Connect a source on the **Ingest** tab to get started.")


def render() -> None:
    st.title("Aryx")
    st.markdown(
        '<p class="aryx-hero">Aryx turns your scattered data — database tables, '
        "support tickets, documents — into a single <b>knowledge graph</b> you can "
        "query in plain language and explore visually.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    _stat_row()
    st.divider()

    st.subheader("How to use Aryx")
    for i, (title, body) in enumerate(_STEPS, start=1):
        st.markdown(
            f'<div class="aryx-step"><span class="num">{i}</span>'
            f"<b>{title}</b><br><span style='color:#aab3c0'>{body}</span></div>",
            unsafe_allow_html=True,
        )

    st.caption("Use the sidebar to move through **Ingest → Ask → Graph** in order.")

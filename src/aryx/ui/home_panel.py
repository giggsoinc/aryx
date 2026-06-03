"""Home panel — welcome screen with a plain-English summary and how-to steps."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from aryx.ui import api

_ASSETS = Path(__file__).parent / "assets"
_BANNER = _ASSETS / "Aryx_Banner.png"

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
    # Banner image already contains "ARYX · A Fortress of Structured Knowledge
    # · Turn messy enterprise knowledge…" — only show the CSS brandbar when
    # the image is missing, so the same message never appears twice.
    if _BANNER.is_file():
        st.image(str(_BANNER), use_container_width=True)
    else:
        st.markdown(
            '<div class="aryx-brandbar">'
            '<h1>ARYX</h1>'
            '<span class="tag">A Fortress of Structured Knowledge</span>'
            '<p class="aryx-hero" style="color:#E7ECF7;margin-top:0.9rem;">'
            "Turn messy enterprise knowledge into "
            "<b>structured intelligence</b> — a single knowledge graph you "
            "can query in plain English and explore visually.</p></div>",
            unsafe_allow_html=True,
        )

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

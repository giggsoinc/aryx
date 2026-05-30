"""Aryx Streamlit UI — graph canvas, Q&A, and data ingestion."""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Aryx",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from aryx.ui import ask_panel, graph_panel, ingest_panel  # noqa: E402

PAGES = {
    "🕸️  Graph": graph_panel,
    "💬  Ask": ask_panel,
    "➕  Ingest": ingest_panel,
}

with st.sidebar:
    st.title("Aryx")
    st.caption("Knowledge graph platform")
    st.divider()
    page = st.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.caption("v1.0 · [Graph API](/docs)")

PAGES[page].render()

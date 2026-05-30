"""Aryx Streamlit UI — welcome, ingest, ask, and graph canvas."""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Aryx",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from aryx.ui import (  # noqa: E402
    ask_panel, graph_panel, home_panel, ingest_panel, settings_panel, theme,
)

theme.inject()

PAGES = {
    "🏠  Home": home_panel,
    "➕  Ingest": ingest_panel,
    "💬  Ask": ask_panel,
    "🕸️  Graph": graph_panel,
    "⚙️  Settings": settings_panel,
}

with st.sidebar:
    st.title("Aryx")
    st.caption("Knowledge graph platform")
    st.divider()
    page = st.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.caption("v1.0 · [Graph API](/docs)")

PAGES[page].render()

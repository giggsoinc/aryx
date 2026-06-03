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
    ask_panel, brief_panel, graph_panel, home_panel, ingest_panel,
    observability_panel, ontology_panel, settings_panel, theme, workspace_bar,
)

theme.inject()

PAGES = {
    "🏠  Home": home_panel,
    "📋  Brief": brief_panel,
    "➕  Ingest": ingest_panel,
    "💬  Ask": ask_panel,
    "🕸️  Graph": graph_panel,
    "🦉  Ontology": ontology_panel,
    "📊  Observability": observability_panel,
    "⚙️  Settings": settings_panel,
}

_nav_target = st.session_state.pop("nav_target", None)
with st.sidebar:
    workspace_bar.render()
    st.divider()
    _labels = list(PAGES.keys())
    _idx = _labels.index(_nav_target) if _nav_target in _labels else 0
    page = st.radio("Navigate", _labels, index=_idx,
                    label_visibility="collapsed", key="nav_radio")
    st.divider()
    st.caption("v1.0 · [Graph API](/docs)")

PAGES[page].render()

"""Ontology page — browse, export, and import the workspace ontology.

Browse shows what's in the ontology today (types, relationships) so the page
is useful before a user even thinks about RDF. Export and Import become
secondary tabs for semantic-web tool interop.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import (
    ontology_client, ontology_rules, ontology_sections, ontology_versions,
    workspace_summary,
)


def _config() -> dict:
    try:
        return ontology_client.config()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return {}


def _what_is() -> None:
    with st.expander("ℹ️  What is this page for?", expanded=False):
        st.markdown(
            "**Types & relationships = your business vocabulary.** "
            "An ontology defines what 'Customer', 'Contract', 'Ticket' mean "
            "to *your* business and how they connect.\n\n"
            "- **Browse** — see the vocabulary Aryx has learned from your data.\n"
            "- **Export** — open it in Protégé / GraphDB / load into a SPARQL store.\n"
            "- **Import** — bring a standard vocabulary (schema.org, FIBO) so "
            "Aryx classifies your data using it."
        )


def render() -> None:
    """Ontology page — Browse / Export / Import."""
    st.title("Ontology")
    workspace_summary.render("Ontology")
    _what_is()
    cfg = _config()
    if not cfg:
        return
    if not cfg.get("enabled"):
        st.info("Ontology interchange is **disabled** in Settings — "
                "you can still Browse below.")
    try:
        ext_by_format = {f["name"]: f["extension"]
                         for f in ontology_client.formats()}
    except Exception:
        ext_by_format = {}
    tabs = st.tabs(["🔎 Browse", "🧠 Rules", "🕘 Versions",
                    "📤 Export", "📥 Import"])
    with tabs[0]:
        ontology_sections.browse()
    with tabs[1]:
        ontology_rules.render()
    with tabs[2]:
        ontology_versions.render()
    with tabs[3]:
        if cfg.get("enabled"):
            ontology_sections.export_(cfg, ext_by_format)
        else:
            st.warning("Enable ontology interchange in Settings to export.")
    with tabs[4]:
        if cfg.get("enabled"):
            ontology_sections.import_()
        else:
            st.warning("Enable ontology interchange in Settings to import.")

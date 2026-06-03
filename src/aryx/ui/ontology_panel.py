"""Ontology page — staged lifecycle view.

Lifecycle (matches the deck's slides 5/6/8 and the user's brief):
    Brief → Ingest → 🟦 Lightweight (observed)
                      ↓ HITL review
                     🟪 Heavyweight (governed)
                      ↓ Rules + Versions
                     📤 Publish

Each tab below is one stage. The Brief stage lives on its own top-nav
page; Ingest is upstream of this view; everything else surfaces here.
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
    with st.expander("ℹ️  Ontology lifecycle — Brief → Lightweight → "
                     "HITL → Heavyweight → Publish", expanded=False):
        st.markdown(
            "**1 · Brief** (top-nav) — competency questions ground intent.\n"
            "**2 · Ingest** (top-nav) — sources feed the discovery agent.\n"
            "**3 · 🟦 Lightweight (observed)** — proposed `owl:Class` + "
            "`owl:ObjectProperty` Aryx surfaced from the data + brief.\n"
            "**4 · 👤 HITL Review** — human approves / edits proposed types.\n"
            "**5 · 🟪 Heavyweight (governed)** — rules + versioned "
            "snapshots. Inferred edges (`INF_*`) come from this stage.\n"
            "**6 · 📤 Publish** — serialise to Turtle / JSON-LD / RDF-XML "
            "for Protégé, GraphDB, Apache Jena, any SPARQL store."
        )


def render() -> None:
    """Ontology page — staged lifecycle tabs."""
    st.title("🦉 Ontology")
    workspace_summary.render("Ontology")
    _what_is()
    cfg = _config()
    if not cfg:
        return
    if not cfg.get("enabled"):
        st.info("Publish + Import are disabled in Settings — Lightweight "
                "and Heavyweight stages remain available.")
    try:
        ext_by_format = {f["name"]: f["extension"]
                         for f in ontology_client.formats()}
    except Exception:
        ext_by_format = {}
    tabs = st.tabs([
        "🟦 Lightweight (observed)",
        "🟪 Heavyweight: Rules",
        "🟪 Heavyweight: Versions",
        "📤 Publish",
        "📥 Import vocabulary",
    ])
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
            st.warning("Enable interchange in Settings to publish.")
    with tabs[4]:
        if cfg.get("enabled"):
            ontology_sections.import_()
        else:
            st.warning("Enable interchange in Settings to import.")

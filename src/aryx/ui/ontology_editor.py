"""Inline ontology editor — add a new type with attributes.

Split out of ontology_sections to keep that module under the line budget.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import ontology_client


def render_add_type_form() -> None:
    """Manual type editor — add a new entity type with attributes."""
    with st.expander("➕ Add a new entity type", expanded=False):
        with st.form("add_type_form", clear_on_submit=True):
            name = st.text_input("Type name", placeholder="Vendor")
            attrs_raw = st.text_input(
                "Attributes (comma-separated: name, value_type)",
                placeholder="name:string, country:string, founded:int",
            )
            submitted = st.form_submit_button("Add type", type="primary")
        if not (submitted and name.strip()):
            return
        attrs: dict[str, str] = {}
        for part in (attrs_raw or "").split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                attrs[k.strip()] = v.strip()
            elif part.strip():
                attrs[part.strip()] = "string"
        try:
            ontology_client.add_type(name.strip(), attrs)
            st.success(f"Added type '{name.strip()}'.")
            st.rerun()
        except Exception as exc:
            st.error(f"Add failed: {exc}")

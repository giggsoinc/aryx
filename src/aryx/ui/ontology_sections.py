"""Ontology page section renderers — browse / export / import.

Split out of ontology_panel.py to keep each module within the line budget.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import (
    api, ontology_client, ontology_diagram, ontology_editor, ontology_publish,
    toast as _toast,
)


def _approve_button(name: str, key: str) -> None:
    """Approve a proposed type — HITL stage transition."""
    if not st.button(f"✅ Approve '{name}'", key=key, type="primary"):
        return
    ws = api.current_workspace()
    try:
        ontology_client.approve_type(name)
        _toast.notify(f"Approved '{name}' (HITL)", kind="ok", stage="HITL",
                      action="approve_type", target=name, workspace_id=ws)
        st.rerun()
    except Exception as exc:
        _toast.notify(f"Approve failed: {exc}", kind="error", stage="HITL",
                      action="approve_type", target=name, workspace_id=ws)


def browse() -> None:
    """List approved types + relationships; surface proposed types for review."""
    try:
        data = ontology_client.list_types()
    except Exception as exc:
        st.error(f"Cannot load ontology: {exc}")
        return
    types = data.get("types", []) or []
    rels = data.get("relationships", []) or []
    if not types and not rels:
        st.info("No ontology defined yet — run **Ingest** and Aryx will "
                "propose types, or **Import** a vocabulary.")
        return
    proposed = [t for t in types if t.get("status") == "proposed"]
    approved = [t for t in types if t.get("status") != "proposed"]
    if proposed:
        st.markdown(f"### 🟡 Pending review ({len(proposed)})")
        st.caption("These types were proposed by ingest discovery or an "
                   "import. Approve them to make them part of the ontology.")
        for t in proposed:
            cols = st.columns([3, 2, 2])
            cols[0].markdown(f"**{t.get('name')}** · "
                             f"_{(t.get('source') or 'discovery')}_")
            cols[1].caption(f"attrs: "
                            f"{', '.join((t.get('attributes') or {}).keys()) or '—'}")
            with cols[2]:
                _approve_button(t.get("name", "?"), f"appr_{t.get('name')}")
        st.divider()
    st.markdown(f"### ✅ Approved entity types · owl:Class ({len(approved)})")
    if approved:
        st.dataframe(
            [{"owl:Class": t.get("name"),
              "Instances": t.get("instance_count", 0),
              "Source": t.get("source") or "approved",
              "owl:DatatypeProperty": ", ".join(
                  (t.get("attributes") or {}).keys())[:60]}
             for t in approved],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No approved types yet — approve some above.")
    st.markdown("### 🔗 Relationship types · owl:ObjectProperty")
    if rels:
        st.dataframe(
            [{"owl:ObjectProperty": r.get("name"),
              "Count": r.get("count", 0)} for r in rels],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No relationships yet.")
    st.divider()
    with st.expander("🖼  Lightweight ontology — schema diagram",
                     expanded=True):
        ontology_diagram.render(types, rels)
    ontology_editor.render_add_type_form()


def export_(cfg: dict, ext_by_format: dict[str, str]) -> None:
    """Publish stage — delegated to ontology_publish.render()."""
    ontology_publish.render(cfg, ext_by_format)


def import_() -> None:
    """Upload an external ontology to seed proposed types."""
    st.caption("Bring a standard vocabulary (schema.org, FIBO, a Protégé file). "
               "Classes become **proposed** types that pass the review gate.")
    uploaded = st.file_uploader(
        "Ontology file",
        type=["ttl", "owl", "rdf", "xml", "jsonld", "json", "nt", "n3"])
    fmt = st.selectbox("Format", ["auto", "turtle", "json-ld", "xml", "n-triples"])
    if st.button("Import ontology") and uploaded is not None:
        content = uploaded.getvalue().decode("utf-8", errors="replace")
        try:
            result = ontology_client.import_doc(
                content, "" if fmt == "auto" else fmt, uploaded.name)
        except Exception as exc:
            st.error(f"Import failed: {exc}")
            return
        count = result.get("imported", 0)
        if count:
            st.success(f"Imported {count} type(s) as proposed.")
            st.write(", ".join(result.get("types", [])))
            st.info(result.get("message", ""))
        else:
            st.warning(result.get("message", "Nothing imported."))
    elif uploaded is None:
        st.caption("⬆️  Upload a file to enable import.")

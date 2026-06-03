"""Ontology page section renderers — browse / export / import.

Split out of ontology_panel.py to keep each module within the line budget.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import api, ontology_client

_TOOL_HINTS = {
    "turtle": "Protégé, GraphDB, Apache Jena, Stardog",
    "json-ld": "Web apps, Google Rich Results, JSON-LD playground",
    "xml": "Protégé, legacy RDF stores, OWL API tools",
    "n-triples": "Bulk loaders, line-by-line streaming, dump/diff",
}
_MEDIA_BY_EXT = {
    "ttl": "text/turtle", "jsonld": "application/ld+json",
    "rdf": "application/rdf+xml", "nt": "application/n-triples",
}


def browse() -> None:
    """List entity types + attributes + relationship types in this workspace."""
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
    st.markdown("**Entity types**")
    if types:
        st.dataframe(
            [{"Type": t.get("name"), "Status": t.get("status", "approved"),
              "Instances": t.get("instance_count", 0),
              "Description": (t.get("description") or "")[:80]}
             for t in types],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No types yet.")
    st.markdown("**Relationship types**")
    if rels:
        st.dataframe(rels, use_container_width=True, hide_index=True)
    else:
        st.caption("No relationships yet.")


def export_(cfg: dict, ext_by_format: dict[str, str]) -> None:
    """Render the export controls: pick a format, generate, download."""
    formats = cfg.get("formats", [])
    if not formats:
        st.warning("No export formats enabled. Add some in Settings.")
        return
    try:
        live = ontology_client.list_types()
        n_types = len(live.get("types", []) or [])
        n_ents = int(live.get("entity_count", 0))
    except Exception:
        n_types = n_ents = -1
    if n_types == 0 and n_ents == 0:
        st.warning("This workspace has nothing to export yet — ingest data "
                   "or import a vocabulary.")
        return
    fmt = st.selectbox("Format", formats,
                       format_func=lambda f: f"{f}  ·  {_TOOL_HINTS.get(f, '')}")
    st.caption(f"Opens in: {_TOOL_HINTS.get(fmt, 'any RDF tool')}")
    if st.button("Generate export", type="primary"):
        try:
            payload = ontology_client.export(fmt)
        except Exception as exc:
            st.error(f"Export failed: {exc}")
            return
        ext = ext_by_format.get(fmt, "ttl")
        st.session_state["onto_export"] = {
            "bytes": payload, "ext": ext,
            "mime": _MEDIA_BY_EXT.get(ext, "application/octet-stream"),
        }
        st.success(f"Generated {len(payload):,} bytes of {fmt} "
                   f"({n_types} classes · {n_ents} individuals).")
    blob = st.session_state.get("onto_export")
    if blob:
        ws = api.current_workspace()
        st.download_button(
            "⬇️  Download ontology file", data=blob["bytes"],
            file_name=f"aryx_ws{ws}.{blob['ext']}", mime=blob["mime"],
        )
        with st.expander("Preview (first 1,500 chars)"):
            st.code(blob["bytes"].decode("utf-8", errors="replace")[:1500],
                    language="turtle")


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
        sent_fmt = "" if fmt == "auto" else fmt
        try:
            result = ontology_client.import_doc(content, sent_fmt, uploaded.name)
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

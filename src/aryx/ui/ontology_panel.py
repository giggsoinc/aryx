"""Ontology page — export the graph to RDF/OWL and import external ontologies.

Seamless bridge to semantic-web tooling: one click downloads the active
workspace as Turtle/JSON-LD/RDF-XML/N-Triples for Protégé, GraphDB, Apache
Jena, or any SPARQL store; the importer pulls a standard vocabulary back in as
proposed types. Hidden until enabled in Settings (export_runtime).
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import api
from aryx.ui import ontology_client

# Tools known to consume each format — shown as guidance, not validated.
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


def _config() -> dict:
    """Fetch the interchange config, surfacing API errors inline."""
    try:
        return ontology_client.config()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return {}


def _export_section(cfg: dict, ext_by_format: dict[str, str]) -> None:
    """Render the export controls: pick a format, generate, download."""
    st.subheader("Export — graph → RDF / OWL")
    formats = cfg.get("formats", [])
    if not formats:
        st.warning("No export formats enabled. Add some in Settings.")
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
        st.success(f"Generated {len(payload):,} bytes of {fmt}.")

    blob = st.session_state.get("onto_export")
    if blob:
        ws = api.current_workspace()
        st.download_button(
            "⬇️  Download ontology file",
            data=blob["bytes"],
            file_name=f"aryx_ws{ws}.{blob['ext']}",
            mime=blob["mime"],
        )
        with st.expander("Preview (first 1,500 chars)"):
            text = blob["bytes"].decode("utf-8", errors="replace")
            st.code(text[:1500], language="turtle")


def _import_section() -> None:
    """Render the import controls: upload a vocabulary, seed proposed types."""
    st.subheader("Import — external ontology → proposed types")
    st.caption("Bring a standard vocabulary (schema.org, FIBO, a Protégé file). "
               "Classes become **proposed** types that pass the review gate "
               "before the discovery agent uses them.")

    uploaded = st.file_uploader(
        "Ontology file",
        type=["ttl", "owl", "rdf", "xml", "jsonld", "json", "nt", "n3"],
    )
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
            st.success(f"Imported {count} type(s) as proposed "
                       f"(format: {result.get('format')}).")
            st.write(", ".join(result.get("types", [])))
            st.info(result.get("message", ""))
        else:
            st.warning(result.get("message", "Nothing imported."))
    elif uploaded is None:
        st.caption("⬆️  Upload a file to enable import.")


def render() -> None:
    """Ontology interchange page; gated behind the Settings toggle."""
    st.title("Ontology — RDF / OWL interchange")

    cfg = _config()
    if not cfg:
        return
    if not cfg.get("enabled"):
        st.info("Ontology interchange is **disabled**. Enable it in "
                "**Settings → Ontology interchange** to export and import.")
        return

    try:
        ext_by_format = {f["name"]: f["extension"] for f in ontology_client.formats()}
    except Exception:
        ext_by_format = {}

    st.markdown("Export your knowledge graph for semantic-web tools, or import "
                "an external ontology to guide discovery.")
    tab_export, tab_import = st.tabs(["📤  Export", "📥  Import"])
    with tab_export:
        _export_section(cfg, ext_by_format)
    with tab_import:
        _import_section()

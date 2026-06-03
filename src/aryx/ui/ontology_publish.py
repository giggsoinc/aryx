"""Publish stage — serialise the workspace ontology to RDF/OWL formats."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api, ontology_client, toast as _toast

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


def render(cfg: dict, ext_by_format: dict[str, str]) -> None:
    """Render the publish controls: pick a format, generate, download."""
    formats = cfg.get("formats", [])
    if not formats:
        st.warning("No publish formats enabled. Add some in Settings.")
        return
    try:
        live = ontology_client.list_types()
        n_types = len(live.get("types", []) or [])
        n_ents = int(live.get("entity_count", 0))
    except Exception:
        n_types = n_ents = -1
    if n_types == 0 and n_ents == 0:
        st.warning("Nothing to publish — derive a Heavyweight ontology first.")
        return
    fmt = st.selectbox("Format", formats,
                       format_func=lambda f: f"{f}  ·  {_TOOL_HINTS.get(f, '')}")
    st.caption(f"Opens in: {_TOOL_HINTS.get(fmt, 'any RDF tool')}")
    if st.button("Publish", type="primary"):
        try:
            payload = ontology_client.export(fmt)
        except Exception as exc:
            st.error(f"Publish failed: {exc}")
            return
        ext = ext_by_format.get(fmt, "ttl")
        st.session_state["onto_export"] = {
            "bytes": payload, "ext": ext,
            "mime": _MEDIA_BY_EXT.get(ext, "application/octet-stream"),
        }
        _toast.notify(f"Published as {fmt} ({n_types} cls · {n_ents} ind)",
                      kind="stage", stage="Publish",
                      action="publish_export", target=fmt,
                      workspace_id=api.current_workspace())
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

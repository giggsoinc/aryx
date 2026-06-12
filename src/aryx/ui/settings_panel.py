"""Settings panel — choose the model/provider Ask uses, live (no restart).

Swapping the model does not change Ask's behaviour; only which engine answers.
Keys are sent to the API and held in process memory, never written to disk/git.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import api, ontology_client, settings_mcp, settings_tokens

_PROVIDERS = {
    "Local (Ollama)": "ollama",
    "Claude (Anthropic)": "anthropic",
    "OpenAI / compatible": "openai",
    "Gemini (OpenAI-compatible)": "google",
}
_DEFAULT_ENDPOINT = {
    "ollama": "http://ollama:11434",
    "anthropic": "",
    "openai": "https://api.openai.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def _current() -> dict:
    """Fetch the active LLM config, surfacing API errors inline."""
    try:
        return api.get_llm_config()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return {}


def render() -> None:
    """Render the Settings page: LLM provider + ontology interchange config."""
    st.title("Settings — Model Provider")
    st.caption("Pick the engine that answers questions. Local needs no key; "
               "cloud providers need an API key. Ask works the same either way.")

    cur = _current()
    if cur:
        chip = "🔑 key set" if cur.get("api_key_set") else "🔓 no key (local)"
        st.info(f"Active: **{cur.get('provider')}** · answer model "
                f"`{cur.get('answer_model')}` · {chip}")

    with st.form("llm_settings"):
        label = st.selectbox("Provider", list(_PROVIDERS.keys()))
        provider = _PROVIDERS[label]
        col1, col2 = st.columns(2)
        menial = col1.text_input("Fast model (term extraction)", value=cur.get("menial_model", ""))
        answer = col2.text_input("Answer model", value=cur.get("answer_model", ""))
        endpoint = st.text_input("Endpoint / base URL", value=_DEFAULT_ENDPOINT.get(provider, ""))
        api_key = st.text_input("API key (leave blank for local)", type="password")
        saved = st.form_submit_button("Save", type="primary")

    if saved:
        cfg = {"provider": provider, "menial_model": menial, "answer_model": answer,
               "endpoint": endpoint, "api_key": api_key}
        try:
            new = api.set_llm_config({k: v for k, v in cfg.items() if v})
            st.success(f"Saved. Ask now uses **{new.get('provider')}** · `{new.get('answer_model')}`.")
        except Exception as exc:
            st.error(f"Failed to save: {exc}")

    st.divider()
    _ontology_section()
    st.divider()
    settings_mcp.render()
    st.divider()
    settings_tokens.render()
    st.divider()
    _danger_zone()


def _danger_zone() -> None:
    """Factory reset — wipe all data and non-Default workspaces."""
    st.subheader("Danger zone")
    st.caption("Factory reset deletes **all** data across every workspace: "
               "entities, relationships, jobs, ontology, graph, actions, "
               "adjudication queue, ask history. Only the Default workspace "
               "survives (empty). This cannot be undone.")
    if st.button("☢️ Factory Reset (Nuke)", key="nuke_btn"):
        st.session_state["_nuke_confirm"] = True
    if st.session_state.get("_nuke_confirm"):
        st.error("⚠️ **This will permanently delete ALL data in ALL "
                 "workspaces.** Type `NUKE` to confirm.")
        confirm = st.text_input("Type NUKE to confirm", key="nuke_text")
        if st.button("Confirm factory reset", key="nuke_yes",
                      type="primary"):
            if confirm.strip() == "NUKE":
                try:
                    result = api.nuke_system()
                    st.session_state.pop("_nuke_confirm", None)
                    removed = result.get("workspaces_removed", 0)
                    st.success(f"Factory reset complete. "
                               f"{removed} workspace(s) removed.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Nuke failed: {exc}")
            else:
                st.warning("Type exactly `NUKE` to confirm.")


def _ontology_section() -> None:
    """Enable + configure the RDF/OWL interchange plugin (export & import)."""
    st.subheader("Ontology interchange (RDF / OWL)")
    st.caption("Turn this on to export your graph for semantic-web tools "
               "(Protégé, GraphDB, Apache Jena) and import external ontologies. "
               "When enabled, an **Ontology** page appears in the sidebar.")

    try:
        cur = ontology_client.config()
    except Exception as exc:
        st.error(f"Cannot reach API: {exc}")
        return

    available = cur.get("available", [])
    if cur.get("enabled"):
        st.success(f"Enabled · formats: {', '.join(cur.get('formats', [])) or '—'}")
    else:
        st.info("Disabled — turn on below to expose export/import.")

    with st.form("ontology_settings"):
        enabled = st.checkbox("Enable ontology export & import",
                              value=bool(cur.get("enabled")))
        formats = st.multiselect("Export formats", options=available,
                                 default=cur.get("formats", []))
        base_uri = st.text_input("Base URI (IRI prefix for exported terms)",
                                 value=cur.get("base_uri", "https://aryx.local/"))
        include_prov = st.checkbox("Include provenance (source records) in export",
                                   value=bool(cur.get("include_provenance", True)))
        saved = st.form_submit_button("Save ontology settings", type="primary")

    if saved:
        try:
            new = ontology_client.set_config({
                "enabled": enabled, "formats": formats,
                "base_uri": base_uri, "include_provenance": include_prov,
            })
            state = "on" if new.get("enabled") else "off"
            st.success(f"Saved. Ontology interchange is **{state}**.")
        except Exception as exc:
            st.error(f"Failed to save: {exc}")

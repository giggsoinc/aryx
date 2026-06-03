"""Sidebar workspace selector — switch, create, edit context, delete spaces."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _brand_mark() -> None:
    """Render the ARYX wordmark + tagline at the top of the sidebar."""
    st.markdown(
        '<div class="aryx-sidebar-mark">'
        '<div class="word">ARYX</div>'
        '<div class="tagline">A Fortress of Structured Knowledge</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def _context_editor(ws: dict) -> None:
    """Edit the workspace-level business context (shared by all tabs)."""
    current = ws.get("context", "") or ""
    new = st.text_area(
        "Business context",
        value=current,
        placeholder="e.g., Customer support data: companies, tickets, contracts, SLAs.",
        height=110,
        key=f"ws_ctx_{ws.get('id', 0)}",
        help="One description per workspace — used by Ingest, Ask, and Ontology.",
    )
    if new != current and st.button("Save context", key=f"ws_ctx_save_{ws['id']}"):
        try:
            api.set_workspace_context(int(ws["id"]), new)
            st.success("Context saved.")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")


def render() -> None:
    """Render the sidebar: brand mark, workspace picker, context, manage."""
    _brand_mark()
    st.divider()
    try:
        spaces = api.list_workspaces()
    except Exception as exc:
        st.error(f"Workspaces unavailable: {exc}")
        return
    if not spaces:
        return

    by_label = {w["name"]: w for w in spaces}
    labels = list(by_label.keys())
    current_id = api.current_workspace()
    current = next((lbl for lbl, w in by_label.items() if w["id"] == current_id),
                   labels[0])
    choice = st.selectbox("Workspace", labels, index=labels.index(current))
    chosen = by_label[choice]
    api.set_workspace(chosen["id"])

    with st.expander("Manage workspace"):
        _context_editor(chosen)
        st.divider()
        new_name = st.text_input("New workspace name", key="ws_new",
                                 placeholder="e.g. Sales Support")
        if st.button("Create", key="ws_create") and new_name.strip():
            try:
                created = api.create_workspace(new_name.strip())
                api.set_workspace(created["id"])
                st.rerun()
            except Exception as exc:
                st.error(f"Create failed: {exc}")
        if chosen["id"] != 1 and st.button(f"Delete '{choice}'", key="ws_del"):
            try:
                api.delete_workspace(chosen["id"])
                api.set_workspace(1)
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")

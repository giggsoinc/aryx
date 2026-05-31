"""Sidebar workspace selector — switch, create, and delete isolated spaces."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def render() -> None:
    try:
        spaces = api.list_workspaces()
    except Exception as exc:
        st.error(f"Workspaces unavailable: {exc}")
        return
    if not spaces:
        return

    by_label = {w["name"]: w["id"] for w in spaces}
    labels = list(by_label.keys())
    current = next((lbl for lbl, wid in by_label.items() if wid == api.current_workspace()),
                   labels[0])
    choice = st.selectbox("Workspace", labels, index=labels.index(current))
    api.set_workspace(by_label[choice])

    with st.expander("Manage workspaces"):
        new_name = st.text_input("New workspace name", key="ws_new",
                                 placeholder="e.g. Sales Support")
        if st.button("Create", key="ws_create") and new_name.strip():
            try:
                created = api.create_workspace(new_name.strip())
                api.set_workspace(created["id"])
                st.rerun()
            except Exception as exc:
                st.error(f"Create failed: {exc}")
        if by_label[choice] != 1 and st.button(f"Delete '{choice}'", key="ws_del"):
            try:
                api.delete_workspace(by_label[choice])
                api.set_workspace(1)
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")

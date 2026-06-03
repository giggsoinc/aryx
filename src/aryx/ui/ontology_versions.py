"""Ontology page → Versions tab: snapshots + change log."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api_ext


def _snapshot_form() -> None:
    """Create a new version snapshot of types + rules."""
    label = st.text_input(
        "Snapshot label", key="ver_label",
        placeholder="e.g. After Platinum rule added",
    )
    if st.button("📸 Take snapshot", type="primary", key="ver_snap"):
        try:
            row = api_ext.snapshot_version(label or "manual")
            st.success(f"Snapshot v{row.get('version_no')} created.")
            st.rerun()
        except Exception as exc:
            st.error(f"Snapshot failed: {exc}")


def _versions_table(versions: list[dict]) -> None:
    """Display recent snapshots, newest first."""
    if not versions:
        st.info("No snapshots yet — take one to start versioning.")
        return
    st.markdown("**Snapshots**")
    rows = []
    for v in versions:
        types_count = len(v.get("types_json") or [])
        rules_count = len(v.get("rules_json") or [])
        rows.append({
            "Version": f"v{v.get('version_no')}",
            "Label": v.get("label") or "—",
            "Types": types_count,
            "Rules": rules_count,
            "Created at": v.get("created_at"),
            "By": v.get("created_by") or "—",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _changes_table(changes: list[dict]) -> None:
    """Show the ontology change log."""
    if not changes:
        st.info("No changes logged yet.")
        return
    st.markdown("**Recent changes**")
    st.dataframe(
        [{"When": c.get("changed_at"), "Actor": c.get("actor"),
          "Op": c.get("op"), "Kind": c.get("target_kind"),
          "Target": c.get("target_name")} for c in changes],
        use_container_width=True, hide_index=True,
    )


def render() -> None:
    """Render the Versions tab content."""
    st.markdown(
        "Snapshots freeze your current types + rules so you can roll back or "
        "compare later. Every edit also writes to the change log below."
    )
    try:
        versions = api_ext.list_versions(limit=25)
    except Exception as exc:
        st.error(f"Cannot load versions: {exc}")
        versions = []
    _versions_table(versions)
    _snapshot_form()
    st.divider()
    try:
        changes = api_ext.change_log(limit=50)
    except Exception as exc:
        st.error(f"Cannot load change log: {exc}")
        changes = []
    _changes_table(changes)

"""Ingest panel — trigger aryx pipeline from the UI."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def render() -> None:
    st.subheader("Add Data Source")

    with st.form("ingest_db"):
        st.write("**Database Table**")
        col1, col2 = st.columns(2)
        table = col1.text_input("Table name", placeholder="demo_customers")
        otype = col2.text_input("Ontology type", placeholder="Customer")
        match_keys = st.text_input("Match keys (comma-separated)", placeholder="full_name,email")
        system = st.text_input("Source system label", value="postgresql")
        key_col = st.text_input("Primary key column", value="id")
        submitted = st.form_submit_button("Ingest Table", type="primary")

    if submitted:
        if not all([table, otype, match_keys]):
            st.warning("Table, ontology type, and match keys are required.")
        else:
            with st.spinner(f"Queuing ingestion of {table}…"):
                try:
                    result = api.ingest_db(table, otype, match_keys, system, key_col)
                    st.success(f"Queued: {result}")
                except Exception as exc:
                    st.error(f"Failed: {exc}")

    st.divider()
    st.subheader("Recent Runs")
    if st.button("Refresh"):
        st.rerun()

    try:
        runs = api.list_runs()
        if runs:
            for r in runs:
                status_icon = {"complete": "✅", "running": "⏳", "failed": "❌"}.get(
                    r.get("status", ""), "⚪"
                )
                st.markdown(
                    f"{status_icon} **Run {r['run_id']}** — "
                    f"`{r['source_system']}.{r['source_dataset']}` — "
                    f"{r['record_count']} records — {r['status']}"
                )
        else:
            st.info("No runs yet.")
    except Exception as exc:
        st.error(f"Cannot load runs: {exc}")

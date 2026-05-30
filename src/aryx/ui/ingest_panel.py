"""Ingest panel — trigger a DB-table ingest and watch run status."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api

_STATUS_ICON = {"complete": "✅", "running": "⏳", "failed": "❌"}


def _ingest_form() -> None:
    with st.form("ingest_db"):
        st.markdown("#### Database table")
        col1, col2 = st.columns(2)
        table = col1.text_input("Table name", placeholder="demo_customers")
        otype = col2.text_input("Ontology type", placeholder="Customer")
        match_keys = st.text_input("Match keys (comma-separated)", placeholder="full_name,email")
        col3, col4 = st.columns(2)
        system = col3.text_input("Source system label", value="postgresql")
        key_col = col4.text_input("Primary key column", value="id")
        submitted = st.form_submit_button("Ingest table", type="primary")

    if submitted:
        if not all([table, otype, match_keys]):
            st.warning("Table, ontology type, and match keys are required.")
            return
        with st.spinner(f"Queuing ingestion of {table}…"):
            try:
                api.ingest_db(table, otype, match_keys, system, key_col)
                st.success(f"Queued **{table}** — refresh Sources below to watch progress.")
            except Exception as exc:
                st.error(f"Failed: {exc}")


def _sources() -> None:
    head, btn = st.columns([4, 1])
    head.subheader("Sources")
    if btn.button("Refresh"):
        st.rerun()
    try:
        runs = api.list_runs()
    except Exception as exc:
        st.error(f"Cannot load runs: {exc}")
        return
    if not runs:
        st.info("No sources ingested yet. Use the form above to add your first table.")
        return

    total = sum(r.get("record_count") or 0 for r in runs)
    c1, c2 = st.columns(2)
    c1.metric("Sources", len(runs))
    c2.metric("Records ingested", total)

    st.dataframe(
        [
            {
                "Run": r["run_id"],
                "Status": f"{_STATUS_ICON.get(r.get('status', ''), '⚪')} {r.get('status', '')}",
                "Source": f"{r['source_system']}.{r['source_dataset']}",
                "Records": r.get("record_count"),
                "Started": r.get("started_at"),
                "Finished": r.get("finished_at"),
            }
            for r in runs
        ],
        use_container_width=True,
        hide_index=True,
    )


def render() -> None:
    st.title("Add a Data Source")
    st.caption("Connect a Postgres table — Aryx reads the rows, resolves duplicates, "
               "and writes entities into the graph.")
    _ingest_form()
    st.divider()
    _sources()

"""Ingest panel — trigger a DB-table ingest and watch live stage progress."""
from __future__ import annotations

import time

import streamlit as st

from aryx.ui import api

_TERMINAL = {"complete", "failed"}
_ICON = {"complete": "✅", "failed": "❌", "running": "⏳", "queued": "🕓"}


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

        with st.expander("Link to another entity (optional)", expanded=False):
            st.caption("Connect each row to another entity by matching a column to that entity's attribute "
                       "(e.g. customer_name → Customer.full_name as HAS_TICKET).")
            link_col1, link_col2, link_col3 = st.columns(3)
            link_attr = link_col1.text_input("My column", placeholder="customer_name")
            link_type = link_col2.text_input("Target entity type", placeholder="Customer")
            link_target_attr = link_col3.text_input("Target attribute", placeholder="full_name")
            link_name = st.text_input("Edge label", placeholder="HAS_TICKET")

        submitted = st.form_submit_button("Ingest table", type="primary")

    if submitted:
        if not all([table, otype, match_keys]):
            st.warning("Table, ontology type, and match keys are required.")
            return
        fk_links = []
        if all([link_attr, link_type, link_target_attr, link_name]):
            fk_links.append({
                "source_type": otype, "source_attr": link_attr,
                "target_type": link_type, "target_attr": link_target_attr,
                "name": link_name,
            })
        try:
            resp = api.ingest_db(table, otype, match_keys, system, key_col, fk_links=fk_links)
            st.session_state.active_job = resp.get("job_id")
        except Exception as exc:
            st.error(f"Failed: {exc}")


def _progress(job_id: str) -> None:
    placeholder = st.empty()
    for _ in range(120):
        try:
            job = api.get_job(job_id)
        except Exception as exc:
            placeholder.error(f"Lost track of job: {exc}")
            return
        with placeholder.container():
            st.progress(min(int(job.get("pct", 0)), 100),
                        text=f"**{job.get('stage', '')}** — {job.get('detail', '')}")
        if job.get("status") in _TERMINAL:
            if job["status"] == "complete":
                st.success(f"Ingestion complete — {job.get('detail', '')}")
            else:
                st.error(f"Ingestion failed: {job.get('error', 'unknown error')}")
            st.session_state.pop("active_job", None)
            return
        time.sleep(1.5)
    st.info("Still running — see Sources below for status.")


def _sources() -> None:
    head, btn = st.columns([4, 1])
    head.subheader("Sources & runs")
    if btn.button("Refresh"):
        st.rerun()
    try:
        jobs = api.list_jobs()
    except Exception as exc:
        st.error(f"Cannot load jobs: {exc}")
        return
    if not jobs:
        st.info("No ingestion jobs yet. Use the form above to add your first table.")
        return
    st.dataframe(
        [
            {
                "Status": f"{_ICON.get(j.get('status', ''), '⚪')} {j.get('status', '')}",
                "Source": f"{j['source_system']}.{j['source_dataset']}",
                "Stage": j.get("stage"),
                "%": j.get("pct"),
                "Started": j.get("started_at"),
                "Run": j.get("run_id"),
            }
            for j in jobs
        ],
        use_container_width=True,
        hide_index=True,
    )


def render() -> None:
    st.title("Add a Data Source")
    st.caption("Connect a Postgres table — Aryx reads the rows, resolves duplicates, "
               "and writes entities into the graph. Watch each agent work below.")
    _ingest_form()
    if st.session_state.get("active_job"):
        st.divider()
        st.subheader("Ingestion progress")
        _progress(st.session_state["active_job"])
    st.divider()
    _sources()

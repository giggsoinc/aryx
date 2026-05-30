"""Ingest panel — DB tables or file uploads, with live pipeline progress."""
from __future__ import annotations

import time

import streamlit as st

from aryx.ui import api

_TERMINAL = {"complete", "failed"}
_ICON = {"complete": "✅", "failed": "❌", "running": "⏳", "queued": "🕓"}


def _db_form() -> None:
    with st.form("ingest_db"):
        col1, col2 = st.columns(2)
        table = col1.text_input("Table name", placeholder="demo_customers")
        otype = col2.text_input("Ontology type", placeholder="Customer")
        match_keys = st.text_input("Match keys (comma-separated)", placeholder="full_name,email")
        col3, col4 = st.columns(2)
        system = col3.text_input("Source system", value="postgresql")
        key_col = col4.text_input("Primary key column", value="id")
        with st.expander("Link to another entity (optional)", expanded=False):
            lc1, lc2, lc3 = st.columns(3)
            la = lc1.text_input("My column", placeholder="customer_name")
            lt = lc2.text_input("Target type", placeholder="Customer")
            lta = lc3.text_input("Target attribute", placeholder="full_name")
            ln = st.text_input("Edge label", placeholder="HAS_TICKET")
        submitted = st.form_submit_button("Ingest table", type="primary")
    if submitted:
        if not all([table, otype, match_keys]):
            st.warning("Table, ontology type, and match keys are required.")
            return
        fk = [{"source_type": otype, "source_attr": la, "target_type": lt,
               "target_attr": lta, "name": ln}] if all([la, lt, lta, ln]) else []
        try:
            resp = api.ingest_db(table, otype, match_keys, system, key_col, fk_links=fk)
            st.session_state.active_job = resp.get("job_id")
        except Exception as exc:
            st.error(f"Failed: {exc}")


_TYPES = ["json", "csv", "pdf", "pptx", "ppt", "docx", "doc", "rtf",
          "jpg", "jpeg", "png", "tiff", "tif", "bmp"]


def _file_form() -> None:
    with st.form("ingest_file"):
        uploaded = st.file_uploader(
            "Upload files (max 50 files, 2 MB each, 50 MB total)",
            type=_TYPES, accept_multiple_files=True,
        )
        col1, col2 = st.columns(2)
        otype = col1.text_input("Ontology type", placeholder="Product", key="file_otype")
        match_keys = col2.text_input("Match keys", placeholder="name,id", key="file_keys")
        submitted = st.form_submit_button("Ingest files", type="primary")
    if submitted:
        if not uploaded or not otype or not match_keys:
            st.warning("Upload at least one file, set ontology type, and match keys.")
            return
        if len(uploaded) > 50:
            st.error("Max 50 files per upload.")
            return
        total = sum(f.size for f in uploaded)
        if total > 50 * 1024 * 1024:
            st.error(f"Total size {total // (1024*1024)} MB exceeds 50 MB limit.")
            return
        try:
            resp = api.ingest_files(uploaded, otype, match_keys)
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
                st.error(f"Ingestion failed: {job.get('error', 'unknown')}")
            st.session_state.pop("active_job", None)
            return
        time.sleep(1.5)
    st.info("Still running — check Sources below.")


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
        st.info("No ingestion jobs yet.")
        return
    st.dataframe(
        [{"Status": f"{_ICON.get(j.get('status',''),'⚪')} {j.get('status','')}",
          "Source": f"{j['source_system']}.{j['source_dataset']}",
          "Stage": j.get("stage"), "%": j.get("pct"),
          "Started": j.get("started_at"), "Run": j.get("run_id")}
         for j in jobs],
        use_container_width=True, hide_index=True,
    )


def render() -> None:
    st.title("Add a Data Source")
    st.caption("Ingest a Postgres table or upload a JSON/CSV file. "
               "PDF/DOCX/PPTX supported when pgvector is deployed.")
    tab_db, tab_file = st.tabs(["Database table", "File upload (JSON/CSV)"])
    with tab_db:
        _db_form()
    with tab_file:
        _file_form()
    if st.session_state.get("active_job"):
        st.divider()
        st.subheader("Ingestion progress")
        _progress(st.session_state["active_job"])
    st.divider()
    _sources()

"""Ingest page — context first, then connect a database or upload documents.

The discovery agent maps database tables to ontology entities from the context;
documents go through the chunk/embed pipeline. Live job progress below.
"""
from __future__ import annotations

import time

import streamlit as st

from aryx.ui import api, ingest_files, ingest_rdb

_TERMINAL = {"complete", "failed"}
_ICON = {"complete": "✅", "failed": "❌", "running": "⏳", "queued": "🕓"}


def _progress(job_id: str) -> None:
    placeholder = st.empty()
    for _ in range(160):
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
        [{"Status": f"{_ICON.get(j.get('status', ''), '⚪')} {j.get('status', '')}",
          "Source": f"{j['source_system']}.{j['source_dataset']}",
          "Stage": j.get("stage"), "%": j.get("pct"),
          "Started": j.get("started_at"), "Run": j.get("run_id")}
         for j in jobs],
        use_container_width=True, hide_index=True,
    )


def render() -> None:
    st.title("Add a Data Source")
    st.caption("Step 1 — say what you're building. Step 2 — connect a database "
               "(the agent finds the right tables) or upload documents.")
    context = st.text_area(
        "What are you building? — context for the discovery agent",
        key="ingest_context",
        placeholder="e.g. A customer-support knowledge graph linking customers "
                    "to their support tickets and the products they use.",
    )
    st.divider()
    tab_db, tab_docs = st.tabs(["🗄 Database (auto-discover)", "📄 Documents (folder)"])
    with tab_db:
        ingest_rdb.render(context)
    with tab_docs:
        ingest_files.render(context)
    if st.session_state.get("active_job"):
        st.divider()
        st.subheader("Ingestion progress")
        _progress(st.session_state["active_job"])
    st.divider()
    _sources()

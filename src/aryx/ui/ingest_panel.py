"""Ingest page — context first, then connect a database or upload documents.

The discovery agent maps database tables to ontology entities from the context;
documents go through the chunk/embed pipeline. Live job progress below.
"""
from __future__ import annotations

import time

import streamlit as st

from aryx.ui import (
    api, ingest_api_source, ingest_files, ingest_rdb, toast as _toast,
    workspace_summary,
)

_TERMINAL = {"complete", "failed"}
_ICON = {"complete": "✅", "failed": "❌", "running": "⏳", "queued": "🕓"}


def _progress(job_id: str) -> None:
    """Poll job status; fire a toast on every stage transition; update bar."""
    placeholder = st.empty()
    last_stage_key = f"stage_seen_{job_id}"
    for _ in range(160):
        try:
            job = api.get_job(job_id)
        except Exception as exc:
            placeholder.error(f"Lost track of job: {exc}")
            return
        stage_now = job.get("stage", "")
        if stage_now and st.session_state.get(last_stage_key) != stage_now:
            st.session_state[last_stage_key] = stage_now
            _toast.notify(
                f"Ingest · {stage_now} — {job.get('detail', '')} "
                f"({int(job.get('pct', 0))}%)",
                kind="stage", stage="Ingest", action=f"stage_{stage_now}",
                target=job_id, workspace_id=api.current_workspace(),
            )
        with placeholder.container():
            st.progress(min(int(job.get("pct", 0)), 100),
                        text=f"**{stage_now}** — {job.get('detail', '')}")
        if job.get("status") in _TERMINAL:
            ws = api.current_workspace()
            if job["status"] == "complete":
                _toast.notify(f"Ingestion complete — {job.get('detail', '')}",
                              kind="stage", stage="Ingest",
                              action="ingest_complete", target=job_id,
                              workspace_id=ws)
            else:
                _toast.notify(f"Ingestion failed: {job.get('error', 'unknown')}",
                              kind="error", stage="Ingest",
                              action="ingest_failed", target=job_id,
                              workspace_id=ws)
            st.session_state.pop("active_job", None)
            return
        time.sleep(1.5)
    st.info("Still running — check Sources below.")


def _ws_name(workspaces: dict[int, str], wid: int) -> str:
    return workspaces.get(int(wid or 0), f"ws-{wid}")


def _sources() -> None:
    """Show table of recent ingestion jobs scoped by workspace."""
    head, btn = st.columns([4, 1])
    head.subheader("Sources & Runs")
    if btn.button("Refresh"):
        st.rerun()
    try:
        jobs = api.list_jobs()
        ws_map = {int(w["id"]): w["name"] for w in api.list_workspaces()}
    except Exception as exc:
        st.error(f"Cannot load jobs: {exc}")
        return
    if not jobs:
        st.info("No ingestion jobs yet.")
        return
    only_active = st.checkbox(
        "Only show jobs in active workspace",
        value=True, key="jobs_only_active",
    )
    active = api.current_workspace()
    rows = [j for j in jobs
            if not only_active or int(j.get("workspace_id", 1)) == int(active)]
    st.dataframe(
        [{"Workspace": _ws_name(ws_map, j.get("workspace_id", 1)),
          "Status": f"{_ICON.get(j.get('status', ''), '⚪')} {j.get('status', '')}",
          "Source": f"{j['source_system']}.{j['source_dataset']}",
          "Stage": j.get("stage"), "%": j.get("pct"),
          "Started": j.get("started_at"), "Run": j.get("run_id")}
         for j in rows],
        use_container_width=True, hide_index=True,
    )


def render() -> None:
    """Main ingest page: tabs for database/documents, progress monitor, jobs."""
    st.title("Ingest")
    ws = workspace_summary.render("Ingest")
    st.markdown("**Add data sources** — Connect a database (agent auto-discovers tables) "
                "or upload documents (agent finds entities). The agent uses your "
                "workspace's business context to know what to look for.")
    st.divider()
    ctx = ws.get("context", "") or ""
    tab_db, tab_docs, tab_api = st.tabs([
        "🗄 Database (auto-discover)", "📄 Documents (folder)",
        "🔌 API / REST",
    ])
    with tab_db:
        ingest_rdb.render(ctx)
    with tab_docs:
        ingest_files.render(ctx)
    with tab_api:
        ingest_api_source.render(ctx)
    if st.session_state.get("active_job"):
        st.divider()
        st.subheader("Ingestion progress")
        _progress(st.session_state["active_job"])
    st.divider()
    _sources()

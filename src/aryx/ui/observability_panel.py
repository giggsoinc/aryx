"""Observability panel — what's been done, what's pending, how much it cost."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _metrics(data: dict) -> None:
    jobs = data.get("jobs", {})
    llm = data.get("llm", {})
    graph = data.get("graph", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jobs total", jobs.get("total", 0))
    c2.metric("LLM calls", llm.get("total_calls", 0))
    c3.metric("Total tokens", f"{llm.get('total_tokens', 0):,}")
    c4.metric("Avg latency", f"{llm.get('avg_latency_ms', 0):,} ms")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Entities", graph.get("entities", 0))
    c6.metric("Relationships", graph.get("relationships", 0))
    c7.metric("Jobs completed", jobs.get("complete", 0))
    c8.metric("Jobs failed", jobs.get("failed", 0))


def _model_config(data: dict) -> None:
    cfg = data.get("model_config", {})
    cols = st.columns(4)
    cols[0].caption(f"**Provider:** {cfg.get('provider', '?')}")
    cols[1].caption(f"**Menial:** {cfg.get('menial_model', '?')}")
    cols[2].caption(f"**Answer:** {cfg.get('answer_model', '?')}")
    cols[3].caption(f"**Key set:** {'yes' if cfg.get('api_key_set') else 'no'}")


def _jobs_table(data: dict) -> None:
    try:
        jobs = api.list_jobs()
    except Exception as exc:
        st.error(f"Cannot load jobs: {exc}")
        return
    if not jobs:
        st.info("No ingestion jobs recorded yet.")
        return
    st.dataframe(
        [
            {
                "Status": j.get("status"),
                "Source": f"{j['source_system']}.{j['source_dataset']}",
                "Stage": j.get("stage"),
                "%": j.get("pct"),
                "Run": j.get("run_id"),
                "Error": j.get("error") or "",
                "Started": j.get("started_at"),
            }
            for j in jobs
        ],
        use_container_width=True,
        hide_index=True,
    )


def _llm_table(data: dict) -> None:
    recent = data.get("llm_recent", [])
    if not recent:
        st.info("No LLM calls recorded yet. Ask a question to generate data.")
        return
    st.dataframe(
        [
            {
                "Role": r.get("role"),
                "Model": r.get("model"),
                "Prompt tok": r.get("prompt_tokens"),
                "Compl tok": r.get("completion_tokens"),
                "Latency": f"{r.get('latency_ms', 0)} ms",
                "Error": r.get("error") or "",
                "Time": r.get("ts"),
            }
            for r in recent
        ],
        use_container_width=True,
        hide_index=True,
    )


def render() -> None:
    st.title("Observability")
    st.caption("What's been done, what's pending, and how much it cost.")

    if st.button("Refresh", type="secondary"):
        st.rerun()

    try:
        data = api.observability()
    except Exception as exc:
        st.error(f"Cannot reach observability API: {exc}")
        return

    _metrics(data)
    st.divider()
    _model_config(data)
    st.divider()

    tab_jobs, tab_llm = st.tabs(["Pipeline jobs", "LLM calls"])
    with tab_jobs:
        _jobs_table(data)
    with tab_llm:
        _llm_table(data)

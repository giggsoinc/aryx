"""Document source — upload files; the agent discovers what's in them for you.

No ontology, no match keys. You drop files, Aryx reads them and shows a plain
summary of the entity types it found; you tick what to keep and confirm.
"""
from __future__ import annotations

import time

import streamlit as st

from aryx.ui import api

_TYPES = ["json", "csv", "pdf", "pptx", "ppt", "docx", "doc", "rtf",
          "jpg", "jpeg", "png", "tiff", "tif", "bmp"]


def _wait_for_read(did: str) -> bool:
    placeholder = st.empty()
    for _ in range(200):
        try:
            job = api.get_job(did)
        except Exception as exc:
            placeholder.error(f"Read failed: {exc}")
            return False
        with placeholder.container():
            st.progress(min(int(job.get("pct", 0)), 100),
                        text=f"{job.get('stage', '')} — {job.get('detail', '')}")
        if job.get("status") == "complete":
            placeholder.empty()
            return True
        if job.get("status") == "failed":
            placeholder.error(f"Reading failed: {job.get('error', 'unknown')}")
            return False
        time.sleep(1.5)
    return False


def _summary_form(did: str) -> None:
    summary = st.session_state.get("docs_summary") or {}
    types = summary.get("types", [])
    files = summary.get("files", [])
    if not types and not files:
        st.info("I couldn't recognise anything. Try clearer files, or add a line of "
                "context above about what they're about.")
        return
    st.markdown("**Here's what I found — keep what you want:**")
    approved_types = [t["type"] for t in types
                      if st.checkbox(f"**{t['type']}** ({t['count']}) — "
                                     f"e.g. {', '.join(t['examples'][:3])}",
                                     value=True, key=f"dt_{t['type']}")]
    approved_files = [f["filename"] for f in files
                      if st.checkbox(f"**{f['filename']}** → {f['ontology_type']}",
                                     value=True, key=f"df_{f['filename']}")]
    if st.button("Confirm & add to graph", type="primary") and (approved_types or approved_files):
        try:
            resp = api.docs_confirm(did, approved_types, approved_files)
            st.session_state.active_job = resp.get("job_id")
            for key in ("docs_did", "docs_summary"):
                st.session_state.pop(key, None)
        except Exception as exc:
            st.error(f"Failed: {exc}")


def render(context: str) -> None:
    uploaded = st.file_uploader(
        "Drop your files here — I'll read them and tell you what's inside "
        "(max 50 files, 2 MB each)", type=_TYPES, accept_multiple_files=True)
    if st.button("Read & discover", type="primary"):
        if not uploaded:
            st.warning("Upload at least one file first.")
        else:
            try:
                st.session_state.docs_did = api.docs_read(uploaded, context).get("discovery_id")
                st.session_state.pop("docs_summary", None)
            except Exception as exc:
                st.error(f"Failed: {exc}")
    did = st.session_state.get("docs_did")
    if did and "docs_summary" not in st.session_state and _wait_for_read(did):
        try:
            st.session_state.docs_summary = api.docs_summary(did)
        except Exception as exc:
            st.error(f"Could not load summary: {exc}")
    if st.session_state.get("docs_did") and "docs_summary" in st.session_state:
        _summary_form(st.session_state.docs_did)

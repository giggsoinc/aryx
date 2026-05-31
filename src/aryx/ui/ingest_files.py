"""Document source — upload a folder of files (select all) for ingestion."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api

_TYPES = ["json", "csv", "pdf", "pptx", "ppt", "docx", "doc", "rtf",
          "jpg", "jpeg", "png", "tiff", "tif", "bmp"]
_MAX_TOTAL = 50 * 1024 * 1024


def render() -> None:
    with st.form("ingest_files"):
        uploaded = st.file_uploader(
            "Upload a folder of files (select all files in it) — "
            "max 50 files, 2 MB each, 50 MB total",
            type=_TYPES, accept_multiple_files=True,
        )
        col1, col2 = st.columns(2)
        otype = col1.text_input("Ontology type", placeholder="Document", key="file_otype")
        match_keys = col2.text_input("Match keys", placeholder="title,name", key="file_keys")
        submitted = st.form_submit_button("Ingest files", type="primary")
    if not submitted:
        return
    if not uploaded or not otype or not match_keys:
        st.warning("Upload at least one file, set an ontology type, and match keys.")
        return
    if len(uploaded) > 50:
        st.error("Max 50 files per upload.")
        return
    total = sum(f.size for f in uploaded)
    if total > _MAX_TOTAL:
        st.error(f"Total size {total // (1024 * 1024)} MB exceeds the 50 MB limit.")
        return
    try:
        resp = api.ingest_files(uploaded, otype, match_keys)
        st.session_state.active_job = resp.get("job_id")
        st.success(f"Queued {resp.get('count', len(uploaded))} file(s).")
    except Exception as exc:
        st.error(f"Failed: {exc}")

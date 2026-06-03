"""Document source — upload files; the agent discovers what's in them for you.

No ontology, no match keys. You drop files, Aryx reads them and shows a plain
summary of the entity types it found; you tick what to keep and confirm.
"""
from __future__ import annotations

import io
import time

import streamlit as st

from aryx.ui import api, ingest_client, upload

_TYPES = ["json", "csv", "xml", "html", "htm", "pdf", "pptx", "ppt",
          "docx", "doc", "rtf", "jpg", "jpeg", "png", "tiff", "tif", "bmp"]


def _extract_context_text(context_file) -> str:
  """Extract text from common file formats for context."""
  try:
    fname = getattr(context_file, "name", "").lower()
    content = context_file.getvalue() if hasattr(context_file, "getvalue") else context_file.read()
    if fname.endswith(".txt"):
      return content.decode("utf-8", errors="ignore")
    if fname.endswith(".pdf"):
      try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
      except Exception:
        return "[PDF extraction failed]"
    if fname.endswith((".docx", ".doc")):
      try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(para.text for para in doc.paragraphs)
      except Exception:
        return "[DOCX extraction failed]"
    return "[Unsupported context file format]"
  except Exception as e:
    return f"[Error reading context: {e}]"


def _wait_for_read(did: str) -> bool:
    """Poll job status until complete, showing progress in UI."""
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
    """Show discovered entity types/files; let user select and confirm ingest."""
    summary = st.session_state.get("docs_summary") or {}
    types = summary.get("types", [])
    files = summary.get("files", [])
    col_btn, col_reset = st.columns([3, 1])
    with col_reset:
      if st.button("🔄 Reset", use_container_width=True):
        for key in ("docs_did", "docs_summary"):
          st.session_state.pop(key, None)
        st.rerun()
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
            resp = ingest_client.docs_confirm(did, approved_types, approved_files)
            st.session_state.active_job = resp.get("job_id")
            for key in ("docs_did", "docs_summary"):
                st.session_state.pop(key, None)
        except Exception as exc:
            st.error(f"Failed: {exc}")


def render(context: str) -> None:
    """Upload files; agent uses workspace context to identify entities."""
    if context.strip():
        st.markdown(
            f'<div class="aryx-ws-summary">📝 <b>Workspace context:</b> '
            f'<i>{context}</i></div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("No business context for this workspace yet — open **Manage "
                   "workspace** in the sidebar to add one.")
    st.subheader("Upload documents", divider=True)
    uploaded = st.file_uploader(
        "Drop files — JSON, CSV, XML, HTML, PDF, Word, PowerPoint, RTF, "
        "or images (max 50 files, 2 MB each)",
        type=_TYPES, accept_multiple_files=True)
    has_context = bool(context.strip())
    has_files = bool(uploaded)
    col_btn, col_status = st.columns([1, 2])
    with col_btn:
      if st.button("Read & discover", type="primary",
                   disabled=not (has_context and has_files)):
        if not has_context:
            st.error("Set workspace business context in the sidebar first.")
        elif not has_files:
            st.error("Upload at least one file.")
        else:
            try:
                st.session_state.docs_did = upload.docs_read(
                    uploaded, context).get("discovery_id")
                st.session_state.pop("docs_summary", None)
            except Exception as exc:
                st.error(f"Failed: {exc}")
    with col_status:
      if not has_context:
        st.caption("⚠️ Set workspace context first")
      elif not has_files:
        st.caption("⚠️ Upload files first")
    did = st.session_state.get("docs_did")
    if did and "docs_summary" not in st.session_state and _wait_for_read(did):
        try:
            st.session_state.docs_summary = ingest_client.docs_summary(did)
        except Exception as exc:
            st.error(f"Could not load summary: {exc}")
    if st.session_state.get("docs_did") and "docs_summary" in st.session_state:
        _summary_form(st.session_state.docs_did)

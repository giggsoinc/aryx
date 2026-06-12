"""Brief page — 5 competency questions, AI-drafted from a seed or document.

The user types one sentence (or uploads a deck / SOW / PDF) and Aryx drafts
all five fields; they then edit a strong draft instead of a blank form. The
brief grounds every extraction / discovery / inference prompt.
"""
from __future__ import annotations

import streamlit as st

from aryx import brief as brief_lib
from aryx.ui import api, brief_client, toast as _toast, workspace_summary

_KEYS = ("brief_domain", "brief_aim", "brief_objectives",
         "brief_scope", "brief_roles")


def _active_brief() -> dict:
    """Fetch the current workspace's saved brief, or empty dict."""
    try:
        wid = api.current_workspace()
        for w in api.list_workspaces():
            if int(w.get("id", 0)) == int(wid):
                return w.get("brief", {}) or {}
    except Exception:
        return {}
    return {}


def _seed_state(existing: dict) -> None:
    """Initialise widget state from the saved brief; reset on workspace switch."""
    wid = api.current_workspace()
    if st.session_state.get("brief_ws") != wid:
        st.session_state["brief_ws"] = wid
        for k in _KEYS:
            st.session_state.pop(k, None)
    st.session_state.setdefault("brief_domain", existing.get("domain", ""))
    st.session_state.setdefault("brief_aim", existing.get("aim", ""))
    st.session_state.setdefault(
        "brief_objectives", "\n".join(existing.get("objectives", []) or []))
    st.session_state.setdefault("brief_scope", existing.get("scope", ""))
    st.session_state.setdefault(
        "brief_roles", "\n".join(existing.get("roles", []) or []))


def _apply_draft(brief: dict) -> None:
    """Write a drafted brief into the five widget slots."""
    st.session_state["brief_domain"] = brief.get("domain", "")
    st.session_state["brief_aim"] = brief.get("aim", "")
    st.session_state["brief_objectives"] = "\n".join(
        brief.get("objectives", []) or [])
    st.session_state["brief_scope"] = brief.get("scope", "")
    st.session_state["brief_roles"] = "\n".join(brief.get("roles", []) or [])


def _hero() -> None:
    """Seed input + document upload → AI draft of all five fields."""
    st.markdown("##### ✨ Start fast — describe it once, or drop a document")
    seed = st.text_input(
        "One sentence", key="brief_seed", label_visibility="collapsed",
        placeholder="e.g. Match support tickets to the right expert agent")
    doc = st.file_uploader("Or upload a brief / deck / SOW",
                           type=["pdf", "docx", "doc", "pptx", "ppt",
                                 "txt", "md"])
    if st.button("✨ Draft my brief", type="primary",
                 use_container_width=True):
        doc_text = brief_client.extract_text(doc)
        if not seed.strip() and not doc_text.strip():
            st.warning("Type a sentence or upload a document first.")
            return
        with st.spinner("Drafting your brief…"):
            try:
                _apply_draft(brief_client.draft_brief(seed, doc_text))
                st.rerun()
            except Exception as exc:
                st.error(f"Draft failed: {exc}")


def _readiness() -> None:
    """Thin depth meter — Generic NER → Grounded → Sharp → Expert."""
    filled = sum(bool(st.session_state.get(k, "").strip()) for k in _KEYS)
    labels = ["Generic NER", "Grounded", "Grounded", "Sharp", "Expert"]
    st.progress(filled / 5, text=f"Brief depth: {labels[filled]}")


def render() -> None:
    """Render the AI-assisted Brief page."""
    st.title("📋 Brief")
    workspace_summary.render("Brief")
    existing = _active_brief()
    _seed_state(existing)

    _hero()
    st.divider()
    st.caption("Review and edit — skip any field and Aryx ingests generically.")

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        st.text_input("1 · Domain of interest", key="brief_domain")
        st.text_area("3 · Objectives (one per line)", key="brief_objectives",
                     height=110)
    with col2:
        st.text_area("2 · Aim — purpose of the knowledge model",
                     key="brief_aim", height=108)
        st.text_area("5 · Participant roles (one per line)", key="brief_roles",
                     height=110)
    st.text_area("4 · Scope — what's IN, what's OUT", key="brief_scope",
                 height=70)
    _readiness()

    if st.button("💾 Save Brief", type="primary", use_container_width=True):
        _save()

    st.divider()
    if brief_lib.is_populated(existing):
        st.subheader("✓ Saved brief")
        st.table({
            "Domain": existing.get("domain", "—"),
            "Aim": existing.get("aim", "—"),
            "Objectives": " | ".join(existing.get("objectives", []) or ["—"]),
            "Scope": existing.get("scope", "—"),
            "Participants": " | ".join(existing.get("roles", []) or ["—"]),
        })
    else:
        st.info("💡 Brief is empty. Aryx ingests generically (NER) until you "
                "draft or fill the five questions.")


def _save() -> None:
    """Persist the five widget fields as the workspace brief."""
    def _lines(key: str) -> list[str]:
        return [ln.strip() for ln in
                st.session_state.get(key, "").splitlines() if ln.strip()]
    payload = {"domain": st.session_state.get("brief_domain", "").strip(),
               "aim": st.session_state.get("brief_aim", "").strip(),
               "objectives": _lines("brief_objectives"),
               "scope": st.session_state.get("brief_scope", "").strip(),
               "roles": _lines("brief_roles")}
    try:
        api.set_workspace_brief(int(api.current_workspace()), payload)
        _toast.notify("Brief saved — Aryx will use it for extraction",
                      kind="stage", stage="Brief", action="save_brief",
                      workspace_id=api.current_workspace())
        st.rerun()
    except Exception as exc:
        _toast.notify(f"Save failed: {exc}", kind="error", stage="Brief",
                      action="save_brief", workspace_id=api.current_workspace())

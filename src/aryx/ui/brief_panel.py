"""Brief page — 5 METHONTOLOGY-style competency questions before Ingest.

User-facing first stage of the ontology lifecycle:
  Brief → Ingest → Lightweight → HITL → Heavyweight → Publish

Captures the workspace's intent so the discovered ontology is grounded
in declared domain, aim, objectives, scope, and participants — not
generic NER.
"""
from __future__ import annotations

import streamlit as st

from aryx import brief as brief_lib
from aryx.ui import api, toast as _toast, workspace_summary


def _list_field(label: str, value: list[str], key: str,
                placeholder: str) -> list[str]:
    """One-line-per-entry text area → list of non-empty strings."""
    raw = st.text_area(label, value="\n".join(value or []), height=110,
                       placeholder=placeholder, key=key)
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _active_brief() -> dict:
    """Fetch the current workspace's brief, or empty dict if none."""
    try:
        wid = api.current_workspace()
        for w in api.list_workspaces():
            if int(w.get("id", 0)) == int(wid):
                return w.get("brief", {}) or {}
    except Exception:
        pass
    return {}


def render() -> None:
    """Render the 5-question Brief form — Q&A with KVP preview."""
    st.title("📋 Brief")
    workspace_summary.render("Brief")
    st.markdown(
        "Answer these 5 questions to ground Aryx's extraction in your domain intent. "
        "Skip any, and Aryx will ingest generically (NER)."
    )

    existing = _active_brief()

    # Q&A Form — 2 columns for compact layout
    col1, col2 = st.columns(2, gap="medium")

    with col1:
        domain = st.text_input(
            "1 · Domain of interest",
            value=existing.get("domain", ""),
            placeholder="e.g. SaaS marketing operations"
        )
        objectives = _list_field(
            "3 · Objectives (one per line)",
            existing.get("objectives", []) or [],
            key="brief_objectives",
            placeholder="Surface expansion signals\nFlag at-risk accounts\n..."
        )

    with col2:
        aim = st.text_area(
            "2 · Aim — purpose of the knowledge model",
            value=existing.get("aim", ""),
            height=108,
            placeholder="What outcome should this graph enable?"
        )
        roles = _list_field(
            "5 · Participant roles (one per line)",
            existing.get("roles", []) or [],
            key="brief_roles",
            placeholder="Customer Success Manager\nData Steward\n..."
        )

    scope = st.text_area(
        "4 · Scope — what's IN, what's OUT",
        value=existing.get("scope", ""),
        height=60,
        placeholder="IN: customers, products, contracts.\nOUT: HR, payroll."
    )

    # Save button
    if st.button("💾 Save Brief", type="primary", use_container_width=True):
        payload = {"domain": domain, "aim": aim, "objectives": objectives,
                   "scope": scope, "roles": roles}
        try:
            api.set_workspace_brief(int(api.current_workspace()), payload)
            _toast.notify("Brief saved — Aryx will use it for extraction",
                          kind="stage", stage="Brief", action="save_brief",
                          workspace_id=api.current_workspace())
            st.rerun()
        except Exception as exc:
            _toast.notify(f"Save failed: {exc}", kind="error", stage="Brief",
                          action="save_brief",
                          workspace_id=api.current_workspace())

    st.divider()

    # Preview as KVP table
    if brief_lib.is_populated(existing):
        st.subheader("✓ Brief Summary")
        preview_data = {
            "Domain": existing.get("domain", "—"),
            "Aim": existing.get("aim", "—"),
            "Objectives": " | ".join(existing.get("objectives", []) or ["—"]),
            "Scope": existing.get("scope", "—"),
            "Participants": " | ".join(existing.get("roles", []) or ["—"]),
        }
        st.table(preview_data)
    else:
        st.info("💡 Brief is empty. Aryx will ingest generically (vanilla NER) until you answer the 5 questions.")

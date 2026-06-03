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
    try:
        wid = api.current_workspace()
        for w in api.list_workspaces():
            if int(w.get("id", 0)) == int(wid):
                return w.get("brief", {}) or {}
    except Exception:
        pass
    return {}


def render() -> None:
    """Render the 5-question Brief form."""
    st.title("📋 Brief — the knowledge-modelling competency questions")
    workspace_summary.render("Brief")
    st.markdown(
        "Answer these **before** you ingest. Aryx uses the brief to ground "
        "entity extraction in your declared intent — so the lightweight "
        "ontology surfaces *Goal / Scope / ValueProposition / Capability* "
        "instead of vanilla NER."
    )
    existing = _active_brief()
    domain = st.text_input("1 · Domain of interest",
                           value=existing.get("domain", ""),
                           placeholder="e.g. SaaS marketing operations")
    aim = st.text_area("2 · Aim — purpose of the knowledge model",
                       value=existing.get("aim", ""), height=80,
                       placeholder="What outcome should this graph enable?")
    objectives = _list_field(
        "3 · Objectives that meet the aim (one per line)",
        existing.get("objectives", []) or [], key="brief_objectives",
        placeholder="Surface expansion signals\nFlag at-risk accounts\n...")
    scope = st.text_area(
        "4 · Scope — what's IN, what's OUT",
        value=existing.get("scope", ""), height=80,
        placeholder="IN: customers, products, contracts.\nOUT: HR, payroll.")
    roles = _list_field(
        "5 · Participant roles (one per line)",
        existing.get("roles", []) or [], key="brief_roles",
        placeholder="Customer Success Manager\nData Steward\nAccount Executive")
    if st.button("💾 Save Brief", type="primary"):
        payload = {"domain": domain, "aim": aim, "objectives": objectives,
                   "scope": scope, "roles": roles}
        try:
            api.set_workspace_brief(int(api.current_workspace()), payload)
            _toast.notify("Brief saved — Aryx will use it for extraction",
                          kind="stage", stage="Brief",
                          action="save_brief",
                          workspace_id=api.current_workspace())
            st.rerun()
        except Exception as exc:
            _toast.notify(f"Save failed: {exc}", kind="error", stage="Brief",
                          action="save_brief",
                          workspace_id=api.current_workspace())
    st.divider()
    if brief_lib.is_populated(existing):
        st.caption("Preview of the prompt context Aryx will use:")
        st.code(brief_lib.serialize(existing), language="markdown")
    else:
        st.warning("Brief is empty. Ingest will still run, but extracted "
                   "entity types may be generic NER instead of domain-specific.")

"""Shared workspace summary banner — surface workspace name, context, counts.

Single component called from Ingest, Ask, Graph, and Ontology pages so the
user always knows which workspace they're acting on, what business context
the agent uses, and how much data the workspace contains.
"""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _counts() -> dict[str, int]:
    """Return entity/relationship/type counts for the active workspace."""
    try:
        g = api.full_graph()
    except Exception:
        return {"entities": 0, "relationships": 0, "types": 0}
    ents = g.get("entities", []) or []
    rels = g.get("relationships", []) or []
    types = {e.get("type") for e in ents if e.get("type")}
    return {"entities": len(ents), "relationships": len(rels), "types": len(types)}


def _active_workspace() -> dict:
    """Return the active workspace row (or a stub if API is unreachable)."""
    try:
        wid = api.current_workspace()
        for w in api.list_workspaces():
            if int(w.get("id", 0)) == int(wid):
                return w
    except Exception:
        pass
    return {"id": 0, "name": "Default", "context": ""}


def render(page: str) -> dict:
    """Render the workspace summary banner; return the active workspace dict."""
    ws = _active_workspace()
    counts = _counts()
    ctx = (ws.get("context") or "").strip()
    ctx_preview = ctx if len(ctx) <= 140 else ctx[:137] + "…"
    ctx_html = (
        f'<div class="muted" style="margin-top:0.3rem;">'
        f"📝 <i>{ctx_preview}</i></div>" if ctx else
        '<div class="muted" style="margin-top:0.3rem;">'
        "⚠️ No business context set — open <b>Manage workspaces</b> in the "
        "sidebar to add one. The agent uses it to find entities.</div>"
    )
    st.markdown(
        f'<div class="aryx-ws-summary">'
        f'<b>Workspace:</b> {ws.get("name", "?")} &nbsp;·&nbsp; '
        f'<b>{counts["entities"]}</b> entities &nbsp;·&nbsp; '
        f'<b>{counts["relationships"]}</b> relationships &nbsp;·&nbsp; '
        f'<b>{counts["types"]}</b> types '
        f'<span class="muted">&nbsp;·&nbsp;{page}</span>'
        f"{ctx_html}</div>",
        unsafe_allow_html=True,
    )
    if counts["entities"] == 0 and page != "Ingest":
        st.info("This workspace has no graph yet — go to **Ingest** to add data.")
    return ws

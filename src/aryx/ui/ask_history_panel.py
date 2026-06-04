"""Persisted Ask-history table + per-row download / View-in-Graph deep link."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api_ext, ask_export


def render() -> None:
    """Render the persisted history table below the live chat."""
    try:
        rows = api_ext.ask_history(limit=50)
    except Exception as exc:
        st.caption(f"⚠️ History unavailable: {exc}")
        return
    if not rows:
        return
    st.markdown("**🗂 Past conversations in this workspace**")
    table = [{
        "When": r.get("asked_at"),
        "Question": (r.get("question") or "")[:60],
        "Answer": (r.get("answer") or "")[:60],
        "Tokens": (r.get("prompt_tokens") or 0)
                   + (r.get("completion_tokens") or 0),
        "Latency": f"{r.get('latency_ms', 0)} ms",
        "Entities": len(r.get("entity_ids") or []),
    } for r in rows]
    st.dataframe(table, use_container_width=True, hide_index=True)
    chat = []
    for r in rows:
        chat.append({"role": "user", "text": r.get("question", "")})
        chat.append({
            "role": "assistant", "text": r.get("answer", ""),
            "tools": r.get("tools_called") or [],
            "entity_ids": r.get("entity_ids") or [],
            "usage": {
                "prompt_tokens": r.get("prompt_tokens", 0),
                "completion_tokens": r.get("completion_tokens", 0),
                "latency_ms": r.get("latency_ms", 0),
                "answer_model": r.get("answer_model", ""),
            },
        })
    with st.expander("⬇️ Download all history"):
        ask_export.download_buttons(chat, key_suffix="history")

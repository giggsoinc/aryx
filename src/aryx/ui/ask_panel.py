"""Ask panel — LLM-backed chat over the graph via the REST /ask endpoint."""
from __future__ import annotations

import re

import streamlit as st

from aryx.ui import (
    api, ask_export, ask_history_panel, toast as _toast, workspace_summary,
)


def _entity_ids_from(resp: dict) -> list[int]:
    """Pull entity ids out of the response (tools_called + plain answer)."""
    ids: set[int] = set()
    for blob in resp.get("tools_called", []) or []:
        for m in re.findall(r"\bid[\s:=]+(\d+)", str(blob)):
            ids.add(int(m))
        for m in re.findall(r"\bentit(?:y|ies)[^0-9]*(\d+)", str(blob), re.I):
            ids.add(int(m))
    text = resp.get("answer", "") or ""
    for m in re.findall(r"#(\d+)\b", text):
        ids.add(int(m))
    return sorted(ids)[:25]

_GENERIC_SAMPLES = [
    "List the entity types in this workspace",
    "Show 5 random entities and how they connect",
    "Which entities have the most relationships?",
    "Summarise what this graph is about",
]


def _samples_for(types: list[str]) -> list[str]:
    """Workspace-aware suggested questions based on observed entity types."""
    if not types:
        return _GENERIC_SAMPLES
    head = types[0]
    out = [
        f"List all {head}s",
        f"Who is connected to a {head}?",
        f"Show 5 random {head}s",
    ]
    if len(types) >= 2:
        out.append(f"How are {types[0]}s related to {types[1]}s?")
    return out


def _sample_chips() -> None:
    """Render clickable suggested questions; clicking auto-submits."""
    try:
        ents = api.full_graph().get("entities", []) or []
    except Exception:
        ents = []
    types = sorted({e.get("type") for e in ents if e.get("type")})
    samples = _samples_for(types)
    st.caption("Try one of these:")
    cols = st.columns(len(samples))
    for i, q in enumerate(samples):
        if cols[i].button(q, key=f"chip_{i}", use_container_width=True):
            st.session_state.queued_question = q
            st.rerun()


def _render_usage(usage: dict) -> None:
    cols = st.columns(3)
    cols[0].caption(f"⏱ {usage.get('latency_ms', 0)} ms")
    cols[1].caption(f"🔢 {usage.get('prompt_tokens', 0)}+{usage.get('completion_tokens', 0)} tok")
    cols[2].caption(f"🧠 {usage.get('answer_model', '?')}")


def _render_msg(msg: dict, idx: int = 0) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("tools"):
            with st.expander(f"Graph calls ({len(msg['tools'])})"):
                for t in msg["tools"]:
                    st.code(t, language="text")
        ids = msg.get("entity_ids") or []
        if ids and st.button(
            f"🔍 View {len(ids)} entit{'y' if len(ids) == 1 else 'ies'} in Graph",
            key=f"viewgraph_{idx}", type="secondary",
        ):
            st.session_state["focus_ids"] = ids
            st.session_state["nav_target"] = "🕸️  Graph"
            st.rerun()
        if msg.get("usage"):
            _render_usage(msg["usage"])


def render() -> None:
    st.title("Ask the Graph")
    workspace_summary.render("Ask")

    if "chat" not in st.session_state:
        st.session_state.chat = []

    if not st.session_state.chat:
        _sample_chips()

    for idx, msg in enumerate(st.session_state.chat):
        _render_msg(msg, idx)

    if st.session_state.chat:
        with st.expander("⬇️  Download this conversation", expanded=False):
            ask_export.download_buttons(st.session_state.chat)
    with st.expander("🗂  Past conversations (persisted)", expanded=False):
        ask_history_panel.render()

    queued = st.session_state.pop("queued_question", None)
    question = queued or st.chat_input("Ask anything about your graph…")
    if not question:
        return

    user_msg = {"role": "user", "text": question}
    st.session_state.chat.append(user_msg)
    _render_msg(user_msg)

    history = [{"role": m["role"], "text": m["text"]} for m in st.session_state.chat[:-1][-5:]]
    with st.chat_message("assistant"):
        with st.spinner("Thinking — reading the graph…"):
            try:
                resp = api.ask(question, history)
            except Exception as exc:
                resp = {"answer": f"Error reaching Ask API: {exc}", "tools_called": [], "usage": {}}
        st.markdown(resp.get("answer", "(no answer)"))
        tools = resp.get("tools_called", [])
        if tools:
            with st.expander(f"Graph calls ({len(tools)})"):
                for t in tools:
                    st.code(t, language="text")
        if resp.get("usage"):
            _render_usage(resp["usage"])

    st.session_state.chat.append({
        "role": "assistant",
        "text": resp.get("answer", "(no answer)"),
        "tools": tools,
        "entity_ids": _entity_ids_from(resp),
        "usage": resp.get("usage", {}),
    })
    _toast.notify(
        f"Ask answered ({resp.get('usage', {}).get('latency_ms', 0)} ms)",
        kind="info", stage="Ask", action="ask",
        target=question[:80], workspace_id=api.current_workspace(),
        audit_event=True,
    )

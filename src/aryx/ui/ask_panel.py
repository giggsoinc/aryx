"""Ask panel — LLM-backed chat over the graph via the REST /ask endpoint."""
from __future__ import annotations

import streamlit as st

from aryx.ui import api


def _render_usage(usage: dict) -> None:
    cols = st.columns(3)
    cols[0].caption(f"⏱ {usage.get('latency_ms', 0)} ms")
    cols[1].caption(f"🔢 {usage.get('prompt_tokens', 0)}+{usage.get('completion_tokens', 0)} tok")
    cols[2].caption(f"🧠 {usage.get('answer_model', '?')}")


def _render_msg(msg: dict) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("tools"):
            with st.expander(f"Graph calls ({len(msg['tools'])})"):
                for t in msg["tools"]:
                    st.code(t, language="text")
        if msg.get("usage"):
            _render_usage(msg["usage"])


def render() -> None:
    st.title("Ask the Graph")
    st.caption("Ask in plain English — Aryx reads the graph and answers. "
               "e.g. *who is connected to Acme?* · *which tickets are escalated?*")

    if "chat" not in st.session_state:
        st.session_state.chat = []

    for msg in st.session_state.chat:
        _render_msg(msg)

    question = st.chat_input("Ask anything about your graph…")
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
        "usage": resp.get("usage", {}),
    })

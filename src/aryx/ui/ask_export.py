"""Download the current Ask conversation as CSV / JSON / XML.

Reads st.session_state.chat directly — no DB persistence yet (post-demo
work tracked as B3). Pure formatters; safe to call on every render.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any
from xml.etree import ElementTree as ET

import streamlit as st


def _rows(chat: list[dict]) -> list[dict[str, Any]]:
    """Pair user→assistant turns into flat rows; carry usage + tool count."""
    out: list[dict[str, Any]] = []
    pending: dict | None = None
    for msg in chat:
        if msg.get("role") == "user":
            pending = msg
            continue
        if msg.get("role") == "assistant":
            u = msg.get("usage", {}) or {}
            out.append({
                "question": (pending or {}).get("text", ""),
                "answer": msg.get("text", ""),
                "tool_calls": len(msg.get("tools", []) or []),
                "prompt_tokens": u.get("prompt_tokens", 0),
                "completion_tokens": u.get("completion_tokens", 0),
                "latency_ms": u.get("latency_ms", 0),
                "model": u.get("answer_model", ""),
            })
            pending = None
    return out


def _as_csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    if not rows:
        return b""
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _as_json(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, indent=2).encode("utf-8")


def _as_xml(rows: list[dict[str, Any]]) -> bytes:
    root = ET.Element("ask_history")
    for r in rows:
        entry = ET.SubElement(root, "entry")
        for k, v in r.items():
            child = ET.SubElement(entry, k)
            child.text = str(v)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def download_buttons(chat: list[dict], key_suffix: str = "") -> None:
    """Render 3 download buttons. key_suffix disambiguates multiple call sites."""
    rows = _rows(chat)
    if not rows:
        return
    sfx = f"_{key_suffix}" if key_suffix else ""
    cols = st.columns(3)
    cols[0].download_button(
        "⬇️ CSV", data=_as_csv(rows),
        file_name="aryx_conversation.csv", mime="text/csv",
        use_container_width=True, key=f"dl_csv{sfx}",
    )
    cols[1].download_button(
        "⬇️ JSON", data=_as_json(rows),
        file_name="aryx_conversation.json", mime="application/json",
        use_container_width=True, key=f"dl_json{sfx}",
    )
    cols[2].download_button(
        "⬇️ XML", data=_as_xml(rows),
        file_name="aryx_conversation.xml", mime="application/xml",
        use_container_width=True, key=f"dl_xml{sfx}",
    )

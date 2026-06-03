"""Streamlit toaster helper — consistent voice across every UI action.

Replaces ad-hoc st.success / st.info / st.error calls with one notify()
wrapper that fires st.toast() AND writes an audit event in one go. Callers
don't have to remember the lifecycle stage label every time.

Toaster kinds:
  ok       — green check, "done"
  info     — neutral blue, "fyi"
  warn     — amber, "soft block"
  error    — red, "failed"
  stage    — purple, "lifecycle stage transition"
"""
from __future__ import annotations

import streamlit as st

from aryx import audit

_ICONS = {"ok": "✅", "info": "ℹ️", "warn": "⚠️",
          "error": "❌", "stage": "🔄"}


def notify(message: str, kind: str = "info", *,
           stage: str = "Pipeline", action: str = "",
           target: str = "", workspace_id: int | None = None,
           actor: str = "user", audit_event: bool = True) -> None:
    """Fire a st.toast() and optionally write an audit event in one call.

    Args:
        message: Plain-English message the user sees.
        kind: One of ok / info / warn / error / stage. Drives the icon.
        stage: Lifecycle stage label for the audit row.
        action: Specific action name (snake_case) for the audit row.
        target: Object affected (entity name, rule name, file, etc.).
        workspace_id: Scope for the audit row.
        actor: Who triggered the action.
        audit_event: Set False for ephemeral toasts (no log row).
    """
    icon = _ICONS.get(kind, "ℹ️")
    try:
        st.toast(f"{icon} {message}")
    except Exception:  # noqa: BLE001 — older Streamlit or non-UI ctx
        pass
    if audit_event and action:
        audit.log(
            stage=stage, action=action, actor=actor,
            workspace_id=workspace_id, target=target,
            outcome="error" if kind == "error" else "ok",
            message=message,
        )


def stage(message: str, *, stage_name: str, workspace_id: int | None = None,
          actor: str = "user", **extra: object) -> None:
    """Lifecycle-stage toast + audit ('Brief done', 'HITL approved', …)."""
    notify(message, kind="stage", stage=stage_name,
           action=f"stage_{stage_name.lower()}",
           workspace_id=workspace_id, actor=actor)

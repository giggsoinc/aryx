"""Knowledge-modelling brief helpers — serialise to a context string.

The 5-question brief (domain / aim / objectives / scope / roles) is
captured BEFORE ingest. When non-empty, its serialised form is the
canonical workspace context fed into every extraction / discovery /
inference prompt. The free-text `context` column remains as an optional
supplement / override.
"""
from __future__ import annotations

from typing import Any


def serialize(brief: dict[str, Any] | None) -> str:
    """Render a brief dict as a prompt-friendly multi-line string.

    Empty / missing fields are dropped so the prompt isn't littered with
    'Aim:' lines that say nothing.
    """
    brief = brief or {}
    lines: list[str] = []
    if domain := str(brief.get("domain") or "").strip():
        lines.append(f"Domain of interest: {domain}")
    if aim := str(brief.get("aim") or "").strip():
        lines.append(f"Aim: {aim}")
    objectives = [str(o).strip() for o in (brief.get("objectives") or [])
                  if str(o).strip()]
    if objectives:
        lines.append("Objectives:")
        lines.extend(f"  - {o}" for o in objectives)
    if scope := str(brief.get("scope") or "").strip():
        lines.append(f"Scope: {scope}")
    roles = [str(r).strip() for r in (brief.get("roles") or [])
             if str(r).strip()]
    if roles:
        lines.append(f"Participants / roles: {', '.join(roles)}")
    return "\n".join(lines)


def merge_with_context(brief: dict[str, Any] | None, context: str) -> str:
    """Combine the structured brief + free-text context override.

    Brief comes first so the LLM sees the structured anchors before the
    looser supplement. Empty pieces drop out cleanly.
    """
    parts = [serialize(brief), str(context or "").strip()]
    return "\n\n".join(p for p in parts if p)


def is_populated(brief: dict[str, Any] | None) -> bool:
    """Return True if ANY brief field is non-empty (used by Ingest gate)."""
    brief = brief or {}
    if str(brief.get("domain") or "").strip():
        return True
    if str(brief.get("aim") or "").strip():
        return True
    if [o for o in (brief.get("objectives") or []) if str(o).strip()]:
        return True
    if str(brief.get("scope") or "").strip():
        return True
    if [r for r in (brief.get("roles") or []) if str(r).strip()]:
        return True
    return False

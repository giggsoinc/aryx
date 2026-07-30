"""Step 6 (optional) — ask an LLM to suggest a dashboard title and better
section titles for the ALREADY-BUILT deterministic composition.

Strictly bounded: the model is asked for titles only, never for components,
IDs, or values. Its response is validated against the exact set of
section_ids compose.py already produced — any section_id it didn't
recognize, invented, or omitted causes the WHOLE suggestion to be discarded
(never a partial apply), and any exception/malformed response falls back to
the deterministic titles untouched. This is the "NO -> LLM unavailable ->
deterministic layout fallback" path in the component's own control-flow
diagram — the fallback is not a degraded mode, it's a fully valid dashboard.
"""
from __future__ import annotations

import logging

from aryx.dashboard_composition.models import DashboardSection

logger = logging.getLogger(__name__)

_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "dashboard_title": {"type": "string"},
        "section_titles": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["dashboard_title", "section_titles"],
}


def _prompt(sections: list[DashboardSection], audience: str, objective: str) -> tuple[str, str]:
    system = (
        "You title dashboard sections for a business audience. You may ONLY "
        "return a short overall title and one short title per section_id "
        "given to you — you may NOT invent, rename, or omit a section_id, "
        "and you have no visibility into or control over what each section "
        "contains."
    )
    section_lines = "\n".join(f"- {s.section_id}: currently {s.title!r}" for s in sections)
    user = (
        f"Audience: {audience or 'general business audience'}\n"
        f"Objective: {objective or '(none stated)'}\n"
        f"Sections (return a title for EVERY one of these section_ids, no others):\n"
        f"{section_lines}\n"
    )
    return system, user


def suggest_titles(
    sections: list[DashboardSection], audience: str, objective: str, *,
    broker, complete_json_fn, tier: str = "cheap",
) -> tuple[str, dict[str, str]] | None:
    """Return (dashboard_title, {section_id: title}) or None if the LLM is
    unavailable, errored, or returned anything that doesn't exactly match
    the given section_ids — callers must treat None as "use the
    deterministic titles", never as an error to surface."""
    expected_ids = {s.section_id for s in sections}
    system, user = _prompt(sections, audience, objective)
    try:
        data = complete_json_fn(broker, tier, system, user, _SCHEMA)
    except Exception:  # noqa: BLE001 — narration is optional, never blocks composition
        logger.info("C14 narration unavailable, using deterministic titles", exc_info=True)
        return None

    title = data.get("dashboard_title")
    section_titles = data.get("section_titles")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(section_titles, dict):
        return None
    returned_ids = set(section_titles.keys())
    if returned_ids != expected_ids:
        logger.info("C14 narration section_id mismatch expected=%s got=%s — discarding",
                   sorted(expected_ids), sorted(returned_ids))
        return None
    if any(not isinstance(t, str) or not t.strip() for t in section_titles.values()):
        return None
    return title.strip(), {k: v.strip() for k, v in section_titles.items()}


def apply_titles(sections: list[DashboardSection],
                 section_titles: dict[str, str]) -> list[DashboardSection]:
    """Return NEW section objects with only `.title` replaced — components,
    IDs, order, and everything else are untouched copies."""
    return [s.model_copy(update={"title": section_titles[s.section_id]}) for s in sections]

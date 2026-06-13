"""AI-assist for ontology modelling (Slice W2 / option f).

Given a brief and an entity type name (with optional existing attrs),
ask the frontier model to propose a list of attribute names. Reuses the
same broker + complete_json plumbing as brief_draft, so live LLM config
in Settings drives both.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.broker import Broker
from aryx.llm import complete_json

logger = logging.getLogger(__name__)

_ATTRS_SCHEMA: dict[str, Any] = {
    "attributes": ["string"],
    "rationale": "string",
}

_ATTRS_SYSTEM = (
    "You are an ontology modeller. Given a brief and an entity type name "
    "(plus any existing attributes), propose 4-10 ADDITIONAL attribute "
    "names — short, snake_case, business-meaningful. Skip attributes the "
    "user already has. Return JSON with `attributes` (the new names only) "
    "and `rationale` (one sentence on why these). Be specific to the "
    "domain; never echo the instructions."
)


def suggest_attrs(broker: Broker, brief_text: str, type_name: str,
                  existing: list[str] | None = None) -> dict[str, Any]:
    """Return {attributes: [...], rationale: '...'} for one entity type."""
    user = (f"Brief:\n{brief_text or '(none)'}\n\n"
            f"Entity type: {type_name}\n"
            f"Existing attributes: {', '.join(existing or []) or '(none)'}")
    data = complete_json(broker, "frontier", _ATTRS_SYSTEM, user, _ATTRS_SCHEMA)
    raw = data.get("attributes") or []
    seen = {a.lower() for a in (existing or [])}
    cleaned: list[str] = []
    for a in raw:
        s = str(a).strip().lower().replace(" ", "_")
        if s and s not in seen:
            cleaned.append(s)
            seen.add(s)
    return {"attributes": cleaned[:12],
            "rationale": str(data.get("rationale") or "").strip()}

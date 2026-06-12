"""Draft a 5-question knowledge brief from a seed sentence and/or document.

Turns one sentence (and optional pasted document text — a strategy deck,
SOW, runbook) into a structured brief: domain / aim / objectives / scope /
roles. The user then edits the draft rather than authoring from a blank
form. Powered by the same Broker that runs extraction, at the frontier tier.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.broker import Broker
from aryx.llm import complete_json

logger = logging.getLogger(__name__)

_SCHEMA: dict[str, Any] = {
    "domain": "string",
    "aim": "string",
    "objectives": ["string"],
    "scope": "string",
    "roles": ["string"],
}

_SYSTEM = (
    "You are a knowledge-modelling analyst. From the user's seed sentence "
    "and any supplied document text, produce a crisp ontology brief. Return "
    "JSON with exactly these keys: domain (one short phrase), aim (1-2 "
    "sentences on the outcome the knowledge graph should enable), objectives "
    "(3-6 concrete, measurable goals), scope (an 'IN:' block of entity kinds "
    "to model and an 'OUT:' block to exclude), roles (2-5 participant roles, "
    "each with the question that role would ask the graph). Infer sensible "
    "values from the domain; never echo the instructions. Be specific to the "
    "user's domain, not generic."
)


def draft_from_text(broker: Broker, seed: str = "",
                    doc_text: str = "", max_doc_chars: int = 12000) -> dict:
    """Return a 5-field brief dict drafted from seed + optional doc text."""
    seed = (seed or "").strip()
    doc_text = (doc_text or "").strip()[:max_doc_chars]
    if not seed and not doc_text:
        return {"domain": "", "aim": "", "objectives": [],
                "scope": "", "roles": []}
    parts = []
    if seed:
        parts.append(f"Seed sentence:\n{seed}")
    if doc_text:
        parts.append(f"Document excerpt:\n{doc_text}")
    user = "\n\n".join(parts)
    data = complete_json(broker, "frontier", _SYSTEM, user, _SCHEMA)
    return _coerce(data)


def _coerce(data: dict) -> dict:
    """Normalise model output to the canonical brief shape."""
    def _slist(v: Any) -> list[str]:
        if isinstance(v, str):
            return [ln.strip() for ln in v.splitlines() if ln.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []
    return {
        "domain": str(data.get("domain") or "").strip(),
        "aim": str(data.get("aim") or "").strip(),
        "objectives": _slist(data.get("objectives")),
        "scope": str(data.get("scope") or "").strip(),
        "roles": _slist(data.get("roles")),
    }

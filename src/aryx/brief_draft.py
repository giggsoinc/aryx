"""Draft a 5-question knowledge brief from a seed sentence and/or document.

Turns one sentence (and optional pasted document text — a strategy deck,
SOW, runbook) into a structured brief: domain / aim / objectives / scope /
roles. The user then edits the draft rather than authoring from a blank
form. Powered by the same Broker that runs extraction, at the frontier tier.
"""
from __future__ import annotations

import logging
import re
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
    "(3-6 concrete, measurable goals), scope (an 'IN:' block listing the "
    "concrete entity TYPES to model as short singular nouns — e.g. Contract, "
    "ContractLine, Vendor — and an 'OUT:' block to exclude), roles (2-5 "
    "participant roles, each with the question that role would ask the graph). "
    "Infer sensible values from the domain, but PRESERVE any entity, metric, or "
    "relationship the user explicitly names in the seed sentence: use their "
    "exact term verbatim as an entity kind in the IN: scope, and never replace "
    "a named entity with an activity, process, or theme (e.g. if the user says "
    "'Contract' and 'contract line', scope IN: must contain Contract and "
    "ContractLine, not 'contract lifecycle management'). If the user names "
    "specific identifier or column names (e.g. contract_number, line_number), "
    "reproduce those EXACT tokens verbatim — keep the underscores — inside the "
    "objectives, so downstream keying can honour them. Never echo the "
    "instructions. Be specific to the user's domain, not generic."
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
    try:
        data = complete_json(broker, "frontier", _SYSTEM, user, _SCHEMA)
    except Exception as exc:  # noqa: BLE001 - onboarding should stay usable offline
        logger.warning("brief draft LLM failed; using local fallback: %s", exc)
        return _fallback_brief(seed, doc_text)
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


def _fallback_brief(seed: str, doc_text: str = "") -> dict:
    """Draft a conservative brief without an LLM when provider setup fails."""
    text = " ".join(part.strip() for part in (seed, doc_text) if part.strip())
    if not text:
        return {"domain": "", "aim": "", "objectives": [],
                "scope": "", "roles": []}

    identifiers = _identifiers(text)
    entity_types = _entity_types(text, identifiers)
    if not entity_types:
        entity_types = ["Record"]

    domain_terms = " and ".join(_split_type_name(t).lower() for t in entity_types[:2])
    primary = entity_types[0]
    secondary = entity_types[1] if len(entity_types) > 1 else "related records"
    id_phrase = ", ".join(identifiers) if identifiers else "the named identifiers"

    objectives = [
        f"Identify each {primary} using {id_phrase}.",
        f"Capture the relationship between {primary} and {secondary}.",
        "Show how records connect across the model for review and analysis.",
    ]
    if seed:
        objectives.append(f"Honor this onboarding goal: {seed}")

    scope_in = "\n".join(f"- {name}" for name in entity_types)
    if identifiers:
        scope_in += "\n- Identifier"
    return {
        "domain": f"{domain_terms} knowledge model".strip(),
        "aim": (
            f"Build a knowledge graph that maps {primary} records to "
            f"{secondary} while preserving the user-named keys and "
            "relationships."
        ),
        "objectives": objectives[:6],
        "scope": f"IN:\n{scope_in}\n\nOUT:\n- Unnamed processes\n- Unrelated records",
        "roles": [
            "Data steward: Which identifiers make each record unique?",
            "Analyst: How does each record connect to its related records?",
            "Reviewer: Are the modeled relationships complete and correct?",
        ],
    }


def _identifiers(text: str) -> list[str]:
    """Return exact snake_case-style identifiers in first-seen order."""
    seen: set[str] = set()
    values: list[str] = []
    for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", text):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _entity_types(text: str, identifiers: list[str]) -> list[str]:
    """Infer a small, stable set of entity type names from explicit terms."""
    candidates: list[str] = []
    candidates.extend(re.findall(r"\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)?\b", text))
    candidates.extend(re.findall(
        r"\b(?:each|every|many|all|its|the|a|an)\s+([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*)?)s?\b",
        text,
        flags=re.IGNORECASE,
    ))
    for identifier in identifiers:
        candidates.extend(identifier.split("_")[:-1])

    seen: set[str] = set()
    names: list[str] = []
    stop = {
        "a", "all", "an", "and", "by", "connect", "connects", "each",
        "every", "has", "how", "identified", "is", "its", "many", "map",
        "of", "show", "the", "to", "together", "using", "with",
    }
    for candidate in candidates:
        words = [
            word for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", candidate)
            if word.lower() not in stop
        ]
        if not words:
            continue
        name = "".join(_singular(word).capitalize() for word in words[:2])
        if len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
        if len(names) >= 6:
            break
    return names


def _singular(word: str) -> str:
    lower = word.lower()
    if lower.endswith("ies") and len(lower) > 3:
        return lower[:-3] + "y"
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) > 3:
        return lower[:-1]
    return lower


def _split_type_name(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r" \1", name)

"""Schema-aware JSON normalizer — absorbs provider-specific shape quirks.

LLM providers vary in how strictly they honor a requested JSON schema:
  - Anthropic structured outputs enforce schema strictly (no normalization needed).
  - Ollama's JSON mode usually respects the schema's envelope shape.
  - OpenAI's response_format=json_object honors schema loosely.
  - Gemini's OpenAI-compatible JSON mode often unwraps single-property
    envelopes (returns the inner array directly) and renames fields to
    common synonyms (entity_type, verbatim_span, …).

This module coerces any of those into the canonical shape declared by the
schema. Business code (entity extraction, schema discovery, relationship
inference) sees ONE shape regardless of provider. Adding a new provider =
zero code change in callers — only register synonyms here if needed.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common field-name synonyms across providers. Canonical → list of synonyms.
# Edit here when a new provider ships a quirky alias; never in business code.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "type": ("entity_type", "category", "kind", "label_type"),
    "name": ("entity_name", "label", "title", "value"),
    "span": ("verbatim_span", "evidence", "context", "quote", "excerpt"),
    "attributes": ("attrs", "properties_", "fields", "metadata"),
    "confidence": ("score", "probability", "conf"),
}

# Reverse map: synonym → canonical, built once for O(1) lookup.
_CANON: dict[str, str] = {
    syn: canon for canon, syns in _SYNONYMS.items() for syn in syns
}


def _coerce_envelope(raw: Any, schema: dict[str, Any]) -> Any:
    """If schema expects {X: array} but raw is a bare list, wrap it as {X: raw}.

    Handles the most common Gemini quirk: top-level schema is one array
    property, model returns the inner list directly.
    """
    if not isinstance(raw, list):
        return raw
    if (schema or {}).get("type") != "object":
        return raw
    props = (schema or {}).get("properties") or {}
    array_props = [k for k, v in props.items()
                   if isinstance(v, dict) and v.get("type") == "array"]
    if len(array_props) == 1:
        logger.debug("envelope coerced list -> {%s: ...}", array_props[0])
        return {array_props[0]: raw}
    return raw


def _rename_keys(obj: Any) -> Any:
    """Recursively rename known synonyms to their canonical name.

    Existing canonical keys are NOT overwritten if a synonym also appears —
    the canonical value wins.
    """
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            canon = _CANON.get(k, k)
            if canon in out and canon != k:
                continue
            out[canon] = _rename_keys(v)
        return out
    if isinstance(obj, list):
        return [_rename_keys(x) for x in obj]
    return obj


def normalize(raw: Any, schema: dict[str, Any] | None = None) -> Any:
    """Coerce a raw LLM JSON response to the canonical shape declared by schema.

    Args:
        raw: Whatever the provider returned (dict, list, scalar).
        schema: The JSON schema the caller asked for. May be empty.

    Returns:
        Same shape as the schema's top level. If schema is missing or raw is a
        scalar, returns raw unchanged.
    """
    normalized = _coerce_envelope(raw, schema or {})
    normalized = _rename_keys(normalized)
    return normalized

"""Relationship inference (stage 8): name the edge between two entities.

Callable, like the mapping agent. Deterministic FK/co-occurrence-driven pair
selection is a follow-on (it needs FK hints captured at ingestion); this
provides the frontier-tier judgement for a given candidate pair.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from aryx.broker import Broker
from aryx.llm import complete_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You decide whether two entities are related and, if so, name the directed "
    "relationship from A to B in lowercase snake_case (e.g. places, works_for, "
    "located_in). If unrelated, set related=false."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "related": {"type": "boolean"},
        "name": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["related", "name", "confidence"],
    "additionalProperties": False,
}


def infer_relationship(
    left: dict[str, Any], right: dict[str, Any], broker: Broker
) -> tuple[str | None, float]:
    """Ask the frontier model what relationship links A to B, if any.

    Args:
        left: Attributes of entity A (the source).
        right: Attributes of entity B (the target).
        broker: Model broker; inference runs on the frontier tier.

    Returns:
        (relationship_name, confidence), or (None, 0.0) if unrelated.
    """
    user = json.dumps({"a": left, "b": right})
    result = complete_json(broker, "frontier", _SYSTEM, user, _SCHEMA)
    if not result.get("related"):
        return None, 0.0
    name = str(result["name"])
    confidence = float(result.get("confidence", 0.0))
    logger.info("relationship inferred name=%s conf=%.2f", name, confidence)
    return name, confidence

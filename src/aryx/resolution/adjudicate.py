"""LLM adjudication (frontier tier): decide the ambiguous middle band."""
from __future__ import annotations

import json
import logging

from aryx.broker import Broker
from aryx.llm import complete_json
from aryx.models import ResolutionRecord

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You rescore whether two records describe the SAME real-world entity. "
    "Account for abbreviations, casing, legal suffixes, and typos. "
    "Answer strictly with the schema: a confidence score in [0, 1] that the "
    "two records are the same entity, and a short reason."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
    "additionalProperties": False,
}


def adjudicate(left: ResolutionRecord, right: ResolutionRecord, broker: Broker) -> float:
    """Ask the frontier model to rescore two records' match confidence.

    Args:
        left: First candidate record.
        right: Second candidate record.
        broker: Model broker; adjudication runs on the frontier tier.

    Returns:
        Rescored confidence in [0, 1].
    """
    user = json.dumps({"a": left.payload, "b": right.payload})
    result = complete_json(broker, "frontier", _SYSTEM, user, _SCHEMA)
    score = float(result.get("confidence", 0.0))
    logger.info("adjudicate rescored=%.3f a=%s b=%s", score, left.record_id, right.record_id)
    return score

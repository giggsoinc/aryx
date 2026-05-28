"""Field tagging (stage 4): cheap-tier semantic typing of profiled fields."""
from __future__ import annotations

import json
import logging

from aryx.broker import Broker
from aryx.llm import complete_json
from aryx.models import FieldProfile, FieldTag

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You label data fields with a concise semantic type and flag PII. "
    "Use lowercase snake_case types such as email, person_name, country_code, "
    "phone, address, date, identifier, foreign_key, amount, free_text."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "semantic_type": {"type": "string"},
                    "is_pii": {"type": "boolean"},
                },
                "required": ["field", "semantic_type", "is_pii"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tags"],
    "additionalProperties": False,
}


def tag_fields(profiles: list[FieldProfile], broker: Broker) -> list[FieldTag]:
    """Assign a semantic type + PII flag to each profiled field (cheap tier).

    Args:
        profiles: Field profiles from the profile stage.
        broker: Model broker; tagging runs on the cheap tier.

    Returns:
        One FieldTag per field the model labelled.
    """
    if not profiles:
        return []
    user = json.dumps(
        [{"field": p.field, "samples": p.samples, "distinct": p.distinct} for p in profiles]
    )
    result = complete_json(broker, "cheap", _SYSTEM, user, _SCHEMA)
    tags = [FieldTag(**t) for t in result.get("tags", [])]
    logger.info("tagged fields count=%d", len(tags))
    return tags

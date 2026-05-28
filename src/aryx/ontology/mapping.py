"""Ontology mapping agent (stage 6, frontier tier).

Callable: categorize() classifies a source dataset against the current ontology
and proposes a type + field-to-attribute mappings. New types land as 'proposed'
and wait for the human review gate before becoming real.
"""
from __future__ import annotations

import json
import logging

from aryx.broker import Broker
from aryx.llm import complete_json
from aryx.models import FieldProfile, FieldTag, OntologyType, SchemaMapping

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an ontology mapper. Given a source dataset's profiled and tagged "
    "fields plus the current ontology, choose the best canonical type: reuse an "
    "existing type if it fits, otherwise propose a new one. Map each field to an "
    "attribute, preferring existing type/attribute names. Be conservative."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "is_new_type": {"type": "boolean"},
        "attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "attribute": {"type": "string"},
                },
                "required": ["field", "attribute"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["type", "is_new_type", "attributes", "confidence"],
    "additionalProperties": False,
}


def categorize(
    system: str,
    dataset: str,
    profiles: list[FieldProfile],
    tags: list[FieldTag],
    ontology: list[OntologyType],
    broker: Broker,
) -> tuple[OntologyType | None, list[SchemaMapping]]:
    """Classify a source dataset against the ontology (frontier tier).

    Args:
        system: Source system label.
        dataset: Source dataset/table label.
        profiles: Field profiles for the dataset.
        tags: Field semantic tags for the dataset.
        ontology: Current known ontology types (grounding).
        broker: Model broker; mapping runs on the frontier tier.

    Returns:
        A proposed OntologyType (only when new, status 'proposed') or None, and
        the field-level SchemaMappings.
    """
    tag_by_field = {t.field: t.semantic_type for t in tags}
    user = json.dumps({
        "dataset": f"{system}.{dataset}",
        "fields": [
            {"field": p.field, "type": tag_by_field.get(p.field, "unknown"),
             "samples": p.samples}
            for p in profiles
        ],
        "ontology": [{"name": o.name, "attributes": o.attributes} for o in ontology],
    })
    result = complete_json(broker, "frontier", _SYSTEM, user, _SCHEMA)

    type_name = result["type"]
    confidence = float(result["confidence"])
    mappings = [
        SchemaMapping(
            source_system=system, source_dataset=dataset, source_field=a["field"],
            ontology_type=type_name, ontology_attribute=a["attribute"],
            confidence=confidence,
        )
        for a in result.get("attributes", [])
    ]
    proposed = None
    if result.get("is_new_type"):
        attrs = [a["attribute"] for a in result.get("attributes", [])]
        proposed = OntologyType(name=type_name, attributes=attrs, status="proposed")
    logger.info("categorized %s.%s -> %s new=%s conf=%.2f", system, dataset,
                type_name, result.get("is_new_type"), confidence)
    return proposed, mappings

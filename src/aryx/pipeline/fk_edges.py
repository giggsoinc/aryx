"""Deterministic FK edges: link entities by a foreign-key-style attribute.

When the ingested rows reference another entity by name (e.g. a support ticket
carries the customer_name), this stage looks up the referenced entity by
attribute equality and writes a typed Relationship. No LLM, no guesswork —
exact matches only.
"""
from __future__ import annotations

import logging

from aryx.models import Relationship
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def _attr(payload: object, key: str) -> str | None:
    """Best-effort string extract from a resolved-entity attributes payload."""
    if isinstance(payload, dict):
        val = payload.get(key)
        return str(val).strip() if val is not None else None
    return None


def link_by_attribute(
    estore: EntityStore, source_type: str, source_attr: str,
    target_type: str, target_attr: str, name: str,
) -> int:
    """Create edges where source_type.source_attr == target_type.target_attr.

    Args:
        estore: Open EntityStore.
        source_type: Ontology type of the row-side entities (e.g. SupportTicket).
        source_attr: Attribute on the source carrying the lookup value.
        target_type: Ontology type of the referent (e.g. Customer).
        target_attr: Attribute on the target whose value must match.
        name: Edge label written into the graph (e.g. HAS_TICKET).

    Returns:
        Number of relationships saved (existing edges are not deduped here).
    """
    entities = estore.list_entities()
    targets: dict[str, list[int]] = {}
    for tid, ttype, payload in entities:
        if ttype != target_type:
            continue
        key = _attr(payload, target_attr)
        if key:
            targets.setdefault(key.lower(), []).append(tid)

    # Self-typed AND self-attributed (source_type == target_type, source_attr
    # == target_attr) means the match condition is symmetric: A's value ==
    # B's value implies B's value == A's value. The loop below visits every
    # entity as a candidate sid, so a symmetric match gets discovered from
    # BOTH sides — (A,B) when sid=A, (B,A) when sid=B — producing two edges
    # for one logical relationship. Only dedupe in this exact case: a
    # self-typed link with DIFFERENT attrs (e.g. manager_id vs employee_id)
    # is directional by construction and pairs are not naturally doubled, so
    # deduping there would silently drop a legitimate directed edge.
    symmetric_self_link = source_type == target_type and source_attr == target_attr

    rels: list[Relationship] = []
    for sid, stype, payload in entities:
        if stype != source_type:
            continue
        ref = _attr(payload, source_attr)
        if not ref:
            continue
        for tid in targets.get(ref.lower(), []):
            if tid != sid:
                if symmetric_self_link and sid > tid:
                    continue  # the sid < tid pass already emitted this pair
                # sid is the source_type entity, tid the target_type entity —
                # the edge must point sid -> tid to match this function's own
                # parameter naming and the caller's own log line ("linked %s
                # -[%s]-> %s", src, name, tgt in dimension_materialize.py).
                rels.append(Relationship(
                    source_entity_id=sid, target_entity_id=tid,
                    name=name, confidence=1.0,
                ))
    if rels:
        estore.save_relationships(rels)
    logger.info("fk-edges %s.%s -> %s.%s name=%s saved=%d",
                source_type, source_attr, target_type, target_attr, name, len(rels))
    return len(rels)

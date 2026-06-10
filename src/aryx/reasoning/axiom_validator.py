"""Axiom validation pass — runs after projection, records violations.

Night 2 scope is intentionally narrow: ``cardinality_max`` is the one axiom
kind that maps cleanly onto already-projected attribute payloads without
needing class-membership reasoning. Disjoint / equivalent / domain / range
are exported to OWL so Protégé and Jena enforce them — runtime enforcement
of those lands in Night 3 once the ancestor-aware reasoner is in place.

Violations are persisted to ``aryx_axiom_violation`` for audit and surfaced
in the API response; they do not block the projection (fail-loud, like the
PII screen for non-critical findings).
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.store.axiom_store import AxiomStore
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def _violates_cardinality_max(attributes: dict[str, Any],
                              payload: dict[str, Any]) -> tuple[bool, int]:
    """Return ``(violated, observed_count)`` for one cardinality_max axiom."""
    prop = str(payload.get("property") or "").strip()
    try:
        max_count = int(payload.get("max"))
    except (TypeError, ValueError):
        return False, 0
    if not prop:
        return False, 0
    value = attributes.get(prop) if attributes else None
    if value is None or value == "":
        observed = 0
    elif isinstance(value, list):
        observed = len(value)
    else:
        observed = 1
    return observed > max_count, observed


def validate_workspace(workspace_id: int, dsn: str) -> dict[str, Any]:
    """Walk entities + axioms; record violations; return a summary."""
    axiom_store = AxiomStore(dsn)
    try:
        axioms = axiom_store.list_(workspace_id)
    finally:
        axiom_store.close()
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ax in axioms:
        if ax["kind"] == "cardinality_max":
            by_type.setdefault(ax["subject_type"], []).append(ax)
    if not by_type:
        return {"axioms_checked": 0, "entities_scanned": 0, "violations": 0}

    estore = EntityStore(dsn, workspace_id)
    try:
        entities = estore.list_entities()
    finally:
        estore.close()

    recorder = AxiomStore(dsn)
    violations = 0
    try:
        for entity_id, ontology_type, attributes in entities:
            for ax in by_type.get(ontology_type, []):
                violated, count = _violates_cardinality_max(
                    attributes or {}, ax["payload"])
                if violated:
                    reason = (f"cardinality_max violated: "
                              f"{ax['payload'].get('property')}={count} "
                              f"> {ax['payload'].get('max')}")
                    recorder.record_violation(
                        workspace_id, int(entity_id), int(ax["id"]), reason)
                    violations += 1
    finally:
        recorder.close()
    summary = {"axioms_checked": sum(len(v) for v in by_type.values()),
               "entities_scanned": len(entities),
               "violations": violations}
    logger.info("axiom validation ws=%s %s", workspace_id, summary)
    return summary

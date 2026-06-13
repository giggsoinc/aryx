"""Axiom validation pass — runs after projection, records violations.

Covers three axiom kinds:

  - ``cardinality_max`` (Night 2): scalar / list check on the attribute value
  - ``domain``         (Night 3): an entity carrying property P must be of
                                  ``subject_type`` or one of its subtypes
                                  (ancestor-aware membership via OntologyStore)
  - ``range`` (class)  (Night 3): noted but not enforced at runtime — needs
                                  typed relationship targets which Aryx does
                                  not model yet. Exported to OWL/SHACL so
                                  Protégé and pyshacl enforce it instead.

Violations are persisted to ``aryx_axiom_violation`` for audit and surfaced
in the API response; they do not block the projection (fail-loud, like the
PII screen for non-critical findings).
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.store.axiom_store import AxiomStore
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore

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


def _is_subtype(child: str, ancestor: str,
                ancestors_of: dict[str, list[str]]) -> bool:
    """``child`` is a subtype of (or equal to) ``ancestor``."""
    return child == ancestor or ancestor in ancestors_of.get(child, [])


def _violates_domain(attributes: dict[str, Any], payload: dict[str, Any],
                     entity_type: str, subject_type: str,
                     ancestors_of: dict[str, list[str]]) -> bool:
    """Entity carries property P but its type isn't subject_type or subtype."""
    prop = str(payload.get("property") or "").strip()
    if not prop or not (attributes or {}).get(prop):
        return False
    return not _is_subtype(entity_type, subject_type, ancestors_of)


def validate_workspace(workspace_id: int, dsn: str) -> dict[str, Any]:
    """Walk entities + axioms; record violations; return a summary."""
    axiom_store = AxiomStore(dsn)
    try:
        axioms = axiom_store.list_(workspace_id)
    finally:
        axiom_store.close()
    cardinality_by_type: dict[str, list[dict[str, Any]]] = {}
    domain_axioms: list[dict[str, Any]] = []
    for ax in axioms:
        if ax["kind"] == "cardinality_max":
            cardinality_by_type.setdefault(ax["subject_type"], []).append(ax)
        elif ax["kind"] == "domain":
            domain_axioms.append(ax)
    if not cardinality_by_type and not domain_axioms:
        return {"axioms_checked": 0, "entities_scanned": 0, "violations": 0}

    onto = OntologyStore(dsn, workspace_id)
    try:
        ancestors_of = {t.name: onto.ancestors(t.name)
                        for t in onto.list_types()}
    finally:
        onto.close()
    estore = EntityStore(dsn, workspace_id)
    try:
        entities = estore.list_entities()
    finally:
        estore.close()

    recorder = AxiomStore(dsn)
    violations = 0
    try:
        for entity_id, ontology_type, attributes in entities:
            for ax in cardinality_by_type.get(ontology_type, []):
                violated, count = _violates_cardinality_max(
                    attributes or {}, ax["payload"])
                if violated:
                    reason = (f"cardinality_max violated: "
                              f"{ax['payload'].get('property')}={count} "
                              f"> {ax['payload'].get('max')}")
                    recorder.record_violation(
                        workspace_id, int(entity_id), int(ax["id"]), reason)
                    violations += 1
            for ax in domain_axioms:
                if _violates_domain(attributes or {}, ax["payload"],
                                    ontology_type, ax["subject_type"],
                                    ancestors_of):
                    reason = (f"domain violated: property "
                              f"{ax['payload'].get('property')} "
                              f"requires {ax['subject_type']}, "
                              f"got {ontology_type}")
                    recorder.record_violation(
                        workspace_id, int(entity_id), int(ax["id"]), reason)
                    violations += 1
    finally:
        recorder.close()
    summary = {
        "axioms_checked": (sum(len(v) for v in cardinality_by_type.values())
                           + len(domain_axioms)),
        "entities_scanned": len(entities), "violations": violations,
    }
    logger.info("axiom validation ws=%s %s", workspace_id, summary)
    return summary

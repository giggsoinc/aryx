"""Browse helper for the ontology API — types, attrs, relationship counts.

Split out of ontology_api so each module stays within the 150-line budget.
Returns a single payload used by the Streamlit Ontology Browse tab.
"""
from __future__ import annotations

from typing import Any

from aryx.config import get_settings
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore


def approve(name: str) -> dict[str, Any]:
    """Approve a proposed ontology type via the HITL gate."""
    store = OntologyStore(get_settings().rdb_dsn)
    try:
        store.approve_type(name)
    finally:
        store.close()
    return {"status": "approved", "name": name}


def add_type(name: str, attributes: dict, status: str = "approved",
             source: str = "manual") -> dict[str, Any]:
    """Manually create an ontology type (governance editor entry-point)."""
    from aryx.models import OntologyType
    store = OntologyStore(get_settings().rdb_dsn)
    try:
        store.seed_types([OntologyType(name=name, attributes=attributes or {},
                                       status=status, source=source)])
    finally:
        store.close()
    return {"status": "ok", "name": name}


def import_doc(content: str, fmt_hint: str, filename: str) -> dict[str, Any]:
    """Parse RDF/OWL content into proposed types; returns counts + names."""
    from aryx.ontology.rdf import format_for_extension, parse_ontology
    fmt = fmt_hint or format_for_extension(filename) or "turtle"
    try:
        types = parse_ontology(content, fmt)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if not types:
        return {"imported": 0, "types": [], "format": fmt,
                "message": "no owl:Class / rdfs:Class declarations found"}
    onto = OntologyStore(get_settings().rdb_dsn)
    try:
        onto.seed_types(types)
    finally:
        onto.close()
    return {"imported": len(types), "types": [t.name for t in types],
            "format": fmt,
            "message": "imported as 'proposed' — approve in the review gate"}


def list_browse(workspace_id: int) -> dict[str, Any]:
    """Return ontology types + relationship counts + entity count for one workspace."""
    settings = get_settings()
    onto = OntologyStore(settings.rdb_dsn)
    try:
        type_rows = [t.__dict__ if hasattr(t, "__dict__") else dict(t)
                     for t in onto.list_types()]
    finally:
        onto.close()
    store = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        ents = store.list_entities()
        rels = store.list_relationships()
    finally:
        store.close()
    per_type: dict[str, int] = {}
    for e in ents:
        key = e.get("type") or e.get("ontology_type") or "?"
        per_type[key] = per_type.get(key, 0) + 1
    for t in type_rows:
        t["instance_count"] = per_type.get(t.get("name"), 0)
    rel_types: dict[str, int] = {}
    for r in rels:
        rel_types[r.get("name", "?")] = rel_types.get(r.get("name", "?"), 0) + 1
    return {
        "types": type_rows,
        "relationships": [{"name": k, "count": v} for k, v in rel_types.items()],
        "entity_count": len(ents),
    }

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


def add_type(name: str, attributes: Any, status: str = "approved",
             source: str = "manual") -> dict[str, Any]:
    """Manually create an ontology type (governance editor entry-point).

    ``attributes`` accepts either a ``list[str]`` of attribute names or a
    ``dict`` whose keys are attribute names (values ignored). Older callers
    pass ``{}`` from JSON bodies — coerce to a list so OntologyType validates.
    """
    from aryx.models import OntologyType
    if isinstance(attributes, dict):
        attrs = [str(k) for k in attributes.keys()]
    elif isinstance(attributes, list):
        attrs = [str(x) for x in attributes]
    else:
        attrs = []
    store = OntologyStore(get_settings().rdb_dsn)
    try:
        store.seed_types([OntologyType(name=name, attributes=attrs,
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


def set_parent(name: str, parent: str | None) -> dict[str, Any]:
    """Set or clear the parent_type for a type (rdfs:subClassOf)."""
    store = OntologyStore(get_settings().rdb_dsn)
    try:
        store.set_parent(name, parent)
    finally:
        store.close()
    return {"status": "ok", "name": name, "parent_type": parent}


def list_browse(workspace_id: int) -> dict[str, Any]:
    """Return ontology types + relationship counts + entity count for one workspace."""
    settings = get_settings()
    onto = OntologyStore(settings.rdb_dsn)
    try:
        type_objs = onto.list_types()
        type_rows = [t.__dict__ if hasattr(t, "__dict__") else dict(t)
                     for t in type_objs]
        for row in type_rows:
            if row.get("parent_type"):
                row["ancestors"] = onto.ancestors(row["name"])
            else:
                row["ancestors"] = []
    finally:
        onto.close()
    store = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        ents = store.list_entities()
        rels = store.list_relationships()
    finally:
        store.close()
    def _field(row: Any, key: str, idx: int) -> str:
        """Read attr from a dict-row OR tuple-row (entity_store returns tuples)."""
        if isinstance(row, dict):
            return str(row.get(key) or row.get("ontology_type") or "?")
        try:
            return str(row[idx])
        except (IndexError, TypeError):
            return "?"

    per_type: dict[str, int] = {}
    for e in ents:
        key = _field(e, "type", 1)
        per_type[key] = per_type.get(key, 0) + 1
    for t in type_rows:
        t["instance_count"] = per_type.get(t.get("name"), 0)
    rel_types: dict[str, int] = {}
    for r in rels:
        key = _field(r, "name", 2)
        rel_types[key] = rel_types.get(key, 0) + 1
    return {
        "types": type_rows,
        "relationships": [{"name": k, "count": v} for k, v in rel_types.items()],
        "entity_count": len(ents),
    }

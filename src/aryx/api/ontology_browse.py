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

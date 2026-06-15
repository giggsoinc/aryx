"""Data-explorer aggregation — the transparency surface's read model.

Pure functions over already-fetched entity + provenance lists (the relational
source of truth, via EntityStore). No DB, no graph driver — so the shaping is
unit-testable and the HTTP layer (api/data_api.py) stays a thin wire.

Three reads back the Data tab: a workspace summary (types, counts, sources,
the dedup story) and an entities-by-type view that carries each golden record's
attributes AND the source records it traces back to.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

_NAME_KEYS = ("name", "full_name", "title", "label", "ticket_ref", "ref",
              "sku", "code", "email", "username")


def display_name(attributes: dict[str, Any] | None, entity_id: int) -> str:
    """Pick a human label for an entity, falling back to #id."""
    attrs = attributes or {}
    for key in _NAME_KEYS:
        val = attrs.get(key)
        if val:
            return str(val)
    for val in attrs.values():
        if isinstance(val, str) and 0 < len(val) <= 80:
            return val
    return f"#{entity_id}"


def _prov_by_entity(provenance: list[tuple[int, str, str, str]]) -> dict[int, list[dict]]:
    """Group (entity_id, system, dataset, record_id) rows by entity."""
    out: dict[int, list[dict]] = defaultdict(list)
    for entity_id, system, dataset, record_id in provenance:
        out[int(entity_id)].append(
            {"system": system, "dataset": dataset, "record_id": str(record_id)})
    return out


def summarize(entities: list[tuple[int, str, dict]],
              provenance: list[tuple[int, str, str, str]]) -> dict[str, Any]:
    """Workspace-level counts: per-type, per-source, and the dedup story."""
    type_counts = Counter(t for _, t, _ in entities)
    src_counts: Counter = Counter(
        f"{system}.{dataset}" for _, system, dataset, _ in provenance)
    total = len(entities)
    source_records = len(provenance)
    return {
        "total_entities": total,
        "type_count": len(type_counts),
        "types": [{"name": name, "count": count}
                  for name, count in type_counts.most_common()],
        "sources": [{"source": src, "count": count}
                    for src, count in src_counts.most_common()],
        "source_records": source_records,
        "duplicates_merged": max(0, source_records - total),
    }


def entities_view(entities: list[tuple[int, str, dict]],
                  provenance: list[tuple[int, str, str, str]],
                  ontology_type: str | None = None,
                  limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Entities (optionally filtered by type) with attributes + provenance.

    Returns the page plus the unfiltered count for that type so the UI can
    paginate without a second call.
    """
    by_entity = _prov_by_entity(provenance)
    rows = [e for e in entities
            if not ontology_type or e[1] == ontology_type]
    total = len(rows)
    capped = max(1, min(int(limit), 200))
    start = max(0, int(offset))
    page = rows[start:start + capped]
    items = [{
        "id": eid,
        "type": etype,
        "name": display_name(attrs, eid),
        "attributes": attrs or {},
        "sources": by_entity.get(eid, []),
    } for eid, etype, attrs in page]
    return {"type": ontology_type, "total": total,
            "offset": start, "limit": capped, "items": items}


def graph_view(entities: list[tuple[int, str, dict]],
               relationships: list[tuple[int, int, str]]) -> dict[str, Any]:
    """Type-level knowledge map: nodes per type, edges aggregated by relation.

    Renders the *shape* of the graph (Customer -HAS_SITE(22)-> Site ...) rather
    than every node — legible at any scale, the query-don't-render rule.
    """
    id_type = {eid: etype for eid, etype, _ in entities}
    type_counts = Counter(etype for _, etype, _ in entities)
    edge_agg: Counter = Counter()
    for src, tgt, name in relationships:
        st, tt = id_type.get(src), id_type.get(tgt)
        if st and tt:
            edge_agg[(st, tt, name)] += 1
    return {
        "type_nodes": [{"type": t, "count": c}
                       for t, c in type_counts.most_common()],
        "type_edges": [{"source": s, "target": t, "name": n, "count": c}
                       for (s, t, n), c in edge_agg.most_common()],
        "entity_count": len(entities),
        "relationship_count": len(relationships),
    }

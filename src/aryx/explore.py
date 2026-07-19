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


def _entity_label(
    attributes: dict[str, Any] | None, entity_id: int,
    label_attr: str | None = None,
) -> str:
    """Use the hierarchy label column before the generic display fallback."""
    attrs = attributes or {}
    if label_attr and attrs.get(label_attr) not in (None, ""):
        return str(attrs[label_attr])
    return display_name(attrs, entity_id)


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


def grouped_entities_view(entities: list[tuple[int, str, dict]],
                          provenance: list[tuple[int, str, str, str]],
                          hub_attr: str, label_attr: str | None = None,
                          ontology_type: str | None = None,
                          group_limit: int = 25, group_offset: int = 0) -> dict[str, Any]:
    """Entities grouped under their hub value (e.g. child rows by parent_key).

    The table companion to the hub/spoke graph: rows are bucketed by
    ``hub_attr`` so related child rows sit together under one header.
    Paginated by GROUP (``group_offset``/``group_limit``) so large sources stay
    responsive. Each row is labelled by ``label_attr`` when given,
    else its display name. General — the caller supplies the columns.
    """
    by_entity = _prov_by_entity(provenance)
    rows = [e for e in entities if not ontology_type or e[1] == ontology_type]
    buckets: dict[str, list[tuple[int, str, dict]]] = {}
    for eid, etype, attrs in rows:
        key = str((attrs or {}).get(hub_attr, "")).strip() or "—"
        buckets.setdefault(key, []).append((eid, etype, attrs))
    order = sorted(buckets)
    start = max(0, int(group_offset))
    limit = max(1, min(int(group_limit), 200))
    groups = []
    for key in order[start:start + limit]:
        items = [{
            "id": eid,
            "type": etype,
            "name": (str(attrs[label_attr]) if label_attr and attrs
                     and attrs.get(label_attr) not in (None, "")
                     else display_name(attrs, eid)),
            "attributes": attrs or {},
            "sources": by_entity.get(eid, []),
        } for eid, etype, attrs in buckets[key]]
        groups.append({"key": key, "count": len(items), "items": items})
    return {"grouped": True, "group_attr": hub_attr, "label_attr": label_attr,
            "total_groups": len(order), "group_offset": start,
            "group_limit": limit, "groups": groups}


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


_ID_HINT = ("number", "num", "no", "id", "code", "ref", "key")
_MEASURE_HINT = ("amount", "price", "cost", "total", "qty", "value", "rate",
                 "sum", "count", "date")


def _attr_values(entities: list[tuple[int, str, dict]],
                 attr: str) -> list[str]:
    """Non-empty string values of one attribute across entities."""
    return [str(a[attr]) for _, _, a in entities
            if a and a.get(attr) not in (None, "", [])]


def _parent_type(otype: str) -> str:
    """Name the hub concept after its spokes: ChildLine -> Child."""
    for suf in ("Lines", "Items", "Line", "Item"):
        if otype.endswith(suf) and len(otype) > len(suf):
            return otype[:-len(suf)]
    return otype


def detect_hierarchy(
    entities: list[tuple[int, str, dict]]
) -> tuple[str, str | None] | None:
    """Detect a hub/spoke shape: a grouping key + a within-group discriminator.

    Hierarchical data (many child rows sharing a smaller set of parent keys,
    each child distinguished by another key) reads as thousands of disconnected
    nodes in the flat entity view. When one attribute groups the rows and
    another makes each row unique within its group, we can render a hub per
    group with its children hanging off it.

    Returns ``(hub_attr, label_attr)`` or None when the data isn't hierarchical
    (so the caller falls back to the flat view). ``label_attr`` may be None,
    meaning label the spokes by their display name.
    """
    n = len(entities)
    if n < 4:
        return None
    types = {etype for _, etype, _ in entities}
    if len(types) != 1:            # hub/spoke only makes sense within one type
        return None
    attrs = {k for _, _, a in entities for k in (a or {})
             if k != "_provenance"}

    def _idish(k: str) -> bool:
        return any(h in k.lower() for h in _ID_HINT)

    def _measure(k: str) -> bool:
        return any(m in k.lower() for m in _MEASURE_HINT)

    # Hub: identifier-like, present on most rows, groups exist but isn't unique
    # per row. Prefer bigger groups (lower distinct ratio) to avoid picking a
    # near-unique column that would make every row its own hub.
    hub: tuple[tuple[int, float], str] | None = None
    for k in attrs:
        if _measure(k):
            continue
        vals = _attr_values(entities, k)
        if len(vals) < n * 0.8:
            continue
        ratio = len(set(vals)) / n
        if not (0.02 <= ratio <= 0.9):
            continue
        score = (1 if _idish(k) else 0, -ratio)
        if hub is None or score > hub[0]:
            hub = (score, k)
    if hub is None:
        return None
    hub_attr = hub[1]

    # Label: makes (hub, label) unique across rows; prefer identifier-like with
    # the fewest distinct values (a positional discriminator like child_key,
    # not a high-cardinality Product Number).
    label: tuple[tuple[int, int], str] | None = None
    for k in attrs:
        if k == hub_attr or _measure(k):
            continue
        pairs, present = set(), 0
        for _, _, a in entities:
            hv, lv = (a or {}).get(hub_attr), (a or {}).get(k)
            if hv in (None, "") or lv in (None, ""):
                continue
            present += 1
            pairs.add((str(hv), str(lv)))
        if present >= n * 0.8 and len(pairs) >= present * 0.98:
            distinct = len(set(_attr_values(entities, k)))
            score = (1 if _idish(k) else 0, -distinct)
            if label is None or score > label[0]:
                label = (score, k)
    return hub_attr, (label[1] if label else None)


def entity_graph_view(entities: list[tuple[int, str, dict]],
                      relationships: list[tuple[int, int, str]],
                      hub_attr: str | None = None,
                      label_attr: str | None = None) -> dict[str, Any]:
    """Entity-level graph: one node per resolved entity, one edge per link.

    The detail companion to ``graph_view`` — shows the specific mappings
    (which Company each Customer belongs to) rather than the aggregated shape.
    When the entities form a hub/spoke shape, renders that hierarchy instead
    of a flat node soup.

    ``hub_attr``/``label_attr`` let the caller pin the grouping to the columns
    the user named in the goal — honoured over
    auto-detection, which can pick a different-but-valid grouping (e.g. by
    Customer Number). Falls back to auto-detection, then the flat view.
    """
    attr_names = {k for _, _, a in entities for k in (a or {})}
    if hub_attr and hub_attr in attr_names:
        materialized = _materialized_hierarchy(
            entities, relationships, hub_attr,
            label_attr if label_attr in attr_names else None)
        if materialized:
            return materialized
        return _hub_spoke_view(entities, relationships, hub_attr,
                               label_attr if label_attr in attr_names else None)
    hier = detect_hierarchy(entities)
    if hier is not None:
        materialized = _materialized_hierarchy(entities, relationships, *hier)
        if materialized:
            return materialized
        return _hub_spoke_view(entities, relationships, *hier)
    return _flat_entity_graph(entities, relationships)


def _flat_entity_graph(entities: list[tuple[int, str, dict]],
                       relationships: list[tuple[int, int, str]],
                       label_attr: str | None = None) -> dict[str, Any]:
    """Render real entities and stored relationships without synthetic hubs."""
    id_type = {eid: etype for eid, etype, _ in entities}
    nodes = [{"id": eid, "type": etype, "name": _entity_label(attrs, eid, label_attr)}
             for eid, etype, attrs in entities]
    edges = [{"source": src, "target": tgt, "name": name}
             for src, tgt, name in relationships
             if src in id_type and tgt in id_type]
    return {
        "nodes": nodes,
        "edges": edges,
        "entity_count": len(nodes),
        "relationship_count": len(edges),
    }


def _materialized_hierarchy(
    entities: list[tuple[int, str, dict]],
    relationships: list[tuple[int, int, str]],
    hub_attr: str,
    label_attr: str | None,
) -> dict[str, Any] | None:
    """Return the real graph when hub entities + hub edges already exist."""
    by_id = {eid: (etype, attrs or {}) for eid, etype, attrs in entities}
    child_types = [
        etype for _, etype, attrs in entities
        if attrs and attrs.get(hub_attr) not in (None, "")
    ]
    if not child_types:
        return None
    child_type = Counter(child_types).most_common(1)[0][0]
    parent_type = _parent_type(child_type)
    edge_name = f"HAS_{child_type.upper()}"
    for src, tgt, name in relationships:
        src_meta, tgt_meta = by_id.get(src), by_id.get(tgt)
        if not src_meta or not tgt_meta or name != edge_name:
            continue
        if src_meta[0] == parent_type and tgt_meta[0] == child_type:
            return _flat_entity_graph(entities, relationships, label_attr)
    return None


def _hub_spoke_view(entities: list[tuple[int, str, dict]],
                    relationships: list[tuple[int, int, str]],
                    hub_attr: str, label_attr: str | None) -> dict[str, Any]:
    """Render a hub node per ``hub_attr`` value with its rows as spokes.

    Hub nodes get string ids (``hub:<value>``) so they never collide with the
    integer entity ids of the spokes; the UI treats a non-numeric id as an
    aggregate (no detail fetch). Each spoke links to its hub via HAS_ item.
    """
    otype = entities[0][1]
    parent = _parent_type(otype)  # hub concept name: ChildLine -> Child
    edge_name = f"HAS_{otype.upper()}"
    ids = {eid for eid, _, _ in entities}
    hub_ids: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    # Keep any real inter-entity relationships alongside the hub->spoke edges.
    edges: list[dict[str, Any]] = [
        {"source": src, "target": tgt, "name": name}
        for src, tgt, name in relationships if src in ids and tgt in ids]
    for eid, _etype, attrs in entities:
        attrs = attrs or {}
        hv = attrs.get(hub_attr)
        label = _entity_label(attrs, eid, label_attr)
        nodes.append({"id": eid, "type": otype, "name": label})
        if hv in (None, ""):
            continue
        hv = str(hv)
        if hv not in hub_ids:
            hid = f"hub:{hv}"
            hub_ids[hv] = hid
            nodes.append({"id": hid, "type": parent, "name": hv})
        edges.append({"source": hub_ids[hv], "target": eid, "name": edge_name})
    return {
        "nodes": nodes,
        "edges": edges,
        "entity_count": len(entities),
        "relationship_count": len(edges),
    }


def entity_detail(entities: list[tuple[int, str, dict]],
                  provenance: list[tuple[int, str, str, str]],
                  relationships: list[tuple[int, int, str]],
                  entity_id: int,
                  hub_attr: str | None = None,
                  label_attr: str | None = None) -> dict[str, Any] | None:
    """One entity's full record: attributes, source provenance, and neighbours.

    Powers the graph side panel — clicking a node shows what it is, where it
    came from, and everything it connects to (with edge label + direction).
    Returns None when the id is not in this workspace.

    ``hub_attr`` mirrors the hub/spoke graph: when set, a synthesized edge to
    the entity's hub is added so the
    panel matches the picture. It's display-only — no stored relationship — so
    it also lists a hub's spokes when a hub node itself is inspected.
    """
    meta = {eid: (etype, attrs) for eid, etype, attrs in entities}
    if entity_id not in meta:
        return None
    name_of = {eid: _entity_label(a, eid, label_attr) for eid, _, a in entities}
    type_of = {eid: t for eid, t, _ in entities}
    rels: list[dict[str, Any]] = []
    for src, tgt, name in relationships:
        if src == entity_id and tgt in meta:
            rels.append({"direction": "out", "name": name, "other_id": tgt,
                         "other_name": name_of[tgt], "other_type": type_of[tgt]})
        elif tgt == entity_id and src in meta:
            rels.append({"direction": "in", "name": name, "other_id": src,
                         "other_name": name_of[src], "other_type": type_of[src]})
    etype, attrs = meta[entity_id]
    if hub_attr:
        hv = (attrs or {}).get(hub_attr)
        if hv not in (None, ""):
            edge = f"HAS_{etype.upper()}"
            parent = _parent_type(etype)
            has_real_hub = any(
                r["direction"] == "in" and r["name"] == edge
                and r["other_type"] == parent
                for r in rels
            )
            if not has_real_hub:
                rels.insert(0, {
                    "direction": "in", "name": edge, "other_id": f"hub:{hv}",
                    "other_name": str(hv), "other_type": parent})
    return {
        "id": entity_id,
        "type": etype,
        "name": _entity_label(attrs, entity_id, label_attr),
        "attributes": attrs or {},
        "sources": _prov_by_entity(provenance).get(entity_id, []),
        "relationships": rels,
    }

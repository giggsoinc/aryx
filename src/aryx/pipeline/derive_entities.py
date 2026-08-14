"""Derive a new entity type by deduplicating an existing type's column.

Groups an already-resolved type's entities by one attribute (e.g. every
ContractLineItem row that shares a "Customer Number") and writes one new
entity per distinct group value, registering a new ontology type for it.
Provenance is carried forward: each new entity's members are the union of
landed_record_ids behind every source entity folded into its group, so
lineage traces back to the original ingested rows, not just to the
intermediate source entities.
"""
from __future__ import annotations

import logging

from aryx.graph import FalkorStore
from aryx.models import EntityMember, ResolvedEntity
from aryx.pipeline.enrich import _build_type_ancestors
from aryx.project import project_graph
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)


def _norm(value: object) -> str | None:
    """Normalize a group-by value the same way fk_edges.py matches later
    (case-insensitive, trimmed) so entities derived here link cleanly."""
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _group_source_entities(
    source: list[tuple[int, dict]], group_by_attr: str, carry_attrs: list[str],
) -> tuple[dict[str, dict], dict[str, list[int]], int]:
    """Fold source entities into one bucket per normalized group_by_attr
    value. Survivorship for carry_attrs: first non-empty value wins
    (documented v1 default — no conflict-resolution UI).

    Returns (groups, group_source_ids, skipped) — `groups` maps norm key ->
    the derived entity's attributes dict, `group_source_ids` maps the same
    key -> the source entity ids folded into it (for provenance), `skipped`
    counts source rows with no usable group_by_attr value.
    """
    groups: dict[str, dict] = {}
    group_source_ids: dict[str, list[int]] = {}
    skipped = 0
    for eid, attrs in source:
        if not isinstance(attrs, dict):
            skipped += 1
            continue
        raw_key = attrs.get(group_by_attr)
        key = _norm(raw_key)
        if not key:
            skipped += 1
            continue
        group_source_ids.setdefault(key, []).append(eid)
        bucket = groups.setdefault(key, {group_by_attr: str(raw_key).strip()})
        for attr in carry_attrs:
            if bucket.get(attr) in (None, ""):
                val = attrs.get(attr)
                if val not in (None, ""):
                    bucket[attr] = val
    return groups, group_source_ids, skipped


def _resolved_entities_for_groups(
    new_type_name: str, groups: dict[str, dict], group_source_ids: dict[str, list[int]],
    landed_by_entity: dict[int, list[int]],
) -> list[tuple[ResolvedEntity, list[EntityMember]]]:
    """Build one (ResolvedEntity, members) pair per group, with provenance
    members carrying the union of landed_record_ids behind every source
    entity folded into that group."""
    to_save: list[tuple[ResolvedEntity, list[EntityMember]]] = []
    for key, attrs in groups.items():
        landed_ids = sorted({
            lrid for eid in group_source_ids[key]
            for lrid in landed_by_entity.get(eid, [])
        })
        resolved = ResolvedEntity(ontology_type=new_type_name, attributes=attrs, confidence=1.0)
        members = [EntityMember(landed_record_id=lrid, confidence=1.0) for lrid in landed_ids]
        to_save.append((resolved, members))
    return to_save


def derive_entities_by_column(
    dsn: str, graph_url: str, workspace_id: int,
    source_type: str, group_by_attr: str, new_type_name: str,
    carry_attrs: list[str] | None = None,
) -> dict[str, int | str]:
    """Create one new-type entity per distinct value of group_by_attr.

    Args:
        dsn: Postgres DSN.
        graph_url: FalkorDB connection URL.
        workspace_id: Workspace to read from / write into.
        source_type: Ontology type whose entities are grouped, e.g. ContractLineItem.
        group_by_attr: Attribute key to dedupe on, e.g. "Customer Number".
        new_type_name: Name of the derived type to create/merge into, e.g. Customer.
        carry_attrs: Additional attribute keys to copy onto each derived entity.

    Returns:
        {"type", "created", "source_groups", "skipped_missing_key",
        **project_graph counts}. `created` is the literal count of new
        entities written — 0 is a real, surfaced outcome (never a silent
        success), same contract as /pipeline/link-entities.
    """
    carry_attrs = carry_attrs or []
    estore = EntityStore(dsn, workspace_id)
    try:
        source = [(eid, attrs) for eid, etype, attrs in estore.list_entities()
                  if etype == source_type]
        groups, group_source_ids, skipped = _group_source_entities(
            source, group_by_attr, carry_attrs)

        all_source_ids = [eid for ids in group_source_ids.values() for eid in ids]
        landed_by_entity = estore.member_landed_ids(all_source_ids)
        to_save = _resolved_entities_for_groups(
            new_type_name, groups, group_source_ids, landed_by_entity)

        created = estore.save(to_save)
        ostore = OntologyStore(dsn, workspace_id)
        try:
            ostore.merge_attributes(new_type_name, [group_by_attr] + carry_attrs)
        finally:
            ostore.close()

        type_ancestors = _build_type_ancestors(dsn)
        counts = project_graph(
            estore, FalkorStore(graph_url, ws_graph(workspace_id)),
            type_ancestors=type_ancestors, workspace_id=workspace_id,
        )
    finally:
        estore.close()
    logger.info(
        "derive_entities ws=%s source=%s group_by=%s new_type=%s groups=%d "
        "created=%d skipped=%d",
        workspace_id, source_type, group_by_attr, new_type_name,
        len(groups), created, skipped,
    )
    return {
        "type": new_type_name, "created": created,
        "source_groups": len(groups), "skipped_missing_key": skipped,
        **counts,
    }

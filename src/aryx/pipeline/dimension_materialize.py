"""Materialize dimension entities from graph_plan column mappings.

After primary row-entities land, create one entity per distinct value in
declared dimension columns and link row → dimension by attribute equality.
Provider-agnostic / deterministic — plan comes from smart_understand.
Entity creation itself lives in ``dimension_entities.py``; this module owns
merging column samples across files and linking the result.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.graph import FalkorStore
from aryx.pipeline.dimension_entities import materialize_one_dimension
from aryx.pipeline.fk_edges import link_by_attribute
from aryx.project import project_graph
from aryx.store.entity_store import EntityStore
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)


def _relationship_direction(
    rel: dict[str, Any], dim_by_name: dict[str, dict[str, Any]],
) -> tuple[str, str, str, str]:
    """The (source_type, target_type, via_column, edge_name) to link on.

    The LLM sometimes states a relationship in causal/semantic order
    ("Company placed Order") rather than FK-carrier order ("Order.
    company_name points at Company") — that produces a from/to pair where
    neither side actually owns via_column, so link_by_attribute finds zero
    matches regardless of the data. dimension_types is generated
    deterministically from column ownership (from_type is always the
    row-entity that actually carries source_column), so it's the authority
    on direction — use it to correct src/tgt whenever a dimension agrees
    on the same column; otherwise trust the relationship as stated.
    """
    src = str(rel.get("from") or "")
    tgt = str(rel.get("to") or "")
    via = str(rel.get("via_column") or "")
    name = str(rel.get("name") or f"{src}_{tgt}").upper()
    dim = dim_by_name.get(src) or dim_by_name.get(tgt)
    if dim and dim.get("source_column") == via:
        src = str(dim.get("from_type") or src)
        tgt = str(dim.get("name") or tgt)
    return src, tgt, via, name


def _link_dimension_relationships(
    rels: list[Any], dim_by_name: dict[str, dict[str, Any]], *,
    dsn: str, graph_url: str, workspace_id: int,
) -> int:
    """Link row entities to dimensions per plan, then re-project the graph."""
    from aryx.pipeline.enrich import _build_type_ancestors

    total_rels = 0
    estore = EntityStore(dsn, workspace_id)
    try:
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            src, tgt, via, name = _relationship_direction(rel, dim_by_name)
            if not (src and tgt and via):
                continue
            n = link_by_attribute(estore, src, via, tgt, "name", name)
            total_rels += n
            logger.info("linked %s -[%s]-> %s count=%d", src, name, tgt, n)
        project_graph(
            estore, FalkorStore(graph_url, ws_graph(workspace_id)),
            type_ancestors=_build_type_ancestors(dsn),
            workspace_id=workspace_id,
        )
    finally:
        estore.close()
    return total_rels


def materialize_dimensions(
    *,
    dsn: str,
    graph_url: str,
    workspace_id: int,
    broker: Any,
    graph_plan: dict[str, Any],
    colvals_by_file: list[dict[str, Any]],
) -> int:
    """Create dimension entities + links from plan. Returns relationship count."""
    dims = graph_plan.get("dimension_types") or []
    if not dims:
        return 0

    merged: dict[str, list[str]] = {}
    for plan in colvals_by_file:
        for col, vals in (plan.get("colvals") or {}).items():
            merged.setdefault(col, []).extend(vals)

    for dim in dims:
        if isinstance(dim, dict):
            materialize_one_dimension(dim, merged, dsn=dsn, graph_url=graph_url,
                                      workspace_id=workspace_id, broker=broker)

    dim_by_name = {str(d.get("name") or "").strip(): d
                   for d in dims if isinstance(d, dict)}
    return _link_dimension_relationships(
        graph_plan.get("relationships") or [], dim_by_name,
        dsn=dsn, graph_url=graph_url, workspace_id=workspace_id)

"""Materialize dimension entities from graph_plan column mappings.

After primary row-entities land, create one entity per distinct value in
declared dimension columns and link row → dimension by attribute equality.
Provider-agnostic / deterministic — plan comes from smart_understand.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.connectors.records_source import RecordsConnector
from aryx.graph import FalkorStore
from aryx.models import RawRecord, SourceRef
from aryx.pipeline.fk_edges import link_by_attribute
from aryx.pipeline.orchestrate import run_pipeline
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
    rels = graph_plan.get("relationships") or []
    if not dims:
        return 0

    # Merge column values across files
    merged: dict[str, list[str]] = {}
    for plan in colvals_by_file:
        for col, vals in (plan.get("colvals") or {}).items():
            merged.setdefault(col, []).extend(vals)

    total_rels = 0
    from aryx.api import ontology_browse

    for dim in dims:
        if not isinstance(dim, dict):
            continue
        dim_name = str(dim.get("name") or "").strip()
        source_col = str(dim.get("source_column") or "").strip()
        if not dim_name or not source_col:
            continue
        vals = merged.get(source_col) or []
        # case-insensitive column match
        if not vals:
            for k, v in merged.items():
                if k.lower() == source_col.lower():
                    vals = v
                    source_col = k
                    break
        # First-seen order, not alphabetical: dimension record_id assignment
        # (Company:0, Company:1, ...) becomes the "landed first" signal the
        # default first_non_empty survivorship strategy relies on. Sorting
        # alphabetically here would make that choice depend on the alphabet
        # instead of the source file — the exact non-determinism DEC-004
        # ("order-independent merge") was written to rule out.
        seen: set[str] = set()
        unique: list[str] = []
        for v in vals:
            v = (v or "").strip()
            if v and v not in seen:
                seen.add(v)
                unique.append(v)
        if not unique:
            logger.info("dimension %s: no values for column %s", dim_name, source_col)
            continue
        try:
            ontology_browse.add_type(
                dim_name, ["name", "source_column"], "approved",
                source="smart-plan", workspace_id=workspace_id,
            )
        except Exception:  # noqa: BLE001
            pass
        recs = [
            RawRecord(
                source=SourceRef(
                    system="dimension", dataset=dim_name, record_id=f"{dim_name}:{i}",
                ),
                payload={"name": u, "source_column": source_col, "type": dim_name},
            )
            for i, u in enumerate(unique)
        ]
        logger.info("materializing %d × %s from column %s", len(recs), dim_name, source_col)
        run_pipeline(
            connector=RecordsConnector(recs),
            dsn=dsn,
            system="dimension",
            dataset=dim_name,
            ontology_type=dim_name,
            match_keys=["name"],
            graph_url=graph_url,
            broker=broker,
            workspace_id=workspace_id,
        )

    # Links from relationships in plan.
    dim_by_name = {str(d.get("name") or "").strip(): d
                   for d in dims if isinstance(d, dict)}
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
        # re-project dirty graph
        from aryx.pipeline.enrich import _build_type_ancestors
        project_graph(
            estore, FalkorStore(graph_url, ws_graph(workspace_id)),
            type_ancestors=_build_type_ancestors(dsn),
            workspace_id=workspace_id,
        )
    finally:
        estore.close()
    return total_rels

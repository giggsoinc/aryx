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
        dname = str(dim.get("name") or "").strip()
        scol = str(dim.get("source_column") or "").strip()
        if not dname or not scol:
            continue
        vals = merged.get(scol) or []
        # case-insensitive column match
        if not vals:
            for k, v in merged.items():
                if k.lower() == scol.lower():
                    vals = v
                    scol = k
                    break
        unique = sorted({(v or "").strip() for v in vals if (v or "").strip()})
        if not unique:
            logger.info("dimension %s: no values for column %s", dname, scol)
            continue
        try:
            ontology_browse.add_type(
                dname, ["name", "source_column"], "approved",
                source="smart-plan", workspace_id=workspace_id,
            )
        except Exception:  # noqa: BLE001
            pass
        recs = [
            RawRecord(
                source=SourceRef(
                    system="dimension", dataset=dname, record_id=f"{dname}:{i}",
                ),
                payload={"name": u, "source_column": scol, "type": dname},
            )
            for i, u in enumerate(unique)
        ]
        logger.info("materializing %d × %s from column %s", len(recs), dname, scol)
        run_pipeline(
            connector=RecordsConnector(recs),
            dsn=dsn,
            system="dimension",
            dataset=dname,
            ontology_type=dname,
            match_keys=["name"],
            graph_url=graph_url,
            broker=broker,
            workspace_id=workspace_id,
        )

    # Links from relationships in plan
    estore = EntityStore(dsn, workspace_id)
    try:
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            src = str(rel.get("from") or "")
            tgt = str(rel.get("to") or "")
            via = str(rel.get("via_column") or "")
            name = str(rel.get("name") or f"{src}_{tgt}").upper()
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

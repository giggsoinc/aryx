"""Dimension-entity creation from graph_plan column values.

Split out of ``dimension_materialize.py`` to keep each file under the size
cap — this module owns turning one dimension type's distinct column values
into landed entities; linking those entities to row types lives in
``dimension_materialize.py``.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.connectors.records_source import RecordsConnector
from aryx.models import RawRecord, SourceRef
from aryx.pipeline.orchestrate import run_pipeline

logger = logging.getLogger(__name__)


def dedup_first_seen(vals: list[str]) -> list[str]:
    """Dedup preserving first-seen order, not alphabetical.

    Dimension record_id assignment (Company:0, Company:1, ...) becomes the
    "landed first" signal the default first_non_empty survivorship strategy
    relies on. Sorting alphabetically would make that choice depend on the
    alphabet instead of the source file — the non-determinism DEC-004
    ("order-independent merge") was written to rule out.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for v in vals:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def materialize_one_dimension(
    dim: dict[str, Any], merged: dict[str, list[str]], *,
    dsn: str, graph_url: str, workspace_id: int, broker: Any,
) -> None:
    """Create one dimension type's entities from its distinct column values."""
    from aryx.api import ontology_browse

    dim_name = str(dim.get("name") or "").strip()
    source_col = str(dim.get("source_column") or "").strip()
    if not dim_name or not source_col:
        return
    vals = merged.get(source_col) or []
    if not vals:  # case-insensitive column match
        for k, v in merged.items():
            if k.lower() == source_col.lower():
                vals, source_col = v, k
                break
    unique = dedup_first_seen(vals)
    if not unique:
        logger.info("dimension %s: no values for column %s", dim_name, source_col)
        return
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
        connector=RecordsConnector(recs), dsn=dsn, system="dimension",
        dataset=dim_name, ontology_type=dim_name, match_keys=["name"],
        graph_url=graph_url, broker=broker, workspace_id=workspace_id,
    )

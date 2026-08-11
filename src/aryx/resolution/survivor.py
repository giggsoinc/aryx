"""Confidence-weighted golden record with conflict detection and provenance (G3)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def survivors(
    payloads: list[dict[str, Any]],
    record_ids: list[int],
    pair_scores: dict[tuple[int, int], float],
    edge_index: dict[int, list[tuple[int, float]]] | None = None,
) -> dict[str, Any]:
    """Merge cluster payloads into one golden record.

    Each attribute value is weighted by the average pairwise similarity score
    of the records that contributed it. The highest-weight value wins.

    Conflicting values (different non-empty values for the same key) trigger a
    WARNING so data-quality issues surface without blocking the pipeline.
    A ``_provenance`` key maps each attribute to the record_id that won.

    When pair_scores is empty (legacy call path), falls back to first-non-empty
    value per attribute with no warnings, matching the old golden_record() behaviour.

    Args:
        payloads: Attribute dicts for each record in the cluster.
        record_ids: Ids parallel to payloads; used for provenance + weighting.
        pair_scores: {(id_a, id_b): score} from the resolution scoring loop.
        edge_index: Optional output of ``confidence.build_edge_index(pair_scores)``.
            Supplying it replaces a full scan of ``pair_scores`` per record with an
            O(degree) lookup — the same weights, without the quadratic cost. Build
            it once per resolution run, never inside the cluster loop. When omitted
            the original scan is used, so existing callers are unaffected.

    Returns:
        Merged attribute dict including ``_provenance``.
    """
    if not payloads:
        return {}
    if not pair_scores and not edge_index:
        return _legacy_merge(payloads, record_ids)

    # Build per-attribute candidate groups: str(value) → (value, total_weight, record_id)
    groups: dict[str, dict[str, list[Any]]] = {}
    for i, payload in enumerate(payloads):
        rid = record_ids[i] if i < len(record_ids) else i
        weight = _record_weight(rid, pair_scores, edge_index)
        for key, value in payload.items():
            if value in (None, "", []):
                continue
            val_str = str(value)
            bucket = groups.setdefault(key, {})
            if val_str not in bucket:
                bucket[val_str] = [value, 0.0, rid]
            bucket[val_str][1] += weight

    merged: dict[str, Any] = {}
    prov: dict[str, int] = {}
    for key, bucket in groups.items():
        if len(bucket) > 1:
            logger.warning(
                "conflict attr=%s values=%r record_ids=%r — top-weight value kept",
                key, list(bucket.keys()), record_ids,
            )
        best_str = max(bucket, key=lambda s: bucket[s][1])
        merged[key] = bucket[best_str][0]
        prov[key] = bucket[best_str][2]
    merged["_provenance"] = prov
    return merged


def _record_weight(
    rid: int,
    pair_scores: dict[tuple[int, int], float],
    edge_index: dict[int, list[tuple[int, float]]] | None,
) -> float:
    """Mean score of every scored pair touching ``rid``; 1.0 when it has none.

    Two paths, identical results:

    * indexed — O(degree of rid), using ``confidence.build_edge_index``.
    * scan — the original ``a == rid or b == rid`` filter over all pair_scores,
      kept so callers that pass no index behave exactly as before.

    A self-pair ``(rid, rid)`` is stored once in the index and matches once in
    the scan, so both paths weight it the same.
    """
    if edge_index is not None:
        scores = [score for _other, score in edge_index.get(rid, ())]
    else:
        scores = [v for (a, b), v in pair_scores.items() if a == rid or b == rid]
    return sum(scores) / len(scores) if scores else 1.0


def _legacy_merge(
    payloads: list[dict[str, Any]], record_ids: list[int]
) -> dict[str, Any]:
    """First-non-empty-value merge — backward-compat fallback."""
    merged: dict[str, Any] = {}
    prov: dict[str, int] = {}
    for i, payload in enumerate(payloads):
        rid = record_ids[i] if i < len(record_ids) else i
        for key, value in payload.items():
            if key not in merged and value not in (None, "", []):
                merged[key] = value
                prov[key] = rid
    merged["_provenance"] = prov
    return merged

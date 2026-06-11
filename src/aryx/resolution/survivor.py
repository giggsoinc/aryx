"""Confidence-weighted golden record with conflict detection and provenance (G3)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def survivors(
    payloads: list[dict[str, Any]],
    record_ids: list[int],
    pair_scores: dict[tuple[int, int], float],
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

    Returns:
        Merged attribute dict including ``_provenance``.
    """
    if not payloads:
        return {}

    if not pair_scores:
        return _legacy_merge(payloads, record_ids)

    # Build per-attribute candidate groups: str(value) → (value, total_weight, record_id)
    groups: dict[str, dict[str, list[Any]]] = {}
    for i, payload in enumerate(payloads):
        rid = record_ids[i] if i < len(record_ids) else i
        scores = [
            v for (a, b), v in pair_scores.items() if a == rid or b == rid
        ]
        weight = sum(scores) / len(scores) if scores else 1.0
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

"""Entity resolution funnel (stage 7): block -> score -> adjudicate -> cluster."""
from __future__ import annotations

import logging

from aryx.broker import Broker
from aryx.models import EntityMember, ResolutionRecord, ResolvedEntity
from aryx.resolution.adjudicate import adjudicate
from aryx.resolution.classical import block, score_pair
from aryx.resolution.cluster import UnionFind, golden_record_weighted

logger = logging.getLogger(__name__)

_AUTO_MERGE = 0.92
_REJECT = 0.60
# Only the genuinely ambiguous middle reaches the LLM; clear non-matches
# (below ADJUDICATE_FROM) skip it entirely so CPU-only boxes stay usable.
_ADJUDICATE_FROM = 0.90


def _block_embeddings(
    records: list[ResolutionRecord], broker: Broker
) -> dict[int, list[float]]:
    """Embed a block's texts locally; empty dict if embeddings unavailable."""
    try:
        vectors = broker.embed([r.text for r in records])
    except Exception:  # embeddings are optional — fall back to string-only  # noqa: BLE001
        vectors = []
    return {r.record_id: v for r, v in zip(records, vectors)} if vectors else {}


def resolve(
    records: list[ResolutionRecord], broker: Broker, ontology_type: str
) -> list[tuple[ResolvedEntity, list[EntityMember]]]:
    """Resolve records into canonical entities via the funnel.

    High-similarity pairs auto-merge, low-similarity reject, and only the
    ambiguous middle reaches the frontier model. Matches union into clusters;
    each cluster becomes one entity with a golden record.

    Args:
        records: Landed records prepared for matching.
        broker: Model broker (embeddings local, adjudication frontier).
        ontology_type: Canonical type these records resolve into.

    Returns:
        (entity, members) pairs, one per cluster.
    """
    by_id = {r.record_id: r for r in records}
    union = UnionFind()
    pair_scores: dict[tuple[int, int], float] = {}
    for record in records:
        union.add(record.record_id)

    for group in block(records).values():
        embeddings = _block_embeddings(group, broker)
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                left, right = group[i], group[j]
                score = score_pair(left.text, right.text,
                                   embeddings.get(left.record_id),
                                   embeddings.get(right.record_id))
                pair_scores[(left.record_id, right.record_id)] = score
                if score >= _AUTO_MERGE:
                    union.union(left.record_id, right.record_id)
                elif score >= _ADJUDICATE_FROM and adjudicate(left, right, broker):
                    union.union(left.record_id, right.record_id)

    results: list[tuple[ResolvedEntity, list[EntityMember]]] = []
    for member_ids in union.groups().values():
        records_in = [by_id[mid] for mid in member_ids]
        merged = golden_record_weighted(
            [r.payload for r in records_in], member_ids, pair_scores,
        )
        provenance = merged.pop("_provenance", None)
        entity = ResolvedEntity(
            ontology_type=ontology_type,
            attributes=merged,
            confidence=1.0 if len(member_ids) > 1 else 0.5,
            provenance=provenance,
        )
        members = [EntityMember(landed_record_id=mid) for mid in member_ids]
        results.append((entity, members))
    logger.info("resolved records=%d entities=%d", len(records), len(results))
    return results

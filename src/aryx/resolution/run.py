"""Entity resolution funnel (stage 7): block -> score -> adjudicate -> cluster.

Thresholds (env-tunable, defaults from the G9 sweep — see DECISIONS.md):
  ARYX_ER_AUTO_MERGE   >= this -> auto-merge                       (default 0.95)
  ARYX_ER_ADJUDICATE   [ARYX_ER_REVIEW, AUTO_MERGE) -> LLM rescores (band, no threshold of its own)
                       rescored >= AUTO_MERGE -> merge;
                       rescored <  AUTO_REJECT -> auto-reject (DEC-010);
                       else -> human queue
  ARYX_ER_REVIEW       below this -> human queue directly           (default 0.80)
  ARYX_ER_AUTO_REJECT  LLM rescore below this -> auto-reject, no human queue (default 0.05, DEC-010)
  Every pair below AUTO_MERGE and at/above AUTO_REJECT ends up merged or queued;
  nothing ambiguous is silently dropped — only a confidently-non-matching LLM
  verdict is.

Pairs routed to the human queue are treated as NON-merge for the current run
(conservative: a wrong merge is worse than a missed merge in audited domains).
A later human approval unions the entities via apply_decision (G10).

Materialisation cost
--------------------
``_materialize`` runs once per cluster, and both of its helpers used to answer
"which scored pairs touch these records?" by scanning the whole ``pair_scores``
dict — ``cluster_edges`` once per cluster, ``survivors`` once per RECORD. Total
work grew as ``records x total_pairs``, which on a few thousand records reads
as a hang rather than a slow run. ``resolve`` now inverts ``pair_scores`` once
into an edge index and passes it down; results are unchanged.
"""
from __future__ import annotations

import logging
import os

from aryx.broker import Broker
from aryx.config import get_settings
from aryx.models import EntityMember, ResolutionRecord, ResolvedEntity
from aryx.resolution.adjudicate import adjudicate
from aryx.resolution.classical import block, score_pair
from aryx.resolution.cluster import UnionFind, golden_record_weighted
from aryx.resolution.confidence import (
    build_edge_index,
    cluster_confidence,
    cluster_edges,
    cluster_edges_indexed,
)
from aryx.resolution.golden import golden_record_with_policy
from aryx.resolution.review_queue import ReviewSink
from aryx.resolution.survivorship import SurvivorshipPolicy

logger = logging.getLogger(__name__)


def _threshold(env: str, default: float) -> float:
    """Read one tunable threshold from the environment."""
    try:
        return float(os.environ.get(env, default))
    except ValueError:
        return default


def _block_embeddings(
    records: list[ResolutionRecord], broker: Broker
) -> dict[int, list[float]]:
    """Embed a block's texts locally; empty dict if embeddings unavailable.

    Embeddings help fuzzy free-text matching, but for short structured keys
    (an ID/code) they are pure cost — and noise: two adjacent IDs embed to
    near-identical vectors (cosine ~1.0), spuriously inflating similarity into
    the adjudication band. Embedding thousands of records is also the dominant
    wall-clock cost at scale. So skip them when the block's text is short and
    fall back to string-only scoring, which is faster and more accurate here.
    """
    min_chars = int(_threshold("ARYX_ER_EMBED_MIN_CHARS", 40))
    if max((len(r.text) for r in records), default=0) < min_chars:
        return {}
    try:
        vectors = broker.embed([r.text for r in records])
    except Exception:  # embeddings are optional — fall back to string-only  # noqa: BLE001
        vectors = []
    return {r.record_id: v for r, v in zip(records, vectors)} if vectors else {}


def _route_decision(
    left: ResolutionRecord, right: ResolutionRecord, score: float,
    broker: Broker, thresholds: tuple[float, float, float],
    adj_budget: list[int] | None = None,
) -> tuple[str, float | None, str | None]:
    """Pure threshold routing for one scored pair — no union/review side
    effects, so both the in-memory resolver (``_route_pair`` below) and the
    chunked resolver (``resolution/chunked.py``) share one threshold
    implementation instead of drifting (the chunked path used to hard-code
    only the auto-merge cutoff and silently drop every other pair).

    ``adj_budget`` is a one-element mutable counter of remaining LLM
    adjudications for the run; decremented here when an LLM call is made.

    Returns:
        (action, llm_verdict, llm_reason). ``action`` is one of "merge"
        (score alone clears AUTO_MERGE), "auto_llm" (LLM rescore cleared
        AUTO_MERGE), "auto_reject" (DEC-010: confident LLM non-match), or
        "pending" (needs human review).
    """
    auto, rev, reject = thresholds
    if score >= auto:
        return "merge", None, None
    if score < rev:
        return "pending", None, None
    if adj_budget is not None and adj_budget[0] <= 0:
        return "pending", None, "adjudication budget exhausted"
    if adj_budget is not None:
        adj_budget[0] -= 1
    try:
        rescored = adjudicate(left, right, broker)
    except Exception as exc:  # noqa: BLE001 — LLM down -> human decides
        # The raw exception (network error, malformed provider JSON, etc.)
        # is for the log, not the reviewer — it's an internal failure
        # detail, not something that helps a human decide the pair.
        logger.warning("adjudication failed, queueing for human: %s", exc)
        return "pending", None, "llm unavailable — queued for human review"
    if rescored >= auto:
        return "auto_llm", rescored, "llm adjudication"
    if rescored < reject:
        # The LLM already gave a confident verdict here — "not the same
        # thing" — so asking a human to re-confirm it adds no value.
        # Distinct status from "rejected" (DEC-010) so the human/LLM
        # agreement stat isn't credited with a decision no human actually
        # made, same reason auto_llm is split from a human's "approved".
        return "auto_reject", rescored, "llm rescore below reject threshold"
    return "pending", rescored, "llm rescore below auto-merge threshold"


def _route_pair(left: ResolutionRecord, right: ResolutionRecord, score: float,
                broker: Broker, union: UnionFind,
                review: ReviewSink | None,
                adj_budget: list[int] | None = None,
                thresholds: tuple[float, float, float] | None = None) -> None:
    """Apply the four-way threshold routing to one scored pair.

    ``thresholds`` is the pre-read (auto, review, auto_reject) triple. This
    runs once per scored pair, so re-reading os.environ here is pure
    overhead; the caller reads them once. Omitting it keeps the original
    behaviour.
    """
    if thresholds is None:
        thresholds = (_threshold("ARYX_ER_AUTO_MERGE", 0.95),
                      _threshold("ARYX_ER_REVIEW", 0.80),
                      _threshold("ARYX_ER_AUTO_REJECT", 0.05))
    action, llm_verdict, llm_reason = _route_decision(
        left, right, score, broker, thresholds, adj_budget)
    if action in ("merge", "auto_llm"):
        union.union(left.record_id, right.record_id)
    if action == "merge":
        return
    if review is not None:
        review.offer(left, right, score, llm_verdict=llm_verdict,
                     llm_reason=llm_reason, status=action)


def _materialize(member_ids: list[int], by_id: dict[int, ResolutionRecord],
                 pair_scores: dict[tuple[int, int], float],
                 ontology_type: str,
                 policy: SurvivorshipPolicy | None,
                 edge_index: dict[int, list[tuple[int, float]]] | None = None,
                 adjudicate_threshold: float | None = None) -> ResolvedEntity:
    """Build one golden-record entity from a cluster's members.

    ``edge_index`` and ``adjudicate_threshold`` are hoisted out of this function
    because it runs once per cluster: the index would otherwise be rebuilt (or
    the full pair dict rescanned) and the env var re-read every time. Both
    default to None so any existing caller keeps the original behaviour.
    """
    if adjudicate_threshold is None:
        adjudicate_threshold = _threshold("ARYX_ER_REVIEW", 0.80)

    records_in = [by_id[mid] for mid in member_ids]
    if policy is not None:
        members = [{"payload": r.payload, "record_id": r.record_id,
                    "source_system": r.source_system,
                    "cleaned_at": r.cleaned_at} for r in records_in]
        merged, provenance, conflicts = golden_record_with_policy(members, policy)
    else:
        merged = golden_record_weighted(
            [r.payload for r in records_in], member_ids, pair_scores,
            edge_index=edge_index)
        provenance = merged.pop("_provenance", None)
        conflicts = None

    if edge_index is None:
        edges = cluster_edges(member_ids, pair_scores, adjudicate_threshold)
    else:
        edges = cluster_edges_indexed(member_ids, edge_index, adjudicate_threshold)

    return ResolvedEntity(
        ontology_type=ontology_type, attributes=merged,
        confidence=cluster_confidence(edges, len(member_ids)),
        provenance=provenance, conflicts=conflicts or None,
    )


def resolve(
    records: list[ResolutionRecord],
    broker: Broker,
    ontology_type: str,
    policy: SurvivorshipPolicy | None = None,
    review: ReviewSink | None = None,
) -> list[tuple[ResolvedEntity, list[EntityMember]]]:
    """Resolve records into canonical entities via the funnel.

    Args:
        records: Landed records prepared for matching.
        broker: Model broker (embeddings local, adjudication frontier).
        ontology_type: Canonical type these records resolve into.
        policy: Optional survivorship policy (G3); weighted merge when None.
        review: Optional adjudication queue sink (G10); band pairs are queued.

    Returns:
        (entity, members) pairs, one per cluster.
    """
    by_id = {r.record_id: r for r in records}
    union = UnionFind()
    pair_scores: dict[tuple[int, int], float] = {}
    # MultiKeyBlocker puts each record in every block whose key it produces
    # (prefix, token-set, Soundex) — good for recall, but it means the same
    # two records can co-occur in more than one block. Without this guard,
    # such a pair gets scored and offered to adjudication once per shared
    # key family instead of once. Sorted so the same pair is recognized
    # regardless of which side lands at the lower list index in each block.
    seen_pairs: set[tuple[int, int]] = set()
    for record in records:
        union.add(record.record_id)

    # Read once: these are constant for the run and _route_pair is called for
    # every scored pair.
    thresholds = (
        _threshold("ARYX_ER_AUTO_MERGE", 0.95),
        _threshold("ARYX_ER_REVIEW", 0.80),
        _threshold("ARYX_ER_AUTO_REJECT", 0.05),
    )

    # Cap total LLM adjudications per run. Each frontier call on a local model
    # costs 20-60s, and short/embedding-similar keys can push thousands of
    # pairs into the adjudication band — so per-pair LLM adjudication simply
    # doesn't scale on a laptop. Default 5: a bounded per-run cost, not
    # unlimited spend, but enough that genuinely ambiguous pairs get an LLM
    # opinion by default instead of skipping straight to human review. Set
    # ARYX_ER_MAX_ADJUDICATIONS=0 to disable LLM adjudication entirely.
    initial_adj_budget = max(0, int(_threshold("ARYX_ER_MAX_ADJUDICATIONS", 5)))
    adj_budget = [initial_adj_budget]

    for group in block(records, max_block_size=get_settings().max_block_size).values():
        embeddings = _block_embeddings(group, broker)
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                left, right = group[i], group[j]
                pair_key = (min(left.record_id, right.record_id),
                            max(left.record_id, right.record_id))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                score = score_pair(left.text, right.text,
                                   embeddings.get(left.record_id),
                                   embeddings.get(right.record_id))
                pair_scores[(left.record_id, right.record_id)] = score
                _route_pair(left, right, score, broker, union, review,
                            adj_budget, thresholds)
    if initial_adj_budget > 0 and adj_budget[0] <= 0:
        logger.warning("adjudication budget exhausted — remaining band pairs "
                       "queued for review, not auto-merged")
    elif initial_adj_budget == 0:
        logger.info("adjudication budget not configured (ARYX_ER_MAX_ADJUDICATIONS=0); "
                    "band pairs queued for human review")

    # Invert pair_scores ONCE for the whole materialisation pass. Every cluster
    # and every record then does an O(degree) lookup instead of a full scan.
    clusters = union.groups()
    edge_index = build_edge_index(pair_scores)
    logger.info("materialising clusters=%d pairs=%d indexed_records=%d",
                len(clusters), len(pair_scores), len(edge_index))

    results = [
        (_materialize(member_ids, by_id, pair_scores, ontology_type, policy,
                      edge_index=edge_index,
                      adjudicate_threshold=thresholds[1]),
         [EntityMember(landed_record_id=mid) for mid in member_ids])
        for member_ids in clusters.values()
    ]
    logger.info("resolved records=%d entities=%d", len(records), len(results))
    return results

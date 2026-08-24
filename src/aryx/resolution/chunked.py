"""Chunked block-wise entity resolution (G1): memory bound = largest block.

Three streaming passes over a persistent ChunkBackend:
  1. key pass     — stream records, persist (block_key, record_id) rows
  2. score pass   — per block: load ONLY that block's records, score pairs,
                    persist match edges, mark block done (resume granularity)
  3. cluster pass — load edges (edges << records), UnionFind in memory,
                    materialize one golden-record entity per component

A crashed run resumes from the first block without a done marker; passes 1
and 3 are idempotent (pass 1 skips when keys already exist for the run).
The in-memory ``resolve()`` stays the fast path for runs under
ARYX_ER_CHUNK_THRESHOLD (default 100K records).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator

from aryx.broker import Broker
from aryx.models import EntityMember, ResolutionRecord, ResolvedEntity
from aryx.resolution.blocking import _keys_for
from aryx.resolution.chunk_backend import ChunkBackend
from aryx.resolution.classical import score_pair
from aryx.resolution.cluster import UnionFind
from aryx.resolution.review_queue import ReviewSink
from aryx.resolution.run import _materialize, _route_decision, _threshold
from aryx.resolution.survivorship import SurvivorshipPolicy

logger = logging.getLogger(__name__)

MAX_BLOCK = 5000


def _key_pass(run_id: int, records: Iterable[ResolutionRecord],
              backend: ChunkBackend) -> None:
    """Pass 1: persist (block_key, record_id) rows; skipped on resume."""
    if backend.has_keys(run_id):
        logger.info("key pass skipped (resume) run=%s", run_id)
        return
    batch: list[tuple[str, int]] = []
    for record in records:
        batch.extend((key, record.record_id) for key in _keys_for(record.text))
        if len(batch) >= 10_000:
            backend.add_members(run_id, batch)
            batch = []
    if batch:
        backend.add_members(run_id, batch)


def _score_pass(run_id: int, backend: ChunkBackend,
                broker: Broker | None = None,
                review: ReviewSink | None = None,
                adj_budget: list[int] | None = None) -> None:
    """Pass 2: score each not-yet-done block; auto-merge edges persist.

    Without ``broker``, a pair below AUTO_MERGE is simply dropped (no human
    queue, no LLM). With ``broker``, every non-auto-merge pair routes through
    the same ``_route_decision`` the in-memory resolver uses (DEC-009/010) —
    an LLM-confirmed match adds an edge like a pure-score auto-merge, and
    everything else reaches ``review`` instead of being discarded.
    """
    thresholds = (
        _threshold("ARYX_ER_AUTO_MERGE", 0.95),
        _threshold("ARYX_ER_REVIEW", 0.80),
        _threshold("ARYX_ER_AUTO_REJECT", 0.05),
    )
    for key in backend.todo_blocks(run_id):
        ids = backend.block_record_ids(run_id, key)
        if len(ids) > MAX_BLOCK:
            logger.warning("block %r has %d members > %d — skipped",
                           key, len(ids), MAX_BLOCK)
            backend.mark_done(run_id, key)
            continue
        members = backend.load_records(ids)
        edges = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left, right = members[i], members[j]
                score = score_pair(left.text, right.text)
                if score >= thresholds[0]:
                    edges.append((left.record_id, right.record_id, score))
                elif broker is not None:
                    action, llm_verdict, llm_reason = _route_decision(
                        left, right, score, broker, thresholds, adj_budget)
                    if action == "auto_llm":
                        edges.append((left.record_id, right.record_id,
                                     llm_verdict if llm_verdict is not None else score))
                    elif review is not None:
                        review.offer(left, right, score, llm_verdict=llm_verdict,
                                     llm_reason=llm_reason, status=action)
        if edges:
            backend.add_edges(run_id, edges)
        backend.mark_done(run_id, key)


def _cluster_pass(
    run_id: int, backend: ChunkBackend, all_ids: list[int],
    ontology_type: str, policy: SurvivorshipPolicy | None,
) -> Iterator[tuple[ResolvedEntity, list[EntityMember]]]:
    """Pass 3: connected components over edges; stream entities out."""
    union = UnionFind()
    for rid in all_ids:
        union.add(rid)
    pair_scores: dict[tuple[int, int], float] = {}
    for left, right, score in backend.edges(run_id):
        union.add(left)
        union.add(right)
        union.union(left, right)
        pair_scores[(left, right)] = score
    for member_ids in union.groups().values():
        records_in = backend.load_records(member_ids)
        by_id = {r.record_id: r for r in records_in}
        entity = _materialize(member_ids, by_id, pair_scores,
                              ontology_type, policy)
        yield entity, [EntityMember(landed_record_id=m) for m in member_ids]


def resolve_chunked(
    run_id: int,
    records: Iterable[ResolutionRecord],
    all_record_ids: list[int],
    backend: ChunkBackend,
    ontology_type: str,
    policy: SurvivorshipPolicy | None = None,
    broker: Broker | None = None,
    review: ReviewSink | None = None,
) -> Iterator[tuple[ResolvedEntity, list[EntityMember]]]:
    """Resolve a run block-wise with crash-resume via the backend.

    Args:
        run_id: The run being resolved (keys/edges/done markers scope to it).
        records: Streaming iterable of the run's records (key pass only).
        all_record_ids: Every record id in the run (singleton clusters).
        backend: Persistent chunk state (Postgres in production).
        ontology_type: Canonical type the records resolve into.
        policy: Optional survivorship policy (G3).
        broker: Model broker for the middle band; omitted -> those pairs drop.
        review: Adjudication queue sink (G10); ignored without ``broker``.

    Yields:
        (entity, members) per cluster — callers persist and release each.
    """
    adj_budget = ([max(0, int(_threshold("ARYX_ER_MAX_ADJUDICATIONS", 5)))]
                 if broker is not None else None)
    _key_pass(run_id, records, backend)
    _score_pass(run_id, backend, broker=broker, review=review, adj_budget=adj_budget)
    yield from _cluster_pass(run_id, backend, all_record_ids,
                             ontology_type, policy)

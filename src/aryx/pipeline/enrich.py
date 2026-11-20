"""Post-resolution enrichment helpers: the relate stage."""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import combinations_with_replacement, islice, product

from aryx.broker import Broker
from aryx.envnum import env_number
from aryx.models import Relationship
from aryx.relationships import infer_relationship
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)

# Gemini answers one pair in ~8 s; asking several at once keeps the step in
# minutes. Both are overridable for a slower / rate-limited provider.
_WORKERS = int(env_number("ARYX_RELATE_WORKERS", 6, int, minimum=1))
_BUDGET_S = float(env_number("ARYX_RELATE_BUDGET_S", 300.0, float, minimum=1))


def _candidate_pairs(
    entities: list[tuple[int, str, dict]],
    existing: list[tuple[int, int, str]],
    max_pairs: int,
) -> list[tuple[tuple[int, str, dict], tuple[int, str, dict]]]:
    """Entity pairs worth asking the model about, at most ``max_pairs``.

    * a pair of TYPES that already has an edge (e.g. from a foreign-key column)
      is skipped — the model would only re-derive a link we already have;
    * the rest are sampled across type pairs, so every kind of link gets a
      look instead of the first entity being compared with everything.
    """
    by_type: dict[str, list[tuple[int, str, dict]]] = {}
    type_of: dict[int, str] = {}
    for ent in entities:
        by_type.setdefault(ent[1], []).append(ent)
        type_of[ent[0]] = ent[1]
    linked_types = {
        frozenset((type_of[a], type_of[b])) for a, b, _ in existing
        if a in type_of and b in type_of
    }
    type_pairs = [(a, b) for a, b in combinations_with_replacement(sorted(by_type), 2)
                  if frozenset((a, b)) not in linked_types]
    if not type_pairs or max_pairs <= 0:
        return []
    per_pair = max(1, max_pairs // len(type_pairs))
    buckets: list[list] = []
    for ta, tb in type_pairs:
        pairs = ((x, y) for x, y in product(by_type[ta], by_type[tb])
                 if x[0] < y[0] or ta != tb)
        buckets.append(list(islice((p for p in pairs if p[0][0] != p[1][0]), per_pair)))
    out: list = []
    for rank in range(per_pair):          # round-robin: one per type pair at a time
        for bucket in buckets:
            if rank < len(bucket) and len(out) < max_pairs:
                out.append(bucket[rank])
    return out


def _relate(store: EntityStore, broker: Broker, max_pairs: int) -> int:
    """Infer relationships over candidate entity pairs (frontier tier).

    Same step as before — the model judges each candidate pair, capped at
    ``max_pairs`` — but the pairs are chosen across entity types, pairs of
    types already linked deterministically are skipped, several pairs are
    asked at once, and one failed answer (timeout, bad JSON) costs that pair
    only. The step also stops once ``ARYX_RELATE_BUDGET_S`` has passed and
    keeps what it found, so a slow provider cannot hold the job for an hour.
    """
    entities = store.list_entities()
    candidates = _candidate_pairs(entities, store.list_relationships(), max_pairs)
    rels: list[Relationship] = []
    failed = 0
    started = time.monotonic()

    def ask(pair):
        left, right = pair
        return left, right, infer_relationship(left[2], right[2], broker)

    pool = ThreadPoolExecutor(max_workers=max(1, _WORKERS))
    try:
        todo = iter(candidates)
        running: set = set()
        stopped = False
        while True:
            while not stopped and len(running) < max(1, _WORKERS):
                pair = next(todo, None)
                if pair is None:
                    break
                running.add(pool.submit(ask, pair))
            if not running:
                break
            done, running = wait(running, timeout=5, return_when=FIRST_COMPLETED)
            for fut in done:
                try:
                    left, right, (name, conf) = fut.result()
                except Exception as exc:  # noqa: BLE001 — this pair only
                    failed += 1
                    logger.warning("relate: pair skipped (%s: %.120s)",
                                   type(exc).__name__, str(exc))
                    continue
                if name:
                    rels.append(Relationship(
                        source_entity_id=left[0], target_entity_id=right[0],
                        name=name, confidence=conf))
            if not stopped and time.monotonic() - started > _BUDGET_S:
                stopped = True
                logger.warning("relate: time budget %.0fs reached — keeping %d "
                               "relationship(s) found so far", _BUDGET_S, len(rels))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    store.save_relationships(rels)
    logger.info("relate: %d candidate pair(s), %d relationship(s), %d failed, %.0fs",
                len(candidates), len(rels), failed, time.monotonic() - started)
    return len(rels)

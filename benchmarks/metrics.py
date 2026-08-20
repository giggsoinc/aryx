"""Core ER evaluation: runs the REAL funnel stages and computes pairwise metrics.

Imports blocking and scoring from aryx.resolution — never reimplements them.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Callable

from aryx.models import ResolutionRecord
from aryx.resolution.blocking import MultiKeyBlocker
from aryx.resolution.classical import block_key, score_pair

AUTO_MERGE = 0.92
ADJUDICATE_FROM = 0.90
REJECT = 0.60

BlockerFn = Callable[[list[ResolutionRecord]], dict[str, list[ResolutionRecord]]]


def block_multi(recs: list[ResolutionRecord]) -> dict[str, list[ResolutionRecord]]:
    """G2 multi-key blocker (prefix + token-set + Soundex)."""
    return MultiKeyBlocker().block(recs)


def block_legacy(recs: list[ResolutionRecord]) -> dict[str, list[ResolutionRecord]]:
    """Original single-prefix blocking (pre-G2), for before/after comparison."""
    blocks: dict[str, list[ResolutionRecord]] = {}
    for r in recs:
        blocks.setdefault(block_key(r.text), []).append(r)
    return blocks


def evaluate(
    recs: list[ResolutionRecord],
    true_pairs: set[frozenset],
    id_map: dict[int, str],
    blocker_fn: BlockerFn,
    auto_merge: float = AUTO_MERGE,
    adjudicate_from: float = ADJUDICATE_FROM,
    adjudicate_mode: str = "always_reject",
) -> dict[str, Any]:
    """Run block -> score -> threshold -> cluster and return a metrics dict.

    Args:
        adjudicate_mode: 'always_accept' or 'always_reject' — mocked LLM tiers
            that bracket the adjudicator's possible contribution.
    """
    t0 = time.perf_counter()
    blocks = blocker_fn(recs)

    blocked_pairs: set[frozenset] = set()
    for members in blocks.values():
        ids = [m.record_id for m in members]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                blocked_pairs.add(frozenset([id_map[ids[i]], id_map[ids[j]]]))
    blocking_recall = (
        len(true_pairs & blocked_pairs) / len(true_pairs) if true_pairs else 0.0
    )

    union: dict[int, int] = {r.record_id: r.record_id for r in recs}

    def find(x: int) -> int:
        """Find set representative with path halving."""
        while union[x] != x:
            union[x] = union[union[x]]
            x = union[x]
        return x

    candidate_count = 0
    for members in blocks.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                candidate_count += 1
                score = score_pair(a.text, b.text)
                accept_band = (adjudicate_mode == "always_accept"
                               and score >= adjudicate_from)
                if score >= auto_merge or accept_band:
                    union[find(a.record_id)] = find(b.record_id)

    clusters: dict[int, list[int]] = defaultdict(list)
    for r in recs:
        clusters[find(r.record_id)].append(r.record_id)

    predicted_pairs: set[frozenset] = set()
    for ids in clusters.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                predicted_pairs.add(frozenset([id_map[ids[i]], id_map[ids[j]]]))

    tp = len(predicted_pairs & true_pairs)
    fp = len(predicted_pairs) - tp
    fn = len(true_pairs) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)

    return {
        "precision": precision, "recall": recall, "f1": f1,
        "blocking_recall": blocking_recall,
        "candidate_pairs": candidate_count,
        "predicted_pairs": len(predicted_pairs),
        "true_pairs": len(true_pairs), "tp": tp,
        "wall_time": time.perf_counter() - t0,
    }

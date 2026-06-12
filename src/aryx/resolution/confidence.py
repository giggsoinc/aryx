"""Real cluster confidence from merge-edge scores (G7).

A cluster is as trustworthy as its weakest merge: confidence = MINIMUM
merge-edge score across the cluster's spanning structure — min, not mean,
so one shaky 0.61 merge can't hide behind three 0.95s.

Human-approved adjudication edges count as 0.99: reviewed beats inferred,
but never claims 1.0. Nothing gets 1.0 — certainty isn't on offer.
"""
from __future__ import annotations

HUMAN_EDGE_SCORE = 0.99
SINGLETON_CONFIDENCE = 0.5  # uncontested, also unconfirmed — honest prior
_FLOOR, _CEIL = 0.5, 0.99


def cluster_confidence(edges: list[float], size: int) -> float:
    """Confidence for one resolved cluster.

    Args:
        edges: Merge-edge scores that glued this cluster together (within-
            cluster pair scores at/above the merge threshold; human-approved
            edges passed in as HUMAN_EDGE_SCORE).
        size: Number of member records in the cluster.

    Returns:
        SINGLETON_CONFIDENCE for size 1; otherwise the minimum edge score
        clamped to [0.5, 0.99].
    """
    if size <= 1:
        return SINGLETON_CONFIDENCE
    if not edges:
        # Multi-member with no recorded edges (legacy data) — floor it.
        return _FLOOR
    return max(_FLOOR, min(_CEIL, min(edges)))


def cluster_edges(member_ids: list[int],
                  pair_scores: dict[tuple[int, int], float],
                  threshold: float) -> list[float]:
    """Extract the within-cluster merge-edge scores from scored pairs.

    Args:
        member_ids: The cluster's record ids.
        pair_scores: All scored pairs from the funnel.
        threshold: Minimum score that constituted a merge edge.

    Returns:
        Scores of pairs inside the cluster at/above the threshold.
    """
    members = set(member_ids)
    return [score for (left, right), score in pair_scores.items()
            if left in members and right in members and score >= threshold]

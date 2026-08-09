"""Real cluster confidence from merge-edge scores (G7).

A cluster is as trustworthy as its weakest merge: confidence = MINIMUM
merge-edge score across the cluster's spanning structure — min, not mean,
so one shaky 0.61 merge can't hide behind three 0.95s.

Human-approved adjudication edges count as 0.99: reviewed beats inferred,
but never claims 1.0. Nothing gets 1.0 — certainty isn't on offer.
"""

from __future__ import annotations

from collections import defaultdict

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


def build_edge_index(
    pair_scores: dict[tuple[int, int], float],
) -> dict[int, list[tuple[int, float]]]:
    """Invert pair_scores once into {record_id: [(other_id, score), ...]}.

    Why this exists
    ---------------
    ``cluster_edges`` and ``survivor.survivors`` both need "the scored pairs
    that touch record X", and both used to answer that by scanning the whole
    ``pair_scores`` dict on every call. Since both are called once per cluster
    (and ``survivors`` once per *record*), total work grew as
    ``records x total_pairs`` — hours on a few thousand records.

    Building this index costs one pass, after which every lookup is O(degree).
    Build it ONCE per resolution run, before the cluster loop, and thread it
    through; never build it inside the loop.

    Deliberately NOT thresholded: ``survivors`` weights by every score it can
    see, while ``cluster_edges_indexed`` applies its own threshold. Filtering
    here would silently change survivorship weights.

    Each pair is stored under BOTH endpoints, so callers that iterate a set of
    members will encounter each edge twice — de-duplicate if the count matters
    (``cluster_edges_indexed`` does).
    """
    index: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for (left, right), score in pair_scores.items():
        index[left].append((right, score))
        if right != left:
            index[right].append((left, score))
    return index


def cluster_edges(member_ids: list[int],
                  pair_scores: dict[tuple[int, int], float],
                  threshold: float) -> list[float]:
    """Extract the within-cluster merge-edge scores from scored pairs.

    Scans all of ``pair_scores``. Kept for callers that have no index; prefer
    ``cluster_edges_indexed`` on any hot path — see ``build_edge_index``.

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


def cluster_edges_indexed(member_ids: list[int],
                          edge_index: dict[int, list[tuple[int, float]]],
                          threshold: float) -> list[float]:
    """Indexed equivalent of ``cluster_edges`` — same multiset of scores.

    Touches only the members' own edges instead of the full pair dict. Each
    undirected edge is returned once: the index holds every pair under both
    endpoints, so a ``seen`` set keeps the result identical in length to
    ``cluster_edges`` (``cluster_confidence`` takes the min, but callers that
    count or average edges would otherwise double-count).

    Args:
        member_ids: The cluster's record ids.
        edge_index: Output of ``build_edge_index`` for this run's pair_scores.
        threshold: Minimum score that constituted a merge edge.

    Returns:
        Scores of pairs inside the cluster at/above the threshold.
    """
    members = set(member_ids)
    seen: set[tuple[int, int]] = set()
    out: list[float] = []
    for member in members:
        for other, score in edge_index.get(member, ()):
            if other not in members or score < threshold:
                continue
            key = (member, other) if member <= other else (other, member)
            if key in seen:
                continue
            seen.add(key)
            out.append(score)
    return out

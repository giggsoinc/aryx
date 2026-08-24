"""G7: cluster confidence — weakest link, clamps, singleton, human edges."""
from __future__ import annotations

from aryx.resolution.confidence import (HUMAN_EDGE_SCORE,
                                        SINGLETON_CONFIDENCE,
                                        build_edge_index, cluster_confidence,
                                        cluster_edges, cluster_edges_indexed)


def test_weakest_link_wins() -> None:
    """One shaky 0.61 merge can't hide behind three 0.95s."""
    assert cluster_confidence([0.95, 0.95, 0.95, 0.61], size=5) == 0.61


def test_singleton_prior() -> None:
    """Uncontested but unconfirmed: honest 0.5."""
    assert cluster_confidence([], size=1) == SINGLETON_CONFIDENCE


def test_clamp_ceiling_no_certainty() -> None:
    """Nothing reaches 1.0 — even perfect string scores."""
    assert cluster_confidence([1.0, 1.0], size=3) == 0.99


def test_clamp_floor() -> None:
    """Edges below the floor clamp to 0.5."""
    assert cluster_confidence([0.3], size=2) == 0.5


def test_human_edge_boost() -> None:
    """A human-approved edge counts as 0.99 — reviewed beats inferred."""
    assert cluster_confidence([HUMAN_EDGE_SCORE], size=2) == 0.99


def test_multi_member_no_edges_floors() -> None:
    """Legacy clusters without recorded edges get the floor, not 1.0."""
    assert cluster_confidence([], size=4) == 0.5


def test_cluster_edges_filters_to_members_and_threshold() -> None:
    """Only within-cluster pairs at/above the merge threshold count."""
    scores = {(1, 2): 0.95, (2, 3): 0.91, (1, 9): 0.99, (2, 4): 0.50}
    edges = cluster_edges([1, 2, 3], scores, threshold=0.90)
    assert sorted(edges) == [0.91, 0.95]


def test_cluster_edges_excludes_an_auto_rejected_pair() -> None:
    """Regression (DEC-010 gap): a pair explicitly routed as a non-match
    must never count as a merge-edge, even if both records land in the
    same cluster via a third pair's transitive closure. Reproduces the
    exact case found in review: A-C auto-merges, B-C is LLM-approved, A-B
    was LLM auto-rejected (never unioned) — but A/B/C still end up in one
    cluster via the chain, and A-B's raw 0.90 must not be an eligible edge."""
    pair_scores = {(1, 3): 0.96, (2, 3): 0.85, (1, 2): 0.90}
    edges = cluster_edges([1, 2, 3], pair_scores, threshold=0.80,
                          excluded={(1, 2)})
    assert sorted(edges) == [0.85, 0.96]


def test_cluster_edges_excluded_checks_both_orders() -> None:
    """The excluded set may be recorded in either (left, right) order —
    the pair itself is undirected, so both must be checked."""
    pair_scores = {(1, 2): 0.90, (2, 3): 0.85}
    assert cluster_edges([1, 2, 3], pair_scores, threshold=0.80,
                         excluded={(2, 1)}) == [0.85]


def test_cluster_edges_indexed_excludes_an_auto_rejected_pair() -> None:
    """Same regression as above, for the indexed variant every real
    resolution run actually uses on the hot path."""
    pair_scores = {(1, 3): 0.96, (2, 3): 0.85, (1, 2): 0.90}
    index = build_edge_index(pair_scores)
    edges = cluster_edges_indexed([1, 2, 3], index, threshold=0.80,
                                  excluded={(1, 2)})
    assert sorted(edges) == [0.85, 0.96]


def test_cluster_edges_indexed_without_excluded_is_unchanged() -> None:
    """Omitting excluded (the default) keeps prior behaviour exactly."""
    pair_scores = {(1, 2): 0.95, (2, 3): 0.91}
    index = build_edge_index(pair_scores)
    assert sorted(cluster_edges_indexed([1, 2, 3], index, threshold=0.90)) == [0.91, 0.95]


def test_merging_logic_untouched() -> None:
    """Confidence is metadata: cluster sets identical before/after G7.

    The funnel fixture from test_resolution_funnel produces the same
    clusters regardless of the confidence calculation — asserted here by
    running the same merge logic and only inspecting membership.
    """
    from funnel_helpers import rec, run_funnel
    recs = [rec(0, "zenith polymer corp"), rec(1, "zenith polymer corp"),
            rec(2, "atlas forge ltd")]
    groups = run_funnel(recs)
    clusters = sorted(sorted(v) for v in groups.values())
    assert clusters == [[0, 1], [2]]

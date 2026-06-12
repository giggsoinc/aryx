"""G7: cluster confidence — weakest link, clamps, singleton, human edges."""
from __future__ import annotations

from aryx.resolution.confidence import (HUMAN_EDGE_SCORE,
                                        SINGLETON_CONFIDENCE,
                                        cluster_confidence, cluster_edges)


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

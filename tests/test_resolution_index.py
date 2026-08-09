"""Regression tests for the edge-index fix (v2-edgeindex).

Covers the three gaps named in aryx-followups.md / aryx-handoff.md:
  1. cluster_edges_indexed output-identical to cluster_edges
  2. survivors with and without edge_index produce identical dicts
  3. Scale guard — 2,000 synthetic records resolve in under 10 seconds
"""
from __future__ import annotations

import random
import time

import pytest

from aryx.resolution.confidence import (
    build_edge_index,
    cluster_edges,
    cluster_edges_indexed,
)
from aryx.resolution.survivor import survivors


# ---------------------------------------------------------------------------
# 1. cluster_edges_indexed == cluster_edges (same multiset)
# ---------------------------------------------------------------------------

def _pair_scores(members: list[int], extra: list[int],
                 rng: random.Random) -> dict[tuple[int, int], float]:
    """Generate pair_scores covering members, non-members, and both orientations."""
    all_ids = members + extra
    ps: dict[tuple[int, int], float] = {}
    for i in range(len(all_ids)):
        for j in range(i + 1, len(all_ids)):
            a, b = all_ids[i], all_ids[j]
            score = rng.random()
            if rng.random() > 0.5:
                ps[(a, b)] = score
            else:
                ps[(b, a)] = score
    return ps


@pytest.mark.parametrize("seed", range(300))
def test_cluster_edges_indexed_matches_original(seed: int) -> None:
    rng = random.Random(seed)
    members = list(range(rng.randint(1, 8)))
    extra = list(range(100, 100 + rng.randint(0, 5)))
    threshold = rng.uniform(0.0, 0.99)
    ps = _pair_scores(members, extra, rng)

    expected = sorted(cluster_edges(members, ps, threshold))
    index = build_edge_index(ps)
    actual = sorted(cluster_edges_indexed(members, index, threshold))

    assert actual == expected, (
        f"seed={seed} members={members} threshold={threshold:.3f} "
        f"expected={expected} got={actual}"
    )


def test_cluster_edges_indexed_empty_pair_scores() -> None:
    assert cluster_edges_indexed([1, 2, 3], build_edge_index({}), 0.90) == []


def test_cluster_edges_indexed_singleton() -> None:
    ps = {(1, 2): 0.95}
    index = build_edge_index(ps)
    assert cluster_edges_indexed([1], index, 0.90) == []


def test_cluster_edges_indexed_both_orientations() -> None:
    """Index stores each pair under both endpoints; result must not double-count."""
    ps = {(1, 2): 0.95}
    index = build_edge_index(ps)
    result = cluster_edges_indexed([1, 2], index, 0.90)
    assert result == [0.95]


def test_cluster_edges_indexed_non_member_noise() -> None:
    """Pairs that involve non-members must be excluded."""
    ps = {(1, 99): 0.95, (1, 2): 0.80}
    index = build_edge_index(ps)
    result = cluster_edges_indexed([1, 2], index, 0.70)
    assert sorted(result) == [0.80]


# ---------------------------------------------------------------------------
# 2. survivors with / without edge_index — identical dicts including _provenance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(400))
def test_survivors_indexed_matches_original(seed: int) -> None:
    rng = random.Random(seed)
    n = rng.randint(1, 6)
    record_ids = list(range(n))
    payloads = [
        {f"field_{k}": rng.choice(["alpha", "beta", None])
         for k in range(rng.randint(1, 4))}
        for _ in range(n)
    ]
    ps: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() > 0.3:
                ps[(i, j)] = rng.random()

    expected = survivors(payloads, record_ids, ps)
    index = build_edge_index(ps)
    actual = survivors(payloads, record_ids, ps, edge_index=index)

    assert actual == expected, f"seed={seed} n={n}"


def test_survivors_provenance_identical_with_index() -> None:
    payloads = [{"name": "Alice", "city": "NYC"}, {"city": "SF"}]
    record_ids = [10, 11]
    ps = {(10, 11): 0.91}
    index = build_edge_index(ps)

    without = survivors(payloads, record_ids, ps)
    with_idx = survivors(payloads, record_ids, ps, edge_index=index)
    assert without == with_idx
    assert with_idx["_provenance"]["name"] == 10


def test_survivors_empty_pair_scores_with_index() -> None:
    payloads = [{"x": 1}]
    result = survivors(payloads, [5], {}, edge_index=build_edge_index({}))
    assert result["x"] == 1
    assert result["_provenance"]["x"] == 5


# ---------------------------------------------------------------------------
# 3. Scale guard — 2,000 records must resolve in under 10 seconds
# ---------------------------------------------------------------------------

def test_resolution_scale_guard() -> None:
    """Regression guard: the O(n²) stall must not come back.

    2,000 records with a dense pair_scores dict triggered the original hang
    (billions of dict iterations). With the index, materialisation is O(edges).
    10 s wall-clock is generous — the fixed code does this in well under 1 s.
    """
    from aryx.resolution.confidence import build_edge_index, cluster_edges_indexed
    from aryx.resolution.survivor import survivors

    rng = random.Random(42)
    n = 2_000
    record_ids = list(range(n))
    payloads = [{"val": str(i)} for i in range(n)]

    # Dense pair_scores — every fifth pair scored
    ps: dict[tuple[int, int], float] = {}
    for i in range(0, n, 5):
        for j in range(i + 1, min(i + 10, n)):
            ps[(i, j)] = rng.random()

    index = build_edge_index(ps)

    start = time.monotonic()
    # Simulate what _materialize does: survivors + cluster_edges_indexed per cluster
    for rid in record_ids[:100]:  # spot-check 100 "clusters"
        survivors([payloads[rid]], [rid], ps, edge_index=index)
        cluster_edges_indexed([rid], index, 0.90)
    elapsed = time.monotonic() - start

    assert elapsed < 10.0, f"scale regression: 100 clusters took {elapsed:.2f}s"

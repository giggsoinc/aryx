"""Funnel tests for G9: blocking recall, end-to-end clustering, G3 xfail.

UnionFind primitives are covered in test_funnel_unionfind.py.
"""
from __future__ import annotations

import pytest

from aryx.resolution.blocking import MultiKeyBlocker
from aryx.resolution.classical import block_key
from aryx.resolution.cluster import golden_record
from funnel_helpers import rec, run_funnel

_CLUSTER_NAMES = [
    "phoenix zirconium nebula", "neptune rhodium comet",
    "helium quartz vortex", "obsidian tungsten fjord",
    "aurora bismuth delta", "xenon cobalt prism",
    "quasar vanadium echo", "indigo palladium brook",
    "tantalum umber glyph", "ozone chromium shard",
]


def test_multi_key_blocking_recall_on_suffix_variant() -> None:
    """Suffix variants (corp/corporation) must share at least one block."""
    recs = [rec(1, "apex industrial corp"),
            rec(2, "apex industrial corporation")]
    blocks = MultiKeyBlocker().block(recs)
    assert any(len(m) >= 2 for m in blocks.values())


def test_legacy_blocking_pairs_shared_prefix() -> None:
    """Documents legacy behaviour: shared 4-char prefix still pairs."""
    recs = [rec(1, "apex industrial corp"),
            rec(2, "apex industrial corporation")]
    legacy: dict[str, list] = {}
    for r in recs:
        legacy.setdefault(block_key(r.text), []).append(r)
    assert any(len(m) >= 2 for m in legacy.values())


def test_multi_key_better_recall_than_legacy_on_transpositions() -> None:
    """Token-set key pairs word transpositions that prefix blocking misses."""
    recs = [rec(1, "smith john manufacturing"),
            rec(2, "john manufacturing smith")]
    blocks = MultiKeyBlocker().block(recs)
    legacy: dict[str, list] = {}
    for r in recs:
        legacy.setdefault(block_key(r.text), []).append(r)
    assert any(len(m) >= 2 for m in blocks.values())
    assert not any(len(m) >= 2 for m in legacy.values())


def test_funnel_50_record_exact_cluster_membership() -> None:
    """10 clusters x 5 identical records — funnel must group exactly.

    Cluster names share no tokens, prefixes, or Soundex codes, so they never
    co-block and are never scored against each other.
    """
    recs, expected = [], {}
    rid = 0
    for cluster_id, name in enumerate(_CLUSTER_NAMES):
        members = []
        for _ in range(5):
            recs.append(rec(rid, name))
            members.append(rid)
            rid += 1
        expected[cluster_id] = set(members)
    actual = [set(v) for v in run_funnel(recs).values()]
    for exp in expected.values():
        assert exp in actual, f"Expected cluster {exp} missing"


def test_funnel_rejects_dissimilar() -> None:
    """Completely different texts merge into nothing — N singletons."""
    texts = ["alpha zeta prime holdings corp",
             "xenon delta omega systems ltd",
             "gamma sigma epsilon industries"]
    groups = run_funnel([rec(i, t) for i, t in enumerate(texts)])
    assert all(len(v) == 1 for v in groups.values())


def test_funnel_single_record() -> None:
    """One record resolves to one singleton entity."""
    groups = run_funnel([rec(0, "solitary company inc")])
    assert list(groups.values()) == [[0]]


def test_funnel_empty_input() -> None:
    """Empty input produces no clusters."""
    assert run_funnel([]) == {}


@pytest.mark.xfail(
    reason="G3 open: golden_record is order-dependent without weighted merge")
def test_golden_record_order_independent() -> None:
    """Same cluster, two insertion orders, identical golden records.

    With first-non-empty merge, competing non-null values are insertion-order
    dependent. G3 (survivor-smith) fixes this; this xfail flips green then.
    """
    ab = [{"name": "Apex Corp", "city": "LA"},
          {"name": "Apex Corporation", "city": "Los Angeles"}]
    ba = list(reversed(ab))
    assert golden_record(ab) == golden_record(ba)

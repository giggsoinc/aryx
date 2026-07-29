"""Funnel tests for G9: blocking recall, end-to-end clustering, G3 xfail.

UnionFind primitives are covered in test_funnel_unionfind.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aryx.resolution.blocking import MultiKeyBlocker
from aryx.resolution.classical import block_key
from aryx.resolution.cluster import golden_record
from funnel_helpers import rec, run_funnel
from aryx.models import ResolutionRecord
from aryx.resolution.run import resolve

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


def test_exact_key_shortcut_requires_metadata_and_normalizes_keys() -> None:
    """Declared keys can use the fast path, but separator/case variants merge."""
    broker = MagicMock()
    records = [
        ResolutionRecord(record_id=1, text="ACME-123",
                         payload={"record_key": "ACME-123"}, match_keys=["record_key"]),
        ResolutionRecord(record_id=2, text="acme 123",
                         payload={"record_key": "acme 123"}, match_keys=["record_key"]),
    ]
    for i in range(3, 21):
        records.append(ResolutionRecord(
            record_id=i, text=f"ID-{i}",
            payload={"record_key": f"ID-{i}"}, match_keys=["record_key"]))

    results = resolve(records, broker, "Thing")
    clusters = {
        frozenset(m.landed_record_id for m in members)
        for _, members in results
    }

    assert frozenset({1, 2}) in clusters
    assert len(results) == 19


def test_golden_record_order_independent() -> None:
    """Same cluster, two insertion orders, identical golden records.

    Was xfail while G3 was open; flipped green by survivor-smith's policy
    merge — most_complete is deterministic regardless of input order. The
    legacy ``golden_record`` shim stays order-dependent by design.
    """
    from aryx.resolution.golden import golden_record_with_policy
    from aryx.resolution.survivorship import SurvivorshipPolicy
    policy = SurvivorshipPolicy(default_strategy="most_complete")
    ab = [{"payload": {"name": "Apex Corp", "city": "LA"},
           "record_id": 1, "source_system": "a", "cleaned_at": None},
          {"payload": {"name": "Apex Corporation", "city": "Los Angeles",
                       "country": "US"},
           "record_id": 2, "source_system": "b", "cleaned_at": None}]
    merged_ab, _, _ = golden_record_with_policy(ab, policy)
    merged_ba, _, _ = golden_record_with_policy(list(reversed(ab)), policy)
    assert merged_ab == merged_ba

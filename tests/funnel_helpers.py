"""Shared fixtures for the resolution-funnel test suite (G9)."""
from __future__ import annotations

from aryx.models import ResolutionRecord
from aryx.resolution.classical import score_pair
from aryx.resolution.cluster import UnionFind


def rec(rid: int, text: str, payload: dict | None = None) -> ResolutionRecord:
    """Build a minimal ResolutionRecord for funnel tests."""
    return ResolutionRecord(
        record_id=rid,
        text=text,
        payload=payload or {"name": text},
    )


def run_funnel(recs: list[ResolutionRecord],
               blocker_fn=None,
               auto_merge: float = 0.92) -> dict[int, list[int]]:
    """Run block -> score -> auto-merge -> cluster; no broker required.

    Returns:
        {root_id: [member_ids]} clusters from UnionFind.
    """
    if blocker_fn is None:
        from aryx.resolution.classical import block as default_block
        blocker_fn = default_block
    union = UnionFind()
    for r in recs:
        union.add(r.record_id)
    for members in blocker_fn(recs).values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if score_pair(a.text, b.text) >= auto_merge:
                    union.union(a.record_id, b.record_id)
    return union.groups()

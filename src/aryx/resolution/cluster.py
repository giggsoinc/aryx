"""Clustering: union matched pairs into entities and build golden records."""
from __future__ import annotations

from typing import Any


class UnionFind:
    """Disjoint-set over record ids for transitive-closure clustering."""

    def __init__(self) -> None:
        """Start with no elements."""
        self._parent: dict[int, int] = {}

    def add(self, item: int) -> None:
        """Register an element as its own set if unseen."""
        self._parent.setdefault(item, item)

    def find(self, item: int) -> int:
        """Return the set representative, with path compression."""
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: int, right: int) -> None:
        """Merge the sets containing two elements."""
        self._parent[self.find(left)] = self.find(right)

    def groups(self) -> dict[int, list[int]]:
        """Return clusters as {representative: [member ids]}."""
        clusters: dict[int, list[int]] = {}
        for item in self._parent:
            clusters.setdefault(self.find(item), []).append(item)
        return clusters


def golden_record(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge cluster payloads: first non-empty value per key (legacy shim).

    Strips the internal ``_provenance`` key before returning so callers that
    don't expect it are unaffected.
    """
    from aryx.resolution.survivor import survivors
    merged = survivors(payloads, [], {})
    merged.pop("_provenance", None)
    return merged


def golden_record_weighted(
    payloads: list[dict[str, Any]],
    record_ids: list[int],
    pair_scores: dict[tuple[int, int], float],
) -> dict[str, Any]:
    """Confidence-weighted merge with conflict detection and provenance."""
    from aryx.resolution.survivor import survivors
    return survivors(payloads, record_ids, pair_scores)

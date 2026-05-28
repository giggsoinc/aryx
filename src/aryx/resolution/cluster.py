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
    """Merge cluster payloads into one record: first non-empty value per key."""
    merged: dict[str, Any] = {}
    for payload in payloads:
        for key, value in payload.items():
            if key not in merged and value not in (None, "", []):
                merged[key] = value
    return merged

"""UnionFind clustering tests for G9 (transitivity, singletons, compression)."""
from __future__ import annotations

from aryx.resolution.cluster import UnionFind


def test_union_find_transitivity() -> None:
    """union(1,2) + union(2,3) must put 1,2,3 in one cluster."""
    uf = UnionFind()
    for x in [1, 2, 3]:
        uf.add(x)
    uf.union(1, 2)
    uf.union(2, 3)
    roots = list(uf.groups().values())
    assert any(set(members) == {1, 2, 3} for members in roots)


def test_union_find_singleton() -> None:
    """A lone element forms its own cluster."""
    uf = UnionFind()
    uf.add(42)
    assert list(uf.groups().values()) == [[42]]


def test_union_find_empty() -> None:
    """No elements -> no clusters."""
    assert UnionFind().groups() == {}


def test_union_find_no_merge() -> None:
    """Unmerged elements stay separate."""
    uf = UnionFind()
    for x in [10, 20, 30]:
        uf.add(x)
    assert len(uf.groups()) == 3


def test_union_find_path_compression() -> None:
    """A chain of unions resolves every member to one root."""
    uf = UnionFind()
    for x in range(5):
        uf.add(x)
    for i in range(4):
        uf.union(i, i + 1)
    root = uf.find(0)
    for i in range(5):
        assert uf.find(i) == root

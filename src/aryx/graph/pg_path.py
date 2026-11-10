"""Bidirectional shortest-path search over the Postgres graph.

Split out of ``pg_reader`` to keep the reader small. The search only needs a
way to run a named query, so it takes the reader's ``rows`` function instead of
a connection. Behaviour is held to the old reader by the golden file in
``tests/fixtures/graph_golden``: outbound and inbound searches are never mixed,
and a runaway search raises instead of returning "no path".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_MAX_FRONTIER = 100_000

# Runs a named query (workspace already bound) and returns every row.
Rows = Callable[[str, dict[str, Any]], list[tuple]]


class GraphSearchTooLarge(RuntimeError):
    """A shortest-path search outgrew its frontier cap.

    Raised instead of returning "no path": a runaway search is not evidence
    that no path exists.
    """


@dataclass
class _Side:
    """One direction of a bidirectional search."""

    frontier: list[int]
    parent: dict[int, tuple[int, str] | None] = field(default_factory=dict)
    dist: dict[int, int] = field(default_factory=dict)

    @classmethod
    def start(cls, node: int) -> "_Side":
        """A search side that has only seen its root."""
        return cls(frontier=[node], parent={node: None}, dist={node: 0})



def directed_path(rows: Rows, start: int, goal: int, hops: int
                  ) -> list[tuple[int, str | None]] | None:
    """Shortest path along edge direction from start to goal, or None.

    Bidirectional breadth-first search: forward along edges from start,
    backward against edges from goal, always expanding the smaller side one
    full level. Returns ``[(node, edge name into node), ...]``.

    Args:
        rows: Runs a named graph query for the bound workspace.
        start: Entity id the path begins at.
        goal: Entity id the path ends at.
        hops: Maximum number of edges to follow.

    Raises:
        GraphSearchTooLarge: A search level exceeded the frontier cap.
    """
    fwd, bwd = _Side.start(start), _Side.start(goal)
    while fwd.frontier and bwd.frontier and _depth(fwd) + _depth(bwd) < hops:
        forward = len(fwd.frontier) <= len(bwd.frontier)
        side, other = (fwd, bwd) if forward else (bwd, fwd)
        meet = _expand(rows, side, other,
                       "graph_expand_out" if forward else "graph_expand_in")
        if meet is not None:
            return _chain(fwd, bwd, meet, start, goal)
    return None


def _expand(rows: Rows, side: _Side, other: _Side, query: str) -> int | None:
    """Grow ``side`` by one level; return the best meeting node, if any."""
    level = _depth(side) + 1
    nxt: list[int] = []
    for frm, tov, rel in rows(query, {"frontier": side.frontier}):
        if tov not in side.parent:
            side.parent[tov] = (frm, rel)
            side.dist[tov] = level
            nxt.append(tov)
    if len(nxt) > _MAX_FRONTIER:
        raise GraphSearchTooLarge(
            f"shortest-path frontier exceeded {_MAX_FRONTIER} entities")
    side.frontier = nxt
    meets = [n for n in nxt if n in other.parent]
    if not meets:
        return None
    return min(meets, key=lambda n: (side.dist[n] + other.dist[n], n))


def _depth(side: _Side) -> int:
    """How many levels this side has expanded."""
    return max(side.dist.values())


def _chain(fwd: _Side, bwd: _Side, meet: int, start: int, goal: int
           ) -> list[tuple[int, str | None]]:
    """Stitch the two halves into ``[(node, edge name into node), ...]``."""
    head: list[tuple[int, str | None]] = []
    node = meet
    while node != start:
        prev, rel = fwd.parent[node]  # type: ignore[misc]
        head.append((node, rel))
        node = prev
    head.append((start, None))
    head.reverse()
    node = meet
    while node != goal:
        nxt, rel = bwd.parent[node]  # type: ignore[misc]
        head.append((nxt, rel))
        node = nxt
    return head

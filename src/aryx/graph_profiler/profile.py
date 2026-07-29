"""Deterministic graph profiling (C06) — no LLM.

Mirrors the component Procedure:
  1. extract entity types, relationship types, properties, counts
  2. compute permitted graph statistics and bounded paths
  3. identify key paths relevant to objective-linked entities
  4. detect disconnected / sparse regions and missing keys
  5. create a compact graph schema summary
  6. (optional) request business interpretation — off by default
  7. (caller) validate, version, persist

Every verified path is derived from schema edges that actually occur in the
graph, so no node/relationship/path can be invented. Enumeration is bounded by
`max_depth` and a total path cap; anything dropped is reported in `limitations`.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from aryx.graph_profiler.models import (
    GraphProfile,
    GraphQualityFlag,
    SchemaEdge,
    TypeCount,
    VerifiedPath,
)

MAX_PATHS = 50            # cap on returned verified paths
_WALK_BUDGET = 4000       # global cap on path prefixes explored (bounds time)


def _tokens(name: str) -> set[str]:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name or "")
    out = set()
    for tok in re.split(r"[^A-Za-z0-9]+", name.lower()):
        if not tok:
            continue
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        out.add(tok)
    return out


def _objective_types(user_objective: str, types: list[str]) -> set[str]:
    """Types whose name tokens overlap the objective (relevance ranking)."""
    obj = _tokens(user_objective)
    if not obj:
        return set()
    return {t for t in types if _tokens(t) & obj}


def _path_id(path: list[str]) -> str:
    # Include relationship names, not just types, so distinct paths with the
    # same type sequence (A -owns-> B vs A -likes-> B) get distinct ids.
    slug = "_".join(re.sub(r"[^a-z0-9]+", "", seg.lower()) for seg in path)
    return f"path_{slug}"


def _enumerate_paths(adj: dict[str, list[tuple[str, str]]], start: str,
                     max_depth: int, budget: list[int]) -> list[list[str]]:
    """Type-level simple paths from `start`, each hop a real schema edge."""
    results: list[list[str]] = []

    def dfs(node: str, path: list[str], visited: set[str]) -> None:
        if budget[0] <= 0:
            return
        depth = (len(path) - 1) // 2
        if depth >= 1:
            results.append(list(path))
            budget[0] -= 1
        if depth >= max_depth:
            return
        for rel, tgt in adj.get(node, ()):  # deterministic order (sorted adj)
            if budget[0] <= 0:
                return
            if tgt == node:
                # Self-referential schema edge (e.g. Employee reports_to
                # Employee) — a real one-hop path; record it but don't recurse.
                results.append(path + [rel, tgt])
                budget[0] -= 1
                continue
            if tgt in visited:
                continue
            visited.add(tgt)
            path.extend([rel, tgt])
            dfs(tgt, path, visited)
            path.pop()
            path.pop()
            visited.discard(tgt)

    dfs(start, [start], {start})
    return results


def profile_graph(
    normalized: dict[str, Any],
    graph_id: str,
    graph_version: str,
    *,
    user_objective: str = "",
    max_depth: int = 3,
    graph_valid: bool = True,
) -> GraphProfile:
    """Profile a validated, normalized graph into schema stats + verified paths."""
    entities = normalized.get("entities") or []
    rels = normalized.get("relationships") or []
    max_depth = max(1, min(int(max_depth), 6))

    # Step 1 — types + counts.
    type_counts = Counter(e.get("type", "Entity") for e in entities)
    id_to_type = {e.get("id"): e.get("type", "Entity") for e in entities}
    rel_type_counts: Counter[str] = Counter()
    schema_edge_counts: Counter[tuple[str, str, str]] = Counter()
    for r in rels:
        st = id_to_type.get(r.get("source"))
        tt = id_to_type.get(r.get("target"))
        rtype = r.get("type", "REL")
        rel_type_counts[rtype] += 1
        if st and tt:
            schema_edge_counts[(st, rtype, tt)] += 1

    # Step 5 — compact schema summary (type-level adjacency).
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for (st, rtype, tt) in sorted(schema_edge_counts):
        adj[st].append((rtype, tt))

    # Steps 2/3 — bounded verified paths. Enumerate from every type (so paths
    # that END at an objective-linked sink are found too); objective only ranks.
    linked = _objective_types(user_objective, list(type_counts))
    starts = sorted(type_counts)
    budget = [_WALK_BUDGET]
    seen: set[tuple[str, ...]] = set()
    all_paths: list[list[str]] = []
    for start in starts:
        for path in _enumerate_paths(adj, start, max_depth, budget):
            key = tuple(path)
            if key in seen:
                continue
            seen.add(key)
            all_paths.append(path)

    def _priority(path: list[str]) -> tuple[int, int]:
        touches = any(t in linked for t in path[::2])
        depth = (len(path) - 1) // 2
        return (0 if touches else 1, -depth)

    all_paths.sort(key=_priority)
    capped = all_paths[:MAX_PATHS]
    verified_paths = [
        VerifiedPath(path_id=_path_id(p), path=p, depth=(len(p) - 1) // 2)
        for p in capped
    ]

    # Step 4 — disconnected / sparse regions + missing keys.
    connected: set[str] = set()
    for (st, _rt, tt) in schema_edge_counts:
        connected.add(st)
        connected.add(tt)
    quality_flags: list[GraphQualityFlag] = []
    for t, c in sorted(type_counts.items()):
        if t not in connected:
            quality_flags.append(GraphQualityFlag(
                code="disconnected_type", type=t, count=c,
                detail=f"{t} has no relationships (possible missing key)"))
    if entities and not rels:
        quality_flags.append(GraphQualityFlag(
            code="no_relationships", detail="graph has entities but no relationships"))

    limitations: list[str] = []
    if len(all_paths) > len(capped):
        limitations.append(
            f"path enumeration capped at {MAX_PATHS}; {len(all_paths) - len(capped)} more within depth {max_depth}")
    if budget[0] <= 0:
        limitations.append("path search hit the exploration budget; some deep paths may be omitted")
    if not graph_valid:
        limitations.append("underlying graph failed validation (C05); profile may be incomplete")

    return GraphProfile(
        graph_profile_id=f"graph_profile_{graph_id}_{graph_version}",
        graph_id=graph_id, graph_version=graph_version,
        user_objective=user_objective, maximum_path_depth=max_depth,
        entity_count=len(entities), relationship_count=len(rels),
        entity_types=[TypeCount(type=t, count=c)
                      for t, c in sorted(type_counts.items(), key=lambda kv: -kv[1])],
        relationship_types=[TypeCount(type=t, count=c)
                            for t, c in sorted(rel_type_counts.items(), key=lambda kv: -kv[1])],
        schema_edges=[SchemaEdge(source_type=st, relationship=rt, target_type=tt, count=c)
                      for (st, rt, tt), c in sorted(schema_edge_counts.items(), key=lambda kv: -kv[1])],
        verified_paths=verified_paths, quality_flags=quality_flags,
        limitations=limitations,
        profile_status="valid" if (graph_valid and type_counts) else "invalid",
    )

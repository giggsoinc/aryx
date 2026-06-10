"""Edge-scoped axiom closures for the reasoning engine.

Three closure kinds, each idempotent via MERGE:

  - inverse_of  : A -[fwd]-> B  =>  B -[inv]-> A
  - symmetric   : A -[name]-> B (A != B)  =>  B -[name]-> A
  - transitive  : A -[name]^n-> B (2..depth)  =>  A -[name]-> B (direct)

Materialised edges carry ``inferred: true`` so callers can distinguish
asserted from derived relationships. Transitive closure is depth-capped to
prevent runaway on cyclic graphs.
"""
from __future__ import annotations

from aryx.graph.falkor_store import FalkorStore

_TRANSITIVE_MAX = 4


def apply_inverse(graph: FalkorStore, edge: str, inverse: str) -> None:
    """For every A -[edge]-> B, MERGE B -[inverse]-> A (marked inferred)."""
    graph.run(
        "MATCH (a)-[:REL {name: $fwd}]->(b) "
        "MERGE (b)-[i:REL {name: $inv}]->(a) "
        "SET i.inferred = true",
        params={"fwd": edge, "inv": inverse},
    )


def apply_symmetric(graph: FalkorStore, edge: str) -> None:
    """For every A -[edge]-> B (A != B), MERGE B -[edge]-> A (marked inferred)."""
    graph.run(
        "MATCH (a)-[:REL {name: $name}]->(b) WHERE id(a) <> id(b) "
        "MERGE (b)-[i:REL {name: $name}]->(a) "
        "SET i.inferred = true",
        params={"name": edge},
    )


def apply_transitive(graph: FalkorStore, edge: str, depth: int) -> None:
    """Close ``edge`` transitively up to ``depth`` hops (capped at _TRANSITIVE_MAX)."""
    d = max(2, min(int(depth), _TRANSITIVE_MAX))
    for hop in range(2, d + 1):
        graph.run(
            f"MATCH (a)-[:REL*{hop}..{hop} {{name: $name}}]->(b) "
            "WHERE id(a) <> id(b) "
            "MERGE (a)-[i:REL {name: $name}]->(b) "
            "SET i.inferred = true",
            params={"name": edge},
        )


def apply_edge_axiom(graph: FalkorStore, edge: str, then: dict) -> int:
    """Dispatch an edge-scoped axiom; return 1 if any closure ran, 0 otherwise."""
    if not edge:
        return 0
    fired = 0
    if then.get("inverse_of"):
        apply_inverse(graph, edge, str(then["inverse_of"]))
        fired = 1
    if then.get("symmetric"):
        apply_symmetric(graph, edge)
        fired = 1
    if then.get("transitive"):
        apply_transitive(graph, edge, int(then.get("max_depth", _TRANSITIVE_MAX)))
        fired = 1
    return fired

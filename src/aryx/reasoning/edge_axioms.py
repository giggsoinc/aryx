"""Edge-scoped axiom closures for the reasoning engine.

Three closure kinds, each idempotent:

  - inverse_of  : A -[fwd]-> B  =>  B -[inv]-> A
  - symmetric   : A -[name]-> B (A != B)  =>  B -[name]-> A
  - transitive  : a chain of 2..depth ``name`` edges from A to B  =>  A -[name]-> B

Closures read ASSERTED edges only and write into the inferred-edge table, so
callers can always tell asserted from derived relationships, and an asserted
edge is never relabelled. Transitive closure is depth-capped (see
``InferredStore.TRANSITIVE_MAX``) to prevent runaway on cyclic graphs.
"""
from __future__ import annotations

from aryx.store.inferred_store import TRANSITIVE_MAX as _TRANSITIVE_MAX
from aryx.store.inferred_store import InferredStore


def apply_inverse(store: InferredStore, edge: str, inverse: str,
                  rule_name: str = "") -> None:
    """For every A -[edge]-> B, record B -[inverse]-> A as inferred."""
    store.apply_inverse(edge, inverse, rule_name)


def apply_symmetric(store: InferredStore, edge: str, rule_name: str = "") -> None:
    """For every A -[edge]-> B (A != B), record B -[edge]-> A as inferred."""
    store.apply_symmetric(edge, rule_name)


def apply_transitive(store: InferredStore, edge: str, depth: int,
                     rule_name: str = "") -> None:
    """Close ``edge`` transitively up to ``depth`` hops (capped at _TRANSITIVE_MAX)."""
    store.apply_transitive(edge, depth, rule_name)


def apply_edge_axiom(store: InferredStore, edge: str, then: dict,
                     rule_name: str = "") -> int:
    """Dispatch an edge-scoped axiom; return 1 if any closure ran, 0 otherwise."""
    if not edge:
        return 0
    fired = 0
    if then.get("inverse_of"):
        apply_inverse(store, edge, str(then["inverse_of"]), rule_name)
        fired = 1
    if then.get("symmetric"):
        apply_symmetric(store, edge, rule_name)
        fired = 1
    if then.get("transitive"):
        apply_transitive(store, edge, int(then.get("max_depth", _TRANSITIVE_MAX)),
                         rule_name)
        fired = 1
    return fired

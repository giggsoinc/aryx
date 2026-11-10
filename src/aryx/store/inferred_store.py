"""Reasoning-engine output for one workspace: inferred edges and labels.

Derived data, kept apart from ``aryx_relationship`` so asserted edges are never
polluted. Every closure reads asserted edges only and skips pairs that already
exist as an asserted edge, so an asserted edge can never be relabelled as
inferred. Used as a context manager so the clear-then-rebuild of one
evaluation is a single transaction: it commits whole or not at all.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

TRANSITIVE_MIN = 2
TRANSITIVE_MAX = 4  # one query per hop length; deeper chains are not materialised


class InferredStore:
    """Writes inferred edges and labels inside one transaction."""

    def __init__(self, dsn: str, workspace_id: int) -> None:
        """Bind to the shared pool for ``dsn`` and one workspace."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)
        self._cm: Any = None
        self._conn: Any = None

    def __enter__(self) -> "InferredStore":
        self._cm = self._pool.connection()
        self._conn = self._cm.__enter__()
        return self

    def __exit__(self, *exc_info: Any) -> Any:
        return self._cm.__exit__(*exc_info)

    def _run(self, query: str, params: dict[str, Any]) -> int:
        """Run a named statement with the workspace bound; return rows written."""
        with self._conn.cursor() as cur:
            cur.execute(load(query), {"ws": self._ws, **params})
            return max(cur.rowcount, 0)

    def clear(self) -> None:
        """Delete every inferred edge and label for this workspace."""
        with self._conn.cursor() as cur:
            cur.execute(load("delete_inferred_relationships_by_workspace"), (self._ws,))
            cur.execute(load("delete_inferred_labels_by_workspace"), (self._ws,))

    def apply_inverse(self, edge: str, inverse: str, rule_name: str = "") -> int:
        """A -[edge]-> B  =>  B -[inverse]-> A. Returns edges created."""
        return self._run("inferred_apply_inverse",
                         {"fwd": edge, "inv": inverse, "rule": rule_name})

    def apply_symmetric(self, edge: str, rule_name: str = "") -> int:
        """A -[edge]-> B (A != B)  =>  B -[edge]-> A. Returns edges created."""
        return self._run("inferred_apply_symmetric",
                         {"name": edge, "rule": rule_name})

    def apply_transitive(self, edge: str, depth: int, rule_name: str = "") -> int:
        """Connect A to B when a chain of 2..depth asserted ``edge`` hops joins them.

        ``depth`` is clamped to 2..4. Returns edges created.
        """
        capped = max(TRANSITIVE_MIN, min(int(depth), TRANSITIVE_MAX))
        created = 0
        for hops in range(TRANSITIVE_MIN, capped + 1):
            created += self._run(f"inferred_transitive_{hops}",
                                 {"name": edge, "rule": rule_name})
        return created

    def add_named_target_edge(self, source_id: int, name: str, target_type: str,
                              target_name: str, rule_name: str = "") -> int:
        """Connect one entity to each entity of ``target_type`` named ``target_name``."""
        return self._run("inferred_add_named_target_edge", {
            "source": int(source_id), "name": name, "target_type": target_type,
            "target_name": target_name, "rule": rule_name})

    def set_label(self, entity_id: int, label: str, rule_name: str = "") -> None:
        """Set (or replace) an entity's inferred label."""
        self._run("inferred_upsert_label", {
            "entity": int(entity_id), "label": label, "rule": rule_name})

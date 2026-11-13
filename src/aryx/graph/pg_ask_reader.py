"""Aggregate reads the Ask flow needs, split out of the Postgres graph reader.

Exact per-type counts, categorical value counts, record attributes and sample
names. They live in a mixin so ``pg_reader`` stays the plain entity/edge reader
and these four Ask-specific queries have one home. The host class supplies
``_rows(query, params)``, which binds the workspace.
"""
from __future__ import annotations

from typing import Any

_MAX_SAMPLES = 10


class PostgresAskStatsMixin:
    """``count_by_type`` / ``attribute_breakdown`` / ``entity_attributes`` / ``sample_names``."""

    def _rows(self, query: str, params: dict[str, Any]) -> list[tuple]:
        """Run a named query with the workspace bound (the host class overrides this)."""
        raise NotImplementedError

    def count_by_type(self) -> dict[str, int]:
        """Return the exact number of entities per ontology type.

        Unlike ``find_entities`` this is not capped at 500 rows, so it is safe
        to report as a total.

        Returns:
            ``{ontology_type: count}``; empty for an empty workspace.
        """
        return {str(r[0]): int(r[1])
                for r in self._rows("graph_count_by_type", {})}

    def entity_attributes(self, entity_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Return the raw attribute map (status, priority, ...) per entity.

        Args:
            entity_ids: Entities to look up; ids not in this workspace are
                simply absent from the result.

        Returns:
            ``{entity_id: {attribute: value}}``.
        """
        if not entity_ids:
            return {}
        rows = self._rows("graph_entity_attributes",
                          {"ids": [int(i) for i in entity_ids]})
        return {int(r[0]): (r[1] if isinstance(r[1], dict) else {})
                for r in rows}

    def attribute_breakdown(self, max_values: int = 8) -> dict[str, dict[str, dict[str, int]]]:
        """Return value counts for low-cardinality attributes of every type.

        Example: ``{"Ticket": {"status": {"closed": 54, "open": 26}}}``. Keys
        whose values are (nearly) unique, such as ids and names, are left out.
        Counts cover only the records that carry the key.

        Args:
            max_values: Most distinct values a key may have to be reported.

        Returns:
            ``{ontology_type: {attribute: {value: count}}}``.
        """
        out: dict[str, dict[str, dict[str, int]]] = {}
        for t, key, value, n in self._rows(
                "graph_attribute_breakdown",
                {"max_values": max(1, int(max_values))}):
            out.setdefault(str(t), {}).setdefault(str(key), {})[str(value)] = int(n)
        return out

    def sample_names(self, per_type: int = 3) -> dict[str, list[str]]:
        """Return the first few display names of every type, in one query.

        Args:
            per_type: Names per type (clamped to 1..10).

        Returns:
            ``{ontology_type: [name, ...]}`` in id order.
        """
        n = max(1, min(int(per_type), _MAX_SAMPLES))
        out: dict[str, list[str]] = {}
        for t, name in self._rows("graph_sample_names", {"n": n}):
            if name:
                out.setdefault(str(t), []).append(str(name))
        return out

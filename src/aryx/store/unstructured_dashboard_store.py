"""Read-side aggregation for the dashboard's document/word-cloud section.

Deliberately separate from `entity_store.py` and from the C07-C14 governed
dashboard-spec pipeline: this is a plain, deterministic frequency count over
already-landed entity mentions, not an LLM-drafted KPI/Analysis, so it has no
business going through C08's grounding or C09's validation gates. Same
precedent as `DatasetsPanel` reading `profile`/`semantic` directly.
"""
from __future__ import annotations

import logging

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class UnstructuredDashboardStore:
    """Workspace-scoped reads over document-sourced entity mentions."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def has_document_data(self) -> bool:
        """True if this workspace has landed any document-sourced record."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_has_document_source"), (self._ws,))
                row = cur.fetchone()
        return bool(row[0]) if row else False

    def top_document_entities(
        self, limit: int = 40, min_count: int = 2,
    ) -> list[dict[str, str | int]]:
        """Top document-sourced entity mentions by frequency.

        Args:
            limit: Max distinct (type, name) pairs to return.
            min_count: Minimum mention count to include — filters out
                one-off noise before the frontend applies its own
                render-worthiness threshold.

        Returns:
            ``[{"ontology_type": ..., "name": ..., "count": ...}, ...]``,
            highest count first.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("select_document_entity_frequency"),
                    (self._ws, min_count, limit),
                )
                rows = cur.fetchall()
        return [
            {"ontology_type": r[0], "name": r[1], "count": int(r[2])}
            for r in rows
        ]

    def entity_timeline(self) -> list[dict[str, str | int]]:
        """Document-sourced entities discovered per day, oldest first.

        Counts each entity once on the day it was first created
        (`aryx_entity.created_at`), even if it has multiple document-sourced
        member rows — this is a discovery timeline, not a mention count.

        Returns:
            ``[{"date": "YYYY-MM-DD", "count": ...}, ...]``, chronological.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_document_entity_timeline"), (self._ws,))
                rows = cur.fetchall()
        return [{"date": r[0].isoformat(), "count": int(r[1])} for r in rows]

    def entity_excerpts(
        self, ontology_type: str, name: str, limit: int = 3,
    ) -> list[str]:
        """Sample verbatim excerpts for one entity, longest first.

        Deduped by exact text match (near-identical-but-not-exact boilerplate
        is an accepted gap for v1, not fixed here). `span` text is a
        substring of chunk text already screened by the existing fail-closed
        PII boundary (`pii.py::screen_chunks`) before extraction — safe to
        surface as-is, no new PII handling needed.

        Args:
            ontology_type: The entity's type, as returned by
                `top_document_entities`.
            name: The entity's name, as returned by `top_document_entities`.
            limit: Max distinct excerpts to return.

        Returns:
            Verbatim excerpt strings, longest (most informative) first.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("select_document_entity_excerpts"),
                    (self._ws, ontology_type, name, limit),
                )
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

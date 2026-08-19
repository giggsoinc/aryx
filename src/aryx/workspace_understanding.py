"""Brief-provenance and data-understanding accessors for WorkspaceStore.

Split out of workspaces.py purely to keep that module under the 150-line
style cap — these three methods arrived together with migration 0044 and
pushed it over. Mixed into WorkspaceStore, so callers still say
`store.get_understanding(...)`; nothing about the public API changed.

The columns they own encode one rule: the customer's brief (0016) is
authoritative and human-authored, while `data_understanding` (0044) is
what the pipeline inferred from the uploaded data and is read-only.
`brief_source` records which of the two the `brief` column currently holds.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load

logger = logging.getLogger(__name__)


class WorkspaceUnderstandingMixin:
    """Read/write the brief-provenance and data-understanding columns."""

    _conn: Any  # supplied by WorkspaceStore

    def set_brief_source(self, wid: int, source: str) -> str:
        """Record whether `brief` was authored by the customer or derived.

        'customer' is the architecture default — the brief is captured
        before upload. 'derived' marks a brief back-filled from data
        because the customer skipped the brief step.
        """
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_brief_source"),
                        (str(source), int(wid)))
            row = cur.fetchone()
        logger.info("workspace brief_source set id=%s source=%s", wid, source)
        return str(row[1]) if row else str(source)

    def promote_derived_brief(self, wid: int,
                              brief: dict) -> dict[str, Any] | None:
        """Adopt a derived brief, but ONLY while the customer has none.

        One statement, so the emptiness check and the write cannot be
        separated. Doing this as read-then-write let a customer's brief be
        overwritten when they saved it mid-ingest, and could leave a
        derived brief still labelled 'customer' if the process died between
        the two updates.

        Returns the updated row, or None when the brief was already
        populated — meaning someone won the race and the caller must NOT
        treat this as a promotion.
        """
        with self._conn.cursor() as cur:
            cur.execute(load("promote_derived_brief"), (Json(brief or {}), int(wid)))
            row = cur.fetchone()
        if row is None:
            logger.info("derived brief NOT promoted ws=%s — a customer brief "
                        "was saved first", wid)
            return None
        logger.info("derived brief promoted ws=%s", wid)
        return {"id": row[0], "brief": row[1] or {},
                "brief_source": row[2] or "derived"}

    def get_understanding(self, wid: int) -> dict[str, Any]:
        """Return the customer brief alongside Aryx's read-only reading of
        the data, plus the brief's provenance."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_workspace_understanding"), (int(wid),))
            row = cur.fetchone()
        if not row:
            return {"brief": {}, "data_understanding": {},
                    "brief_source": "customer"}
        return {"brief": row[0] or {}, "data_understanding": row[1] or {},
                "brief_source": row[2] or "customer"}

    def set_understanding(self, wid: int,
                          understanding: dict) -> dict[str, Any]:
        """Persist what the pipeline inferred from the data.

        Never touches `brief` — the customer's brief stays authoritative.
        """
        with self._conn.cursor() as cur:
            cur.execute(load("update_workspace_understanding"),
                        (Json(understanding or {}), int(wid)))
            row = cur.fetchone()
        logger.info("workspace understanding updated id=%s keys=%d", wid,
                    len(understanding or {}))
        return {"id": row[0], "data_understanding": row[1] or {}}

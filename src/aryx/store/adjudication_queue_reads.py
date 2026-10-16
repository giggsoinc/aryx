"""Read side of the adjudication queue (G10): paging, dedup, lookups.

Split out of ``adjudication_store.py`` to stay under the size cap; the
write side and merge side live in their own modules and all three compose
together as ``AdjudicationStore``.
"""
from __future__ import annotations

from typing import Any

from aryx.queries import load

_COLS = ("id", "run_id", "left_record_id", "right_record_id", "score",
         "llm_verdict", "llm_reason", "status", "decided_by", "decided_at",
         "created_at")


class AdjudicationQueueReads:
    """Mixin: everything that reads the queue without mutating it.

    Assumes the composing class sets ``self._pool`` and ``self._ws``
    (see ``AdjudicationStore.__init__``).
    """

    def page(self, status: str = "pending", limit: int = 50,
             offset: int = 0) -> list[dict[str, Any]]:
        """Return one page of queue rows with the given status.

        For "pending", dedup happens BEFORE pagination: two rows that
        collapse to the same entity pair (see ``pending_duplicates_of``)
        aren't a column ``ORDER BY`` can group by, so naive SQL LIMIT/OFFSET
        can split them across pages or shrink a page below `limit`. Fetching
        every pending row, deduping in id order, then slicing avoids both.
        Approved/rejected paginate directly in SQL — no duplicate-pair shape
        there. Round trips stay constant either way; only row *volume* scales
        with pending count, same as the batched entity lookup below.
        """
        if status != "pending":
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(load("select_adjudication_page"),
                                (self._ws, status, limit, offset))
                    rows = cur.fetchall()
            return [dict(zip(_COLS, r)) for r in rows]

        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_adjudication_all_by_status"),
                            (self._ws, status))
                rows = cur.fetchall()
        result = [dict(zip(_COLS, r)) for r in rows]
        record_ids = [rid for row in result
                     for rid in (row["left_record_id"], row["right_record_id"])]
        entity_of = self._entities_of_records(record_ids)
        seen_pairs: set[frozenset[int]] = set()
        deduped = []
        for row in result:
            left_entity = entity_of.get(row["left_record_id"])
            right_entity = entity_of.get(row["right_record_id"])
            if left_entity is not None and right_entity is not None:
                pair = frozenset((left_entity, right_entity))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
            deduped.append(row)
        return deduped[offset:offset + limit]

    def get(self, adjudication_id: int) -> dict[str, Any] | None:
        """One queue row by id, scoped to this workspace (None if absent)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_adjudication_by_id"),
                            (adjudication_id, self._ws))
                row = cur.fetchone()
        if row is None:
            return None
        keys = ("id", "workspace_id", "run_id", "left_record_id",
                "right_record_id", "score", "llm_verdict", "llm_reason",
                "status", "decided_by", "decided_at")
        return dict(zip(keys, row))

    def entity_of_record(self, record_id: int) -> int | None:
        """The entity a landed record currently belongs to, if any."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_entity_of_record"),
                            (self._ws, record_id))
                row = cur.fetchone()
        return int(row[0]) if row else None

    def _entities_of_records(self, record_ids: list[int]) -> dict[int, int]:
        """Batched ``entity_of_record``: one round trip for many records.

        ``page()``/``pending_duplicates_of()`` used to call this per side
        per row — 90+ sequential queries on a real 45-row queue. ``DISTINCT
        ON`` + matching ``ORDER BY`` reproduces the single-record tie-break
        (lowest entity_id wins) in one query; no entity means no key, same
        as a None return.
        """
        if not record_ids:
            return {}
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_entities_of_records"),
                            (self._ws, record_ids))
                rows = cur.fetchall()
        return {int(rid): int(eid) for rid, eid in rows}

    def pending_duplicates_of(self, adjudication_id: int, left_record_id: int,
                              right_record_id: int) -> list[int]:
        """Other pending rows that already describe the same entity pair.

        Two originally-distinct record pairs can resolve to the same two
        entities by decide time (e.g. B and C auto-merged via a THIRD pair
        in the same run) — the human would otherwise be asked the same
        question twice. Must be called BEFORE this row's own merge runs, so
        both sides are still pre-merge entity ids to compare against.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_other_pending"),
                            (self._ws, adjudication_id))
                others = cur.fetchall()
        record_ids = [left_record_id, right_record_id]
        for _oid, other_left, other_right in others:
            record_ids.extend((other_left, other_right))
        entity_of = self._entities_of_records(record_ids)

        left_entity = entity_of.get(left_record_id)
        right_entity = entity_of.get(right_record_id)
        if left_entity is None or right_entity is None:
            return []
        target = frozenset((left_entity, right_entity))
        return [
            oid for oid, other_left, other_right in others
            if frozenset((entity_of.get(other_left),
                         entity_of.get(other_right))) == target
        ]

    def raw_records(self, record_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Raw source payloads for records not yet resolved into an entity."""
        if not record_ids:
            return {}
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_landed_by_ids"),
                            (self._ws, record_ids))
                rows = cur.fetchall()
        return {int(rid): payload for rid, payload, _system, _cleaned in rows}

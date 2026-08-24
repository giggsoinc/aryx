"""Persistence for the human adjudication queue (G10).

Every queued pair — human-decided or LLM-decided — is a labeled training
example. ``merge_entities_of`` is the post-hoc union applied when a human
approves a pair after the run already materialized separate entities.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from psycopg.types.json import Json, Jsonb

from aryx.queries import load
from aryx.resolution.golden import golden_record_with_policy
from aryx.resolution.survivorship import SurvivorshipPolicy
from aryx.store.entity_store import _dumps
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

_COLS = ("id", "run_id", "left_record_id", "right_record_id", "score",
         "llm_verdict", "llm_reason", "status", "decided_by", "decided_at",
         "created_at")


class AdjudicationStore:
    """Reads and writes adjudication queue rows + applies entity merges."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def enqueue(self, run_id: int, left_id: int, right_id: int, score: float,
                llm_verdict: float | None, llm_reason: str | None,
                status: str) -> int:
        """Insert one band pair; returns the queue row id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_adjudication"),
                            (self._ws, run_id, left_id, right_id, score,
                             llm_verdict, llm_reason, status))
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def page(self, status: str = "pending", limit: int = 50,
             offset: int = 0) -> list[dict[str, Any]]:
        """Return one page of queue rows with the given status.

        For "pending", rows that already resolve to the same entity pair as
        an earlier row on this page are dropped — see
        ``pending_duplicates_of`` for how that happens (an in-run auto-merge
        collapsing two originally-distinct record pairs into one decision).
        Deciding either duplicate still closes both; this only keeps the
        review list itself from showing the same question twice.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_adjudication_page"),
                            (self._ws, status, limit, offset))
                rows = cur.fetchall()
        result = [dict(zip(_COLS, r)) for r in rows]
        if status != "pending":
            return result
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
        return deduped

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

        ``page()`` and ``pending_duplicates_of()`` used to call
        ``entity_of_record`` once per side per row — 2 round trips per
        pending row, which on a real 45-row queue is 90+ sequential
        queries just to render the list. ``DISTINCT ON`` + the matching
        ``ORDER BY`` in the query reproduces ``entity_of_record``'s own
        tie-break (lowest entity_id wins) in one query; a record with no
        entity simply has no key in the result, same as a None return.
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
        entities by decide time: e.g. records B and C auto-merged via a
        THIRD pair earlier in the same run, so a pending (A, B) row and a
        pending (A, C) row now both mean "should A merge with {B, C}?" —
        the human would otherwise be asked the identical question twice.
        Must be called BEFORE this row's own merge runs (so both sides are
        still pre-merge entity ids to compare against).
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

    def decide(self, adjudication_id: int, approve: bool,
               decided_by: str) -> dict[str, Any]:
        """Flip a pending row to approved/rejected; returns the updated row.

        Raises:
            ValueError: When the row is missing or already decided.
        """
        status = "approved" if approve else "rejected"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("decide_adjudication"),
                            (status, decided_by, adjudication_id))
                row = cur.fetchone()
        if row is None:
            raise ValueError(f"adjudication {adjudication_id} not pending")
        keys = ("id", "workspace_id", "run_id", "left_record_id",
                "right_record_id", "score", "llm_verdict", "status",
                "decided_by")
        return dict(zip(keys, row))

    def stats(self) -> dict[str, Any]:
        """Queue stats incl. human/LLM agreement rate (the sales number)."""
        try:
            auto_merge = float(os.environ.get("ARYX_ER_AUTO_MERGE", 0.95))
        except ValueError:
            auto_merge = 0.95
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("adjudication_stats"), (auto_merge, self._ws))
                row = cur.fetchone()
        pending, approved, rejected, auto_llm, auto_reject, agree, overlap = row
        decided = approved + rejected
        return {
            "pending": pending, "approved": approved, "rejected": rejected,
            "auto_llm": auto_llm, "auto_reject": auto_reject,
            "approval_rate": approved / decided if decided else None,
            "human_llm_agreement": agree / overlap if overlap else None,
        }

    def _members_for_entities(self, cur: Any,
                              entity_ids: list[int]) -> list[dict[str, Any]]:
        """Every landed record behind a set of entities, shaped for
        ``golden_record_with_policy`` (payload + record/source/time)."""
        cur.execute(load("select_member_landed_ids"), (self._ws, entity_ids))
        landed_ids = [r[1] for r in cur.fetchall()]
        cur.execute(load("select_landed_by_ids"), (self._ws, landed_ids))
        return [
            {"payload": payload, "record_id": rid,
             "source_system": source_system, "cleaned_at": cleaned_at}
            for rid, payload, source_system, cleaned_at in cur.fetchall()
        ]

    def _save_conflicts(self, cur: Any, entity_id: int,
                        conflicts: list[dict[str, Any]]) -> None:
        """Audit-log each losing value exactly as normal resolution does."""
        for conflict in conflicts:
            cur.execute(
                load("insert_attribute_conflict"),
                (self._ws, entity_id, conflict["attribute"],
                 Json(conflict["winning_value"], dumps=_dumps),
                 Json(conflict["losing_values"], dumps=_dumps),
                 conflict["strategy"]))

    def merge_entities_of(self, left_record_id: int, right_record_id: int,
                          policy: SurvivorshipPolicy | None = None) -> bool:
        """Union the entities containing two landed records (post-hoc merge).

        The lower-id entity's row survives (its id keeps every foreign key
        stable); which id survives is a storage detail only. The golden
        record's attributes are recomputed from every member of BOTH
        entities under the workspace's real ``SurvivorshipPolicy`` — the
        same engine (``golden_record_with_policy``) full ingest uses — so
        e.g. "most_recent" or "most_complete" is honored here too, instead
        of the survivor's pre-existing values winning unconditionally.
        Conflicts are logged to ``aryx_attribute_conflict`` exactly as they
        are during normal resolution. Re-projection of the workspace graph
        is wipe-rebuild until G8 lands.

        Returns:
            True when a merge happened; False when already same entity or
            either record has no entity yet.
        """
        policy = policy or SurvivorshipPolicy()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_entity_of_record"),
                            (self._ws, left_record_id))
                left = cur.fetchone()
                cur.execute(load("select_entity_of_record"),
                            (self._ws, right_record_id))
                right = cur.fetchone()
                if not left or not right or left[0] == right[0]:
                    return False
                keep, drop = sorted((int(left[0]), int(right[0])))

                members = self._members_for_entities(cur, [keep, drop])
                merged, _provenance, conflicts = golden_record_with_policy(
                    members, policy)

                cur.execute(load("update_entity_attributes"),
                            (Jsonb(merged, dumps=_dumps), keep, self._ws))
                cur.execute(load("move_entity_members"),
                            (keep, self._ws, drop))
                cur.execute(load("delete_entity_row"), (drop, self._ws))
                self._save_conflicts(cur, keep, conflicts)
        logger.info("entities merged keep=%s drop=%s ws=%s conflicts=%d",
                    keep, drop, self._ws, len(conflicts))
        return True

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

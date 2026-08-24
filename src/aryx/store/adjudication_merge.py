"""Post-hoc entity merge for the adjudication queue (G10).

Split out of ``adjudication_store.py`` to keep each file under the size
cap — this mixin owns ``merge_entities_of`` (applied when a human approves
a pair after the run already materialized separate entities) and its two
private helpers; the read side and write side live in their own modules
and compose together as ``AdjudicationStore``.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json, Jsonb

from aryx.queries import load
from aryx.resolution.golden import golden_record_with_policy
from aryx.resolution.survivorship import SurvivorshipPolicy
from aryx.store.entity_store import _dumps

logger = logging.getLogger(__name__)


class AdjudicationMerge:
    """Mixin: the post-hoc union of two entities behind an approved pair.

    Assumes the composing class sets ``self._pool`` and ``self._ws``
    (see ``AdjudicationStore.__init__``).
    """

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

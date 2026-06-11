"""Persistence + record loading for entity resolution (stage 7).

Reads a run's landed records (building match text from key attributes) and
writes resolved entities plus their provenance members. SQL lives in queries/.
"""
from __future__ import annotations

import json
import logging

from psycopg.types.json import Json

from aryx.models import (
    EntityMember,
    Relationship,
    ResolutionRecord,
    ResolvedEntity,
)
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


def _dumps(value: object) -> str:
    """JSON-encode, stringifying non-native types."""
    return json.dumps(value, default=str)


class EntityStore:
    """Loads landed records and persists resolved entities + members."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def landed_records(self, run_id: int, key_attrs: list[str]) -> list[ResolutionRecord]:
        """Read a run's landed records, building match text from key attributes.

        Args:
            run_id: The discovery run to load.
            key_attrs: Payload keys whose values form the match text.

        Returns:
            One ResolutionRecord per landed row.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_landed_by_run"), (run_id, self._ws))
                rows = cur.fetchall()
        records = []
        for record_id, payload in rows:
            text = " ".join(str(payload.get(a, "")) for a in key_attrs).strip()
            records.append(
                ResolutionRecord(record_id=record_id, text=text, payload=payload)
            )
        return records

    def save(self, results: list[tuple[ResolvedEntity, list[EntityMember]]]) -> int:
        """Persist resolved entities and their provenance members.

        Returns the number of entities written.
        """
        count = 0
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                for entity, members in results:
                    cur.execute(
                        load("insert_entity"),
                        (self._ws, entity.ontology_type,
                         Json(entity.attributes, dumps=_dumps), entity.confidence),
                    )
                    row = cur.fetchone()
                    entity_id = int(row[0]) if row else 0
                    for member in members:
                        cur.execute(
                            load("insert_entity_member"),
                            (self._ws, entity_id, member.landed_record_id,
                             member.confidence),
                        )
                    count += 1
        logger.info("entities saved count=%d", count)
        return count

    def save_relationships(self, relationships: list[Relationship]) -> None:
        """Persist inferred relationships between entities (stage 8)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                conn.cursor().executemany(
                    load("insert_relationship"),
                    [(self._ws, r.source_entity_id, r.target_entity_id,
                      r.name, r.confidence) for r in relationships],
                )

    def list_entities(self) -> list[tuple[int, str, dict]]:
        """Return (id, ontology_type, attributes) for graph projection."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_entities"), (self._ws,))
                return [(r[0], r[1], r[2]) for r in cur.fetchall()]

    def list_members_provenance(self) -> list[tuple[int, str, str, str]]:
        """Return (entity_id, system, dataset, record_id) provenance edges."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_members_provenance"), (self._ws,))
                return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]

    def list_relationships(self) -> list[tuple[int, int, str]]:
        """Return (source_entity_id, target_entity_id, name) edges."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_relationships"), (self._ws,))
                return [(r[0], r[1], r[2]) for r in cur.fetchall()]

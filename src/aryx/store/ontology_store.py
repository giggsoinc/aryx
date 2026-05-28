"""Persistence for ontology types and schema mappings (stage 6).

Kept separate from PostgresStore so each module stays focused. SQL lives in
aryx/queries/*.sql. New types are inserted as-is (proposed); approval flips
status via the HITL gate.
"""
from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Json

from aryx.models import OntologyType, SchemaMapping
from aryx.queries import load

logger = logging.getLogger(__name__)


class OntologyStore:
    """Reads and writes ontology types and schema mappings."""

    def __init__(self, dsn: str) -> None:
        """Open a connection to the ontology store."""
        self._conn = psycopg.connect(dsn, autocommit=False)

    def seed_types(self, types: list[OntologyType]) -> None:
        """Insert types, ignoring any whose name already exists."""
        with self._conn.cursor() as cur:
            cur.executemany(
                load("upsert_ontology_type"),
                [(t.name, Json(t.attributes), t.status, t.source) for t in types],
            )
        self._conn.commit()

    def list_types(self) -> list[OntologyType]:
        """Return all known ontology types (grounding for the agent)."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_ontology_types"))
            rows = cur.fetchall()
        return [
            OntologyType(name=r[0], attributes=r[1], status=r[2], source=r[3])
            for r in rows
        ]

    def save_mappings(self, run_id: int, mappings: list[SchemaMapping]) -> None:
        """Persist schema mappings produced for a run."""
        with self._conn.cursor() as cur:
            cur.executemany(
                load("insert_schema_mapping"),
                [
                    (run_id, m.source_system, m.source_dataset, m.source_field,
                     m.ontology_type, m.ontology_attribute, m.confidence)
                    for m in mappings
                ],
            )
        self._conn.commit()

    def approve_type(self, name: str) -> None:
        """Approve a proposed type — the human review gate."""
        with self._conn.cursor() as cur:
            cur.execute(load("approve_ontology_type"), (name,))
        self._conn.commit()
        logger.info("ontology type approved name=%s", name)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

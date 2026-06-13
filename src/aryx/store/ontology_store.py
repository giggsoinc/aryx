"""Persistence for ontology types and schema mappings (stage 6).

Workspace-scoped: every type lives in exactly one workspace. The HITL
gate (approve_type) and the parent / ancestor lookups all filter by
workspace_id so DEMO's types never bleed into Default.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.models import OntologyType, SchemaMapping
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class OntologyStore:
    """Reads and writes ontology types and schema mappings."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._workspace_id = int(workspace_id)

    def seed_types(self, types: list[OntologyType]) -> None:
        """Insert types into this workspace, ignoring duplicates."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    load("upsert_ontology_type"),
                    [(self._workspace_id, t.name, Json(t.attributes),
                      t.status, t.source) for t in types],
                )

    def list_types(self) -> list[OntologyType]:
        """Return ontology types for the bound workspace."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_ontology_types"),
                            (self._workspace_id,))
                rows = cur.fetchall()
        return [
            OntologyType(name=r[0], attributes=r[1], status=r[2], source=r[3],
                         parent_type=r[4])
            for r in rows
        ]

    def set_parent(self, name: str, parent: str | None) -> None:
        """Set or clear the parent_type for a type (rdfs:subClassOf)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("set_ontology_parent"),
                            (parent, self._workspace_id, name))
        logger.info("ontology parent set ws=%s name=%s parent=%s",
                    self._workspace_id, name, parent)

    def ancestors(self, name: str) -> list[str]:
        """Return ancestor type names from nearest parent to root."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_type_ancestors"),
                            (self._workspace_id, name, self._workspace_id))
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def save_mappings(self, run_id: int, mappings: list[SchemaMapping]) -> None:
        """Persist schema mappings produced for a run."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    load("insert_schema_mapping"),
                    [
                        (run_id, m.source_system, m.source_dataset,
                         m.source_field, m.ontology_type, m.ontology_attribute,
                         m.confidence)
                        for m in mappings
                    ],
                )

    def approve_type(self, name: str) -> None:
        """Approve a proposed type — the human review gate."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("approve_ontology_type"),
                            (self._workspace_id, name))
        logger.info("ontology type approved ws=%s name=%s",
                    self._workspace_id, name)

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

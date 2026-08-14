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

    def upsert_type_attributes(self, name: str, attributes: list[str],
                                status: str = "approved",
                                source: str = "derived") -> None:
        """Insert-or-overwrite a type's attribute list.

        Unlike seed_types (ON CONFLICT DO NOTHING, used for HITL-proposed
        types where an existing row must never be clobbered), this always
        applies the given attributes — needed so a manually-stubbed empty
        type (e.g. a Customer type created with no attributes) can gain
        real ones once entities are derived into it. Callers are
        responsible for merging with any pre-existing attribute list first.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("upsert_ontology_type_overwrite"),
                            (self._workspace_id, name, Json(attributes),
                             status, source))
        logger.info("ontology type attrs upserted ws=%s name=%s attrs=%d",
                    self._workspace_id, name, len(attributes))

    def merge_attributes(self, name: str, new_attrs: list[str],
                          status: str = "approved", source: str = "derived") -> None:
        """Merge new_attrs into name's existing attribute list (or create
        it) and upsert — order-preserving dedup so a manually-stubbed empty
        type gains real attributes without losing any it already had.

        Additive on attributes only: if the type already exists, its
        current status and source are kept as-is (status/source args only
        apply when creating a brand-new type) so this can never silently
        flip a HITL-approved or manually-sourced type's status/source just
        because a derive run happened to touch the same name.
        """
        existing = next((t for t in self.list_types() if t.name == name), None)
        merged = list(dict.fromkeys((existing.attributes if existing else []) + new_attrs))
        if existing:
            status, source = existing.status, existing.source
        self.upsert_type_attributes(name, merged, status=status, source=source)

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

    def delete_type(self, name: str) -> None:
        """Remove a type from this workspace. Instances are not touched —
        callers (the API) decide whether to refuse on non-empty types."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("delete_ontology_type"),
                            (self._workspace_id, name))
        logger.info("ontology type deleted ws=%s name=%s",
                    self._workspace_id, name)

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""

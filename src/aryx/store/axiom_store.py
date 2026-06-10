"""Persistence for ontology axioms (disjoint_with, equivalent_to,
domain, range, cardinality_max) and their projection-time violations.

Workspace-scoped; idempotent on ``(workspace_id, subject_type, kind, payload_hash)``
so the same axiom can be POSTed twice without duplicating. The hash is over a
canonicalised JSON payload so equivalent dicts produce one row.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import psycopg
from psycopg.types.json import Json

from aryx.queries import load

logger = logging.getLogger(__name__)

VALID_KINDS = {"disjoint_with", "equivalent_to", "domain", "range",
               "cardinality_max"}


def _canonical_hash(payload: dict[str, Any]) -> str:
    """Stable SHA-256 over a sorted-key JSON payload."""
    encoded = json.dumps(payload or {}, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AxiomStore:
    """Reads, writes, and lists ontology axioms + their violations."""

    def __init__(self, dsn: str) -> None:
        """Open a connection to the axiom store."""
        self._conn = psycopg.connect(dsn, autocommit=False)

    def add(self, workspace_id: int, subject_type: str, kind: str,
            payload: dict[str, Any]) -> int | None:
        """Upsert one axiom; return its id or None when it already exists."""
        if kind not in VALID_KINDS:
            raise ValueError(f"unknown axiom kind '{kind}'; "
                             f"choose from {sorted(VALID_KINDS)}")
        payload_hash = _canonical_hash(payload)
        with self._conn.cursor() as cur:
            cur.execute(
                load("insert_ontology_axiom"),
                (workspace_id, subject_type, kind, Json(payload or {}),
                 payload_hash),
            )
            row = cur.fetchone()
        self._conn.commit()
        return int(row[0]) if row else None

    def list_(self, workspace_id: int) -> list[dict[str, Any]]:
        """Return every axiom in a workspace, ordered for stable export."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_ontology_axioms"), (workspace_id,))
            rows = cur.fetchall()
        return [
            {"id": r[0], "subject_type": r[1], "kind": r[2], "payload": r[3]}
            for r in rows
        ]

    def delete(self, axiom_id: int, workspace_id: int) -> None:
        """Remove an axiom from a workspace (no-op when absent)."""
        with self._conn.cursor() as cur:
            cur.execute(load("delete_ontology_axiom"),
                        (axiom_id, workspace_id))
        self._conn.commit()

    def record_violation(self, workspace_id: int, entity_id: int,
                         axiom_id: int, reason: str) -> None:
        """Persist a projection-time violation for audit."""
        with self._conn.cursor() as cur:
            cur.execute(
                load("insert_axiom_violation"),
                (workspace_id, entity_id, axiom_id, reason),
            )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

"""HTTP client for the ingest endpoints (database connect/discover, documents).

Split out of aryx.ui.api so that module stays within the line budget. Reuses
api's workspace-scoped JSON helpers.
"""
from __future__ import annotations

from typing import Any

from aryx.ui import api


def ingest_db(table: str, ontology_type: str, match_keys: str,
              system: str = "postgresql", key_column: str = "id",
              fk_links: list[dict] | None = None) -> dict:
    """Queue a single-table database ingest."""
    return api._post("/admin/ingest/db", {
        "table": table, "ontology_type": ontology_type,
        "match_keys": match_keys, "system": system, "key_column": key_column,
        "fk_links": fk_links or [],
    })


def db_connect(cfg: dict) -> dict[str, Any]:
    """Open a database connection and introspect its schema."""
    return api._post("/admin/connect", cfg, timeout=60)


def db_discover(connection_id: str, context: str) -> dict[str, Any]:
    """Run the auto-discovery agent to map tables to entity types."""
    return api._post("/admin/discover",
                     {"connection_id": connection_id, "context": context}, timeout=180)


def ingest_multi(connection_id: str, tables: list[dict], edges: list[dict]) -> dict[str, Any]:
    """Queue a multi-table ingest with inferred edges."""
    return api._post("/admin/ingest/multi",
                     {"connection_id": connection_id, "tables": tables, "edges": edges})


def docs_summary(discovery_id: str) -> dict[str, Any]:
    """Return the discovered entity-type summary for an uploaded document set."""
    return api._get(f"/admin/docs/summary/{discovery_id}")


def docs_confirm(discovery_id: str, approved_types: list[str],
                 approved_files: list[str]) -> dict[str, Any]:
    """Confirm which discovered types/files to ingest into the graph."""
    return api._post("/admin/docs/confirm", {"discovery_id": discovery_id,
                     "approved_types": approved_types, "approved_files": approved_files})

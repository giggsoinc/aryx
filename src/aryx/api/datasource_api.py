"""Datasource registry API (Slice 2).

REST shell over DatasourceStore + datasource_quiz: list / add / get / delete
/ test / quiz. Plaintext secrets enter at /add, are immediately Fernet-
encrypted, and never leave this layer again. Test runs a SELECT 1 / list-
files / HEAD-request appropriate to the kind. Ingest of a saved datasource
lives in ``datasource_ingest_api``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx import datasource_secrets
from aryx.config import get_settings
from aryx.connectors.connection_errors import friendly_for_config, redact
from aryx.connectors.schema_inspect import introspect, test_connection
from aryx.datasource_quiz import quiz_for, supported_kinds
from aryx.store.datasource_store import DatasourceStore, open_url

logger = logging.getLogger(__name__)

# Same cap as introspect()'s default, so the picker lists every table that
# ingest would accept (review L2: it used to stop at 25).
_MAX_LISTED_TABLES = 200


class DatasourceAddRequest(BaseModel):
    """Inbound payload for /add — plaintext secret travels at request scope only."""

    name: str
    kind: str
    config: dict[str, Any] = {}
    secret: str = ""
    workspace_id: int = 1
    # Test the connection first and refuse to save on failure (UI sets this).
    verify: bool = False


def datasource_router() -> APIRouter:
    """Build the datasource registry router."""
    router = APIRouter(prefix="/admin/datasources")

    @router.get("/kinds")
    def list_kinds() -> dict[str, Any]:
        """Supported datasource kinds + key configuration status."""
        return {"kinds": supported_kinds(),
                "secret_key_configured": datasource_secrets.key_is_configured()}

    @router.get("/quiz")
    def get_quiz(kind: str) -> dict[str, Any]:
        """Return the quiz field list for a kind."""
        return quiz_for(kind)

    @router.get("")
    def list_datasources(workspace_id: int = 1) -> list[dict[str, Any]]:
        """List datasources for a workspace (mask only, no ciphertext).

        Each row carries ``context_missing`` — True for datasources
        registered before business context became required, so old rows
        are surfaced for backfill rather than blocked.
        """
        rows = DatasourceStore(get_settings().rdb_dsn).list(workspace_id)
        for row in rows:
            row["context_missing"] = not bool(
                (row.get("config") or {}).get("extra_context", "").strip())
        return rows

    @router.post("")
    def add_datasource(req: DatasourceAddRequest) -> dict[str, Any]:
        """Encrypt secret + store. Returns row WITHOUT ciphertext.

        Business context (``config.extra_context``) is required for every
        kind — it drives entity/field mapping quality downstream.
        """
        if not str(req.config.get("extra_context", "")).strip():
            raise HTTPException(
                400, "extra_context is required — describe what this "
                     "datasource contains so mapping can use it")
        store = DatasourceStore(get_settings().rdb_dsn)
        if any(r.get("name") == req.name for r in store.list(req.workspace_id)):
            raise HTTPException(409, _duplicate_msg(req.name))
        # verify=True: test BEFORE saving, so a failed attempt never leaves a
        # half-saved row behind that blocks the retry with a duplicate name.
        ping: dict[str, Any] = {}
        if req.verify:
            ping = _ping(req.kind, req.config, req.secret)
            if not ping.get("ok"):
                raise HTTPException(400, ping.get("error") or "Connection failed")
        try:
            row = store.add(req.workspace_id, req.name, req.kind,
                            req.config, req.secret)
        except psycopg.errors.UniqueViolation as exc:
            raise HTTPException(409, _duplicate_msg(req.name)) from exc
        except Exception as exc:
            raise HTTPException(
                400, f"add failed: {redact(str(exc), req.secret)}") from exc
        if req.verify:
            row["tables"] = ping.get("tables", [])
            row["table_count"] = ping.get("table_count", 0)
        return row

    @router.post("/{datasource_id}/test")
    def test_datasource(datasource_id: int) -> dict[str, Any]:
        """Decrypt → open → ping. Always-pending failure is never silent."""
        store = DatasourceStore(get_settings().rdb_dsn)
        row = store.get(datasource_id)
        if not row:
            raise HTTPException(404, "datasource not found")
        try:
            secret = store.secret_of(datasource_id, actor="api:test")
            return _ping(row["kind"], row["config"], secret)
        except Exception as exc:  # noqa: BLE001 — surface, never raise
            return {"ok": False,
                    "error": friendly_for_config(exc, row["config"] or {}, "")}

    @router.delete("/{datasource_id}")
    def delete_datasource(datasource_id: int) -> dict[str, Any]:
        """Hard-delete a datasource and cascade its audit trail."""
        DatasourceStore(get_settings().rdb_dsn).delete(datasource_id)
        return {"status": "deleted", "datasource_id": datasource_id}

    return router


def _ping(kind: str, config: dict, secret: str) -> dict[str, Any]:
    """Kind-specific reachability check; returns {ok, detail}."""
    if kind == "docs":
        p = Path(config.get("path", ""))
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": f"not a directory: {p}"}
        files = [f.name for f in p.iterdir() if f.is_file()][:25]
        return {"ok": True, "files": files, "file_count": len(files)}
    if kind == "rest":
        return {"ok": True, "note": "rest reachability deferred to ingest"}
    try:
        url = open_url(kind, config, secret)
        test_connection(url)
        tables = [t.get("table") for t in introspect(url, max_tables=_MAX_LISTED_TABLES)
                  if t.get("table")]
        return {"ok": True, "tables": tables, "table_count": len(tables)}
    except Exception as exc:  # noqa: BLE001 — any driver error → friendly text
        return {"ok": False, "error": friendly_for_config(exc, config, secret)}


def _duplicate_msg(name: str) -> str:
    """409 text for a datasource name already used in the workspace."""
    return (f"A connection named '{name}' already exists in this workspace — "
            f"use a different name, or delete the old connection first.")

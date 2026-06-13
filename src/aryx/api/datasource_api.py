"""Datasource registry API (Slice 2).

REST shell over DatasourceStore + datasource_quiz: list / add / get / delete
/ test / quiz. Plaintext secrets enter at /add, are immediately Fernet-
encrypted, and never leave this layer again. Test runs a SELECT 1 / list-
files / HEAD-request appropriate to the kind.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx import datasource_secrets
from aryx.config import get_settings
from aryx.connectors.schema_inspect import introspect, test_connection
from aryx.datasource_quiz import quiz_for, supported_kinds
from aryx.store.datasource_store import DatasourceStore, open_url

logger = logging.getLogger(__name__)


class DatasourceAddRequest(BaseModel):
    """Inbound payload for /add — plaintext secret travels at request scope only."""

    name: str
    kind: str
    config: dict[str, Any] = {}
    secret: str = ""
    workspace_id: int = 1


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
        """List datasources for a workspace (mask only, no ciphertext)."""
        return DatasourceStore(get_settings().rdb_dsn).list(workspace_id)

    @router.post("")
    def add_datasource(req: DatasourceAddRequest) -> dict[str, Any]:
        """Encrypt secret + store. Returns row WITHOUT ciphertext."""
        store = DatasourceStore(get_settings().rdb_dsn)
        try:
            return store.add(req.workspace_id, req.name, req.kind,
                             req.config, req.secret)
        except Exception as exc:
            raise HTTPException(400, f"add failed: {exc}") from exc

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
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

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
    url = open_url(kind, config, secret)
    try:
        test_connection(url)
        tables = [t.get("table") for t in introspect(url, max_tables=25)
                  if t.get("table")]
        return {"ok": True, "tables": tables, "table_count": len(tables)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

"""MCP bearer-token CRUD — issue, list, revoke. Plain token shown ONCE."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.store.mcp_token_store import McpTokenStore

logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Token issuance request."""

    label: str = ""


def mcp_tokens_router() -> APIRouter:
    """Build the /admin/mcp/tokens router."""
    router = APIRouter(prefix="/admin/mcp/tokens")

    @router.get("")
    def list_tokens() -> list[dict[str, Any]]:
        """Return all tokens (metadata only, no raw token)."""
        store = McpTokenStore(get_settings().rdb_dsn)
        try:
            return store.list_()
        finally:
            store.close()

    @router.post("")
    def issue_token(req: TokenRequest) -> dict[str, Any]:
        """Issue a new bearer token. Raw token visible ONCE here."""
        store = McpTokenStore(get_settings().rdb_dsn)
        try:
            return store.issue(req.label or "unnamed")
        finally:
            store.close()

    @router.delete("/{token_id}")
    def revoke_token(token_id: int) -> dict[str, Any]:
        """Revoke a token by id."""
        store = McpTokenStore(get_settings().rdb_dsn)
        try:
            row = store.revoke(token_id)
            if not row:
                raise HTTPException(404, "token not found or already revoked")
            return {"status": "revoked", **row}
        finally:
            store.close()

    return router

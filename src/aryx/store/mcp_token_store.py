"""MCP bearer-token store — issue, list, verify, revoke."""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

import psycopg

from aryx.queries import load

logger = logging.getLogger(__name__)


def _hash(token: str) -> str:
    """SHA-256 of the raw token (storage form)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class McpTokenStore:
    """CRUD for aryx_mcp_token."""

    def __init__(self, dsn: str) -> None:
        """Open a connection."""
        self._conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def issue(self, label: str) -> dict[str, Any]:
        """Generate a new token. Returns plain token ONCE — never again."""
        raw = "aryx_" + secrets.token_urlsafe(32)
        prefix = raw[:12]
        with self._conn.cursor() as cur:
            cur.execute(load("insert_mcp_token"), (label, _hash(raw), prefix))
            row = cur.fetchone()
        logger.info("mcp token issued id=%s label=%s", row[0], label)
        return {"id": row[0], "label": row[1], "prefix": row[2],
                "created_at": row[3], "token": raw}

    def list_(self) -> list[dict[str, Any]]:
        """Return all tokens (no raw token, only prefix + metadata)."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_mcp_tokens"))
            rows = cur.fetchall()
        return [{"id": r[0], "label": r[1], "prefix": r[2],
                 "created_at": r[3], "last_used_at": r[4],
                 "revoked_at": r[5]} for r in rows]

    def verify(self, token: str) -> bool:
        """Return True if the token exists, is not revoked, and touches it."""
        h = _hash(token)
        with self._conn.cursor() as cur:
            cur.execute(load("check_mcp_token"), (h,))
            ok = cur.fetchone() is not None
            if ok:
                cur.execute(load("touch_mcp_token"), (h,))
        return ok

    def revoke(self, token_id: int) -> dict[str, Any]:
        """Mark a token revoked. Returns id+label or empty dict if not found."""
        with self._conn.cursor() as cur:
            cur.execute(load("revoke_mcp_token"), (int(token_id),))
            row = cur.fetchone()
        if not row:
            return {}
        logger.info("mcp token revoked id=%s", row[0])
        return {"id": row[0], "label": row[1]}

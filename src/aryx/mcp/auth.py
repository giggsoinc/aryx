"""Bearer-token authorization for the MCP transports.

Shared by BOTH entry points, which previously differed:

  * the mounted transport (`api/mcp_mount.py`, served at /mcp) checked a
    bearer token but allowed every request through when none was supplied
    OR when no tokens had ever been issued — two fail-OPEN paths;
  * the standalone SSE server (`mcp/sse.py`, the one MCP_QUICKSTART points
    Claude Desktop at, bound 0.0.0.0:8765) had no check at all.

Since the MCP tool surface now MUTATES — file ingest, graph corrections,
chart persistence — an unauthenticated transport is unauthenticated write
access to the knowledge graph. `/mcp` is also in ApiKeyMiddleware's exempt
prefixes, so nothing downstream compensates.

This module fails CLOSED. A deployment with no issued token rejects every
call and says how to fix it, rather than silently serving everyone.
Local development opts out explicitly with ARYX_MCP_AUTH=off.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_UNSET = object()

#: Guidance echoed on rejection so an operator is never left guessing.
DENIED_HINT = (
    "MCP requires a bearer token. Issue one with "
    "POST /admin/mcp/tokens (the plain token is shown once), then send "
    "'Authorization: Bearer <token>'. For local development only, set "
    "ARYX_MCP_AUTH=off to disable this check."
)


def auth_mode() -> str:
    """Return 'off' or 'required' — required is the default (fail closed).

    ARYX_MCP_AUTH_OPTIONAL=1 is still honoured as an explicit legacy
    opt-out so anyone who deliberately set it keeps their behaviour; what
    changes is the DEFAULT, which used to be open.
    """
    mode = (os.environ.get("ARYX_MCP_AUTH") or "").strip().lower()
    if mode in ("off", "required"):
        return mode
    if os.environ.get("ARYX_MCP_AUTH_OPTIONAL") == "1":
        return "off"
    return "required"


def token_from_header(authorization: str | None) -> str:
    """Extract the token from an `Authorization: Bearer <token>` header."""
    value = (authorization or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def is_authorized(token: str) -> bool:
    """True when `token` is a valid, unrevoked MCP token.

    Fails closed on a missing token, on an empty token table, and on any
    store error — the previous implementation returned True for the first
    two, which meant a fresh deployment served every caller.
    """
    if auth_mode() == "off":
        return True
    if not token:
        logger.warning("mcp request rejected — no bearer token supplied")
        return False
    try:
        from aryx.config import get_settings
        from aryx.store.mcp_token_store import McpTokenStore
        store = McpTokenStore(get_settings().rdb_dsn)
        try:
            ok = store.verify(token)
        finally:
            store.close()
    except Exception as exc:  # noqa: BLE001 — never fail open on an error
        logger.error("mcp auth check failed — failing closed: %s", exc)
        return False
    if not ok:
        logger.warning("mcp request rejected — token not recognised")
    return ok


def authorize_headers(authorization: str | None) -> bool:
    """Convenience: extract a bearer token from a header and verify it."""
    return is_authorized(token_from_header(authorization))

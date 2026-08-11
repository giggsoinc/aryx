"""MCP SSE transport mounting for the Aryx FastAPI app.

Split out of api/main.py to keep the app-assembly module under the file
length cap — bearer-auth and SSE mounting are a self-contained concern.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)


def _bearer_ok(request) -> bool:
    """Verify Authorization: Bearer <token>. Allow-all if no tokens issued."""
    auth = (request.headers.get("authorization") or "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        return os.environ.get("ARYX_MCP_AUTH_OPTIONAL", "1") == "1"
    try:
        from aryx.config import get_settings
        from aryx.store.mcp_token_store import McpTokenStore
        store = McpTokenStore(get_settings().rdb_dsn)
        tokens = store.list_()
        if not any(not t.get("revoked_at") for t in tokens):
            return True
        return store.verify(token)
    except Exception as exc:  # noqa: BLE001
        logger.error("mcp auth check failed — failing closed: %s", exc)
        return False


def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP SSE transport at /mcp with bearer-token auth."""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.routing import Mount, Route

        from aryx.mcp.server import server

        sse = SseServerTransport("/mcp/messages/")

        async def handle_sse(request):
            """Authenticate and bridge one MCP client connection over SSE."""
            if not _bearer_ok(request):
                raise HTTPException(401, "missing or invalid bearer token")
            async with sse.connect_sse(
                request.scope, request.receive, request._send,
            ) as streams:
                await server.run(streams[0], streams[1],
                                 server.create_initialization_options())

        app.router.routes.append(Route("/mcp", endpoint=handle_sse))
        app.router.routes.append(Mount("/mcp/messages/",
                                       app=sse.handle_post_message))
        logger.info("MCP mounted at /mcp")
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP mount failed: %s", exc)

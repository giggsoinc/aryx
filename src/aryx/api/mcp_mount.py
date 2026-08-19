"""MCP SSE transport mounting for the Aryx FastAPI app.

Split out of api/main.py to keep the app-assembly module under the file
length cap — bearer-auth and SSE mounting are a self-contained concern.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)


def _bearer_ok(request) -> bool:
    """Verify `Authorization: Bearer <token>` — fails CLOSED.

    Delegates to aryx.mcp.auth so this transport and the standalone SSE
    server (mcp/sse.py) enforce identical rules. The previous local
    implementation allowed a request through when no token was supplied
    and when no tokens had ever been issued; both are now rejections.
    """
    from aryx.mcp.auth import authorize_headers
    return authorize_headers(request.headers.get("authorization"))


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
                from aryx.mcp.auth import DENIED_HINT
                raise HTTPException(401, DENIED_HINT)
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

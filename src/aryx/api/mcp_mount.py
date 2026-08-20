"""MCP SSE transport mounting for the Aryx FastAPI app.

Split out of api/main.py to keep the app-assembly module under the file
length cap — bearer-auth and SSE mounting are a self-contained concern.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def mount_mcp(app: FastAPI) -> None:
    """Mount the MCP SSE transport at /mcp with bearer-token auth.

    Built as an independent Starlette sub-app carrying its OWN middleware,
    then mounted whole — not as two routes appended to the parent app's
    router. A route appended directly only gets whatever auth check its
    own handler happens to run; a sibling route registered alongside it
    (here, the Mount that carries every actual tool-call POST) gets none
    of that protection unless it is wrapped too. This previously left
    `/mcp/messages/` — the channel ingest/correction/chart tool calls
    travel on — completely unauthenticated while `/mcp` itself correctly
    401'd. Mounting a sub-app with `middleware=[Middleware(...)]` runs
    that middleware for every route inside it, including Mounts, which is
    what a per-route `if not authorize_headers(...)` check cannot do.

    Mirrors mcp/sse.py's standalone server, which got this right from the
    start — same BearerAuthMiddleware, so the two transports cannot drift.
    """
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.requests import Request
        from starlette.routing import Mount, Route

        from aryx.mcp.auth import BearerAuthMiddleware
        from aryx.mcp.server import server

        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            """Bridge one authenticated MCP client connection over SSE."""
            async with sse.connect_sse(
                request.scope, request.receive, request._send,
            ) as streams:
                await server.run(streams[0], streams[1],
                                 server.create_initialization_options())

        mcp_app = Starlette(
            routes=[
                # A bare `GET /mcp` (no trailing slash — how this was
                # reachable before this fix) 307-redirects to `/mcp/`
                # before matching this route, since Starlette's mount
                # matching wants "/" for the sub-app's root. Confirmed
                # live that the redirect target still enforces auth
                # (401 with no token, correct handshake with one) — an
                # extra same-origin hop, not a bypass. Tried registering
                # an empty-path route to avoid the hop; Starlette in this
                # version rejects it (raises rather than mounting), and
                # mount_mcp's try/except silently swallowed that,
                # dropping MCP auth AND routing entirely. Not worth that
                # risk for a cosmetic redirect.
                Route("/", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
            middleware=[Middleware(BearerAuthMiddleware)],
        )
        app.mount("/mcp", mcp_app)
        logger.info("MCP mounted at /mcp")
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP mount failed: %s", exc)

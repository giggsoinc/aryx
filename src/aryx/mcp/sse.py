"""MCP SSE server — HTTP transport for server-side deployment (Inc 11).

Run with: uvicorn aryx.mcp.sse:app --host 0.0.0.0 --port 8765
Claude Desktop config:
  { "mcpServers": { "aryx": {
      "url": "http://<host>:8765/sse",
      "headers": { "Authorization": "Bearer <token>" } } } }

This process binds every interface and exposes the FULL MCP tool surface,
which mutates: file ingest, graph corrections, chart persistence. It is
therefore bearer-authenticated on BOTH routes — the SSE stream and the
/messages/ POST channel that carries the actual tool calls. Authenticating
only /sse would be theatre: a caller who knows a session id can post tool
calls straight to /messages/.

Issue a token with POST /admin/mcp/tokens. Set ARYX_MCP_AUTH=off to
disable the check for local development only.
"""
from __future__ import annotations

import logging

import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.routing import Mount, Route

from aryx.config import get_settings
from aryx.logging_setup import configure_logging
from aryx.mcp.auth import BearerAuthMiddleware
from aryx.mcp.server import server

configure_logging(get_settings().log_level)
logger = logging.getLogger(__name__)

sse = SseServerTransport("/messages/")


async def handle_sse(request: Request) -> None:
    """Bridge one authenticated MCP client connection over SSE."""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
    middleware=[Middleware(BearerAuthMiddleware)],
)


def main() -> None:
    uvicorn.run("aryx.mcp.sse:app", host="0.0.0.0", port=8765, log_level="info")


if __name__ == "__main__":
    main()

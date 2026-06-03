"""Combined Aryx API: graph queries + admin/ingestion + MCP /mcp endpoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from aryx.api.admin_api import admin_router
from aryx.api.ask_api import ask_router
from aryx.api.connect_api import connect_router
from aryx.api.doc_discover_api import doc_discover_router
from aryx.api.file_ingest_api import file_ingest_router
from aryx.api.graph_api import graph_router
from aryx.api.jobs_api import jobs_router
from aryx.api.observability_api import observability_router
from aryx.api.ontology_api import ontology_router
from aryx.api.workspace_api import workspace_router

logger = logging.getLogger(__name__)


def _mount_mcp(app: FastAPI) -> None:
    """Mount the MCP SSE transport at /mcp so external agents can connect."""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.routing import Mount, Route

        from aryx.mcp.server import server

        sse = SseServerTransport("/mcp/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send,
            ) as streams:
                await server.run(
                    streams[0], streams[1],
                    server.create_initialization_options(),
                )

        app.router.routes.append(Route("/mcp", endpoint=handle_sse))
        app.router.routes.append(Mount("/mcp/messages/",
                                       app=sse.handle_post_message))
        logger.info("MCP mounted at /mcp")
    except Exception as exc:  # noqa: BLE001 — MCP optional
        logger.warning("MCP mount failed: %s", exc)


def create_app() -> FastAPI:
    """Build the Aryx FastAPI app with every router + MCP mounted."""
    app = FastAPI(title="Aryx API", version="1.0")
    app.include_router(graph_router())
    app.include_router(admin_router())
    app.include_router(ask_router())
    app.include_router(jobs_router())
    app.include_router(file_ingest_router())
    app.include_router(connect_router())
    app.include_router(doc_discover_router())
    app.include_router(workspace_router())
    app.include_router(observability_router())
    app.include_router(ontology_router())
    _mount_mcp(app)
    return app


app = create_app()

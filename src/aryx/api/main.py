"""Combined Aryx API: graph queries + admin/ingestion + MCP /mcp endpoint."""
from __future__ import annotations

import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from aryx.api.actions_api import actions_router
from aryx.api.adjudication_api import adjudication_router
from aryx.api.admin_api import admin_router
from aryx.api.ask_api import ask_router
from aryx.api.brief_api import brief_router
from aryx.api.axioms_api import axioms_router, shapes_router
from aryx.api.ask_history_api import ask_history_router
from aryx.api.connect_api import connect_router
from aryx.api.datasource_api import datasource_router
from aryx.api.demo_ingest_api import demo_ingest_router
from aryx.api.doc_discover_api import doc_discover_router
from aryx.api.file_ingest_api import file_ingest_router
from aryx.api.graph_api import graph_router
from aryx.api.ingest_question_api import ingest_question_router
from aryx.api.jobs_api import jobs_router
from aryx.api.mcp_tokens_api import mcp_tokens_router
from aryx.api.observability_api import observability_router
from aryx.api.ontology_api import ontology_router
from aryx.api.rest_ingest_api import rest_ingest_router
from aryx.api.rules_api import rules_router
from aryx.api.versions_api import versions_router
from aryx.api.workspace_api import workspace_router

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


def _mount_mcp(app: FastAPI) -> None:
    """Mount the MCP SSE transport at /mcp with bearer-token auth."""
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.routing import Mount, Route

        from aryx.mcp.server import server

        sse = SseServerTransport("/mcp/messages/")

        async def handle_sse(request):
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    from aryx.store.pool import close_all
    close_all()


def create_app() -> FastAPI:
    """Build the Aryx FastAPI app with every router + MCP mounted."""
    from aryx.api.security import ApiKeyMiddleware
    app = FastAPI(title="Aryx API", version="1.0", lifespan=_lifespan)
    app.add_middleware(ApiKeyMiddleware)
    app.include_router(graph_router())
    app.include_router(admin_router())
    app.include_router(ask_router())
    app.include_router(ask_history_router())
    app.include_router(jobs_router())
    app.include_router(file_ingest_router())
    app.include_router(connect_router())
    app.include_router(demo_ingest_router())
    app.include_router(doc_discover_router())
    app.include_router(workspace_router())
    app.include_router(brief_router())
    app.include_router(datasource_router())
    app.include_router(ingest_question_router())
    app.include_router(observability_router())
    app.include_router(ontology_router())
    app.include_router(axioms_router())
    app.include_router(shapes_router())
    app.include_router(rules_router())
    app.include_router(rest_ingest_router())
    app.include_router(versions_router())
    app.include_router(mcp_tokens_router())
    app.include_router(adjudication_router())
    app.include_router(actions_router())
    _mount_mcp(app)
    return app


app = create_app()

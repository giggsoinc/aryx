"""Combined Aryx API: graph queries + admin/ingestion."""
from __future__ import annotations

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


def create_app() -> FastAPI:
    """Build the Aryx FastAPI app with every router mounted."""
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
    return app


app = create_app()

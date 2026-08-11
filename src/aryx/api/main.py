"""Combined Aryx API: graph queries + admin/ingestion + MCP /mcp endpoint."""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aryx.api.mcp_mount import mount_mcp
from aryx.config import get_settings
from aryx.logging_setup import configure_logging
from aryx.api.actions_api import actions_router
from aryx.api.adjudication_api import adjudication_router
from aryx.api.admin_api import admin_router
from aryx.api.andie_planner_api import andie_planner_router
from aryx.api.ask_api import ask_router
from aryx.api.brief_api import brief_router
from aryx.api.axioms_api import axioms_router, shapes_router
from aryx.api.ask_history_api import ask_history_router
from aryx.api.connect_api import connect_router
from aryx.api.dashboard_model_api import dashboard_model_router
from aryx.api.data_api import data_router
from aryx.api.dataset_api import dataset_router
from aryx.api.datasource_api import datasource_router
from aryx.api.demo_ingest_api import demo_ingest_router
from aryx.api.doc_discover_api import doc_discover_router
from aryx.api.execution_plan_api import execution_plan_router
from aryx.api.execution_run_api import execution_run_router
from aryx.api.file_ingest_api import file_ingest_router
from aryx.api.render_telemetry_api import render_telemetry_router
from aryx.api.graph_api import graph_router
from aryx.api.graph_intake_api import graph_intake_router
from aryx.api.graph_profile_api import graph_profile_router
from aryx.api.planning_context_api import planning_context_router
from aryx.api.ingest_question_api import ingest_question_router
from aryx.api.intent_api import intent_router
from aryx.api.jobs_api import jobs_router
from aryx.api.lab_api import lab_router
from aryx.api.mcp_tokens_api import mcp_tokens_router
from aryx.api.observability_api import observability_router
from aryx.api.system_api import system_router
from aryx.api.ontology_api import ontology_router
from aryx.api.pipeline_derive_api import pipeline_derive_router
from aryx.api.pipeline_link_api import pipeline_link_router
from aryx.api.profile_api import profile_router
from aryx.api.semantic_api import semantic_router
from aryx.api.ontology_assist_api import ontology_assist_router
from aryx.api.relationship_type_api import relationship_type_router
from aryx.api.rest_ingest_api import rest_ingest_router
from aryx.api.rules_api import rules_router
from aryx.api.versions_api import versions_router
from aryx.api.workspace_api import workspace_router

configure_logging(get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Close the shared connection pool on shutdown; nothing needed on startup."""
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
    app.include_router(lab_router())
    app.include_router(data_router())
    app.include_router(ask_history_router())
    app.include_router(jobs_router())
    app.include_router(system_router())
    from aryx.api.corrections_api import corrections_router
    app.include_router(corrections_router())
    app.include_router(file_ingest_router())
    app.include_router(connect_router())
    app.include_router(demo_ingest_router())
    app.include_router(doc_discover_router())
    app.include_router(workspace_router())
    app.include_router(brief_router())
    app.include_router(datasource_router())
    app.include_router(ingest_question_router())
    app.include_router(intent_router())
    app.include_router(dataset_router())
    app.include_router(profile_router())
    app.include_router(semantic_router())
    app.include_router(graph_intake_router())
    app.include_router(graph_profile_router())
    app.include_router(planning_context_router())
    app.include_router(andie_planner_router())
    app.include_router(execution_plan_router())
    app.include_router(execution_run_router())
    app.include_router(dashboard_model_router())
    app.include_router(render_telemetry_router())
    app.include_router(relationship_type_router())
    app.include_router(pipeline_link_router())
    app.include_router(pipeline_derive_router())
    app.include_router(ontology_assist_router())
    app.include_router(ontology_router())
    app.include_router(axioms_router())
    app.include_router(shapes_router())
    app.include_router(rules_router())
    app.include_router(rest_ingest_router())
    app.include_router(versions_router())
    app.include_router(mcp_tokens_router())
    app.include_router(adjudication_router())
    app.include_router(actions_router())
    app.include_router(observability_router())
    mount_mcp(app)
    return app


app = create_app()

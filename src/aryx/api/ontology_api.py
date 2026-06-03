"""Ontology interchange API — RDF/OWL export + import for third-party tools.

Export reads the canonical Postgres source of truth (entities, relationships,
ontology types) and serialises on demand; nothing is mutated. Import parses an
uploaded RDF/OWL document into 'proposed' ontology types that still pass the
human review gate. The plugin must be enabled in Settings (export_runtime).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from aryx import export_runtime
from aryx.api.ontology_browse import approve as approve_browse, list_browse
from aryx.config import get_settings
from aryx.ontology.rdf import (
    GraphBundle,
    available_formats,
    format_for_extension,
    parse_ontology,
    serialize,
)
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore

logger = logging.getLogger(__name__)


class OntologyConfigRequest(BaseModel):
    """Settings payload for the interchange plugin (all fields optional)."""

    enabled: bool | None = None
    formats: list[str] | None = None
    base_uri: str | None = None
    include_provenance: bool | None = None


class OntologyImportRequest(BaseModel):
    """An uploaded ontology document to parse into proposed types."""

    content: str
    format: str = ""
    filename: str = ""
    workspace_id: int = 1


def _load_bundle(workspace_id: int, include_provenance: bool) -> GraphBundle:
    """Read a workspace's graph from Postgres into a GraphBundle."""
    settings = get_settings()
    store = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        provenance = store.list_members_provenance() if include_provenance else []
        bundle = GraphBundle(
            entities=store.list_entities(),
            relationships=store.list_relationships(),
            provenance=provenance,
        )
    finally:
        store.close()
    onto = OntologyStore(settings.rdb_dsn)
    try:
        bundle.types = onto.list_types()
    finally:
        onto.close()
    return bundle


def ontology_router() -> APIRouter:
    """Build the /ontology router (config, formats, export, import)."""
    router = APIRouter(prefix="/ontology")

    @router.get("/config")
    def get_config() -> dict:
        """Return the current interchange config + available formats."""
        return export_runtime.status()

    @router.post("/config")
    def set_config(req: OntologyConfigRequest) -> dict:
        """Update the interchange config (enable, formats, base URI)."""
        export_runtime.set_config(
            enabled=req.enabled, formats=req.formats,
            base_uri=req.base_uri, include_provenance=req.include_provenance,
        )
        return export_runtime.status()

    @router.get("/formats")
    def list_formats() -> list[dict[str, str]]:
        """List every supported format with its media type and extension."""
        return available_formats()

    @router.get("/types")
    def list_types(workspace_id: int = 1) -> dict:
        """Return ontology types + relationships in this workspace (Browse tab)."""
        return list_browse(workspace_id)

    @router.post("/types/{name}/approve")
    def approve_type(name: str) -> dict:
        """Approve a proposed type — flips status to 'approved'."""
        return approve_browse(name)

    @router.get("/export")
    def export_graph(workspace_id: int = 1, format: str = "turtle") -> Response:
        """Serialise a workspace graph to RDF/OWL as a downloadable file."""
        if not export_runtime.is_enabled():
            raise HTTPException(403, "ontology export is disabled — enable it in Settings")
        if format not in export_runtime.enabled_formats():
            raise HTTPException(403, f"format '{format}' is not enabled in Settings")
        cfg = export_runtime.status()
        try:
            bundle = _load_bundle(workspace_id, bool(cfg["include_provenance"]))
            payload, media_type, ext = serialize(
                bundle, format, str(cfg["base_uri"]), bool(cfg["include_provenance"]),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — surface store/serialise faults
            logger.warning("ontology export failed: %s", exc)
            raise HTTPException(500, f"export failed: {exc}") from exc
        filename = f"aryx_ws{workspace_id}.{ext}"
        return Response(
            content=payload, media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/import")
    def import_ontology(req: OntologyImportRequest) -> dict:
        """Parse an RDF/OWL document into proposed ontology types and seed them."""
        if not export_runtime.is_enabled():
            raise HTTPException(403, "ontology import is disabled — enable it in Settings")
        fmt = req.format or format_for_extension(req.filename) or "turtle"
        try:
            types = parse_ontology(req.content, fmt)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not types:
            return {"imported": 0, "types": [], "format": fmt,
                    "message": "no owl:Class / rdfs:Class declarations found"}
        onto = OntologyStore(get_settings().rdb_dsn)
        try:
            onto.seed_types(types)
        finally:
            onto.close()
        names = [t.name for t in types]
        logger.info("ontology imported count=%d format=%s", len(names), fmt)
        return {"imported": len(names), "types": names, "format": fmt,
                "message": "imported as 'proposed' — approve them in the ontology review gate"}

    return router

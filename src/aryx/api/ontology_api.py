"""Ontology interchange API — RDF/OWL export + import; ontology CRUD."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from aryx import export_runtime
from aryx.api import ontology_browse as _ob
from aryx.config import get_settings
from aryx.ontology.rdf import GraphBundle, available_formats, serialize
from aryx.store.axiom_store import AxiomStore
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
    onto = OntologyStore(settings.rdb_dsn, workspace_id)
    try: bundle.types = onto.list_types()
    finally: onto.close()
    axiom_store = AxiomStore(settings.rdb_dsn)
    try: bundle.axioms = axiom_store.list_(workspace_id)
    finally: axiom_store.close()
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
        """Return ontology types + relationships (Browse tab)."""
        return _ob.list_browse(workspace_id)

    @router.post("/types/{name}/approve")
    def approve_type(name: str, workspace_id: int = 1) -> dict:
        """Approve a proposed type."""
        return _ob.approve(name, workspace_id)

    @router.post("/types/{name}/parent")
    def set_parent(name: str, body: dict,
                    workspace_id: int = 1) -> dict:
        """Set or clear the parent_type for a type (rdfs:subClassOf).

        Body: ``{"parent_type": "Vehicle"}`` or ``{"parent_type": null}`` to clear.
        """
        parent = body.get("parent_type")
        return _ob.set_parent(name, str(parent) if parent else None,
                                workspace_id)

    @router.post("/types")
    def add_type(body: dict) -> dict:
        """Create a new ontology type manually in one workspace."""
        return _ob.add_type(str(body.get("name", "")).strip(),
                            body.get("attributes") or {},
                            str(body.get("status", "approved")),
                            workspace_id=int(body.get("workspace_id", 1)))

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
        """Parse RDF/OWL into proposed types via the ontology_browse helper."""
        if not export_runtime.is_enabled():
            raise HTTPException(403, "ontology import disabled — enable in Settings")
        try:
            return _ob.import_doc(req.content, req.format, req.filename,
                                  req.workspace_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router

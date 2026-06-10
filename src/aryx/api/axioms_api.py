"""Ontology axioms router — formal-ontology constraints over types.

Endpoints (prefix ``/ontology/axioms``):

  POST   /             — create an axiom (idempotent on payload hash)
  GET    /             — list axioms in a workspace
  DELETE /{axiom_id}   — remove an axiom from a workspace

Stays separate from ``ontology_api`` so each module respects the 150-line cap.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from aryx import export_runtime
from aryx.config import get_settings
from aryx.ontology.rdf.shapes import build_shapes_graph
from aryx.store.axiom_store import VALID_KINDS, AxiomStore

logger = logging.getLogger(__name__)


def axioms_router() -> APIRouter:
    """Build the ``/ontology/axioms`` router."""
    router = APIRouter(prefix="/ontology/axioms")

    @router.get("")
    def list_axioms(workspace_id: int = 1) -> dict[str, Any]:
        """Return every axiom declared in a workspace."""
        store = AxiomStore(get_settings().rdb_dsn)
        try:
            axioms = store.list_(workspace_id)
        finally:
            store.close()
        return {"workspace_id": workspace_id, "axioms": axioms,
                "valid_kinds": sorted(VALID_KINDS)}

    @router.post("")
    def add_axiom(body: dict[str, Any]) -> dict[str, Any]:
        """Create one axiom. Body: ``{subject_type, kind, payload, workspace_id?}``."""
        subject = str(body.get("subject_type", "")).strip()
        kind = str(body.get("kind", "")).strip()
        payload = body.get("payload") or {}
        workspace_id = int(body.get("workspace_id", 1))
        if not subject:
            raise HTTPException(400, "subject_type is required")
        if kind not in VALID_KINDS:
            raise HTTPException(
                400, f"unknown kind '{kind}'; choose from {sorted(VALID_KINDS)}")
        if not isinstance(payload, dict):
            raise HTTPException(400, "payload must be an object")
        store = AxiomStore(get_settings().rdb_dsn)
        try:
            axiom_id = store.add(workspace_id, subject, kind, payload)
        finally:
            store.close()
        return {"status": "ok", "id": axiom_id, "subject_type": subject,
                "kind": kind, "payload": payload,
                "deduped": axiom_id is None}

    @router.delete("/{axiom_id}")
    def delete_axiom(axiom_id: int, workspace_id: int = 1) -> dict[str, Any]:
        """Remove an axiom from a workspace (no-op when absent)."""
        store = AxiomStore(get_settings().rdb_dsn)
        try:
            store.delete(axiom_id, workspace_id)
        finally:
            store.close()
        return {"status": "ok", "id": axiom_id,
                "workspace_id": workspace_id}

    @router.post("/validate")
    def validate(workspace_id: int = 1) -> dict[str, Any]:
        """Run the axiom-validation pass; record + return a summary."""
        from aryx.reasoning.axiom_validator import validate_workspace
        return validate_workspace(workspace_id, get_settings().rdb_dsn)

    return router


def shapes_router() -> APIRouter:
    """Build the ``/ontology/shapes`` SHACL endpoint."""
    router = APIRouter(prefix="/ontology/shapes")

    @router.get("")
    def get_shapes(workspace_id: int = 1, format: str = "turtle") -> Response:
        """Serve a SHACL shapes graph derived from the workspace's axioms."""
        if not export_runtime.is_enabled():
            raise HTTPException(403, "ontology export is disabled "
                                "— enable it in Settings")
        store = AxiomStore(get_settings().rdb_dsn)
        try:
            axioms = store.list_(workspace_id)
        finally:
            store.close()
        cfg = export_runtime.status()
        graph = build_shapes_graph(axioms, str(cfg["base_uri"]))
        fmt_map = {"turtle": ("turtle", "text/turtle", "ttl"),
                   "n-triples": ("nt", "application/n-triples", "nt"),
                   "json-ld": ("json-ld", "application/ld+json", "jsonld")}
        if format not in fmt_map:
            raise HTTPException(400, f"unsupported format '{format}'")
        rdflib_fmt, media, ext = fmt_map[format]
        payload = graph.serialize(format=rdflib_fmt, encoding="utf-8")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        filename = f"aryx_ws{workspace_id}_shapes.{ext}"
        return Response(content=payload, media_type=media,
                        headers={"Content-Disposition":
                                 f'attachment; filename="{filename}"'})

    return router

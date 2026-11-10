"""FastAPI read API over the knowledge graph, served from Postgres (Increment 6)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from aryx.ports import GraphReaderPort, ports


def _reader(workspace_id: int = 1) -> GraphReaderPort:
    return ports().graph_reader(workspace_id)


def graph_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/entities")
    def find_entities(
        type: str | None = None, name: str | None = None, limit: int = 50,
        reader: GraphReaderPort = Depends(_reader),
    ) -> list[dict[str, Any]]:
        return reader.find_entities(ontology_type=type, name=name, limit=limit)

    @router.get("/graph")
    def full_graph(reader: GraphReaderPort = Depends(_reader)) -> dict[str, Any]:
        """All entities + all relationships in one call (for graph canvas)."""
        return {
            "entities": reader.find_entities(limit=500),
            "relationships": reader.all_relationships(),
        }

    @router.post("/graph/cypher", deprecated=True)
    def cypher_read(body: dict[str, Any]) -> dict[str, Any]:
        """Removed. The graph is served from Postgres, so there is no Cypher engine."""
        raise HTTPException(
            status_code=410,
            detail="POST /graph/cypher was removed: the graph is now served from "
                   "Postgres. Use /entities, /graph, /entities/{id}/neighbors, "
                   "/entities/{id}/provenance, /entities/{id}/path/{target_id} or /data/*.")

    @router.get("/entities/{entity_id}")
    def get_entity(
        entity_id: int, reader: GraphReaderPort = Depends(_reader)
    ) -> dict[str, Any]:
        entity = reader.get_entity(entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="entity not found")
        return entity

    @router.get("/entities/{entity_id}/neighbors")
    def neighbors(
        entity_id: int, reader: GraphReaderPort = Depends(_reader)
    ) -> list[dict[str, Any]]:
        return reader.neighbors(entity_id)

    @router.get("/entities/{entity_id}/provenance")
    def provenance(
        entity_id: int, reader: GraphReaderPort = Depends(_reader)
    ) -> list[dict[str, Any]]:
        return reader.provenance(entity_id)

    @router.get("/entities/{entity_id}/path/{target_id}")
    def path(
        entity_id: int, target_id: int, max_hops: int = 6,
        reader: GraphReaderPort = Depends(_reader),
    ) -> list[dict[str, Any]]:
        # Imported here, not at module level: importing aryx.graph pulls in the
        # connection pool, and this module is imported by unit tests that stub psycopg.
        from aryx.graph.pg_path import GraphSearchTooLarge
        try:
            return reader.shortest_path(entity_id, target_id, max_hops)
        except GraphSearchTooLarge as exc:
            # Not "no path": the search was cut off. Tell the caller to narrow it.
            raise HTTPException(
                422, f"search too large; lower max_hops ({exc})") from exc

    return router


def create_app() -> FastAPI:
    app = FastAPI(title="Aryx Graph API", version="1.0")
    app.include_router(graph_router())
    return app


app = create_app()

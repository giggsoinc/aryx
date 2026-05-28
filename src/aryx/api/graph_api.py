"""FastAPI read API over the FalkorDB knowledge graph (Increment 6).

A thin, read-only HTTP surface on top of GraphReader: look up resolved
entities, search them, walk one-hop relationships, and trace provenance back
to source records. The graph is a rebuildable projection, so this layer never
writes. Run with: uvicorn aryx.api.graph_api:app
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from aryx.config import get_settings
from aryx.graph import GraphReader


@lru_cache(maxsize=1)
def _reader() -> GraphReader:
    """Return a process-wide GraphReader bound to the configured graph URL."""
    return GraphReader(get_settings().graph_url)


def create_app() -> FastAPI:
    """Build the read-only knowledge-graph API."""
    app = FastAPI(title="Aryx Graph API", version="1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/entities")
    def find_entities(
        type: str | None = None,
        name: str | None = None,
        limit: int = 50,
        reader: GraphReader = Depends(_reader),
    ) -> list[dict[str, Any]]:
        """Search entities by optional ontology type and name substring."""
        return reader.find_entities(ontology_type=type, name=name, limit=limit)

    @app.get("/entities/{entity_id}")
    def get_entity(
        entity_id: int, reader: GraphReader = Depends(_reader)
    ) -> dict[str, Any]:
        """Look up one entity by id; 404 if it does not exist."""
        entity = reader.get_entity(entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="entity not found")
        return entity

    @app.get("/entities/{entity_id}/neighbors")
    def neighbors(
        entity_id: int, reader: GraphReader = Depends(_reader)
    ) -> list[dict[str, Any]]:
        """Return one-hop related entities in both directions."""
        return reader.neighbors(entity_id)

    @app.get("/entities/{entity_id}/provenance")
    def provenance(
        entity_id: int, reader: GraphReader = Depends(_reader)
    ) -> list[dict[str, Any]]:
        """Return the source records the entity was projected from."""
        return reader.provenance(entity_id)

    return app


app = create_app()

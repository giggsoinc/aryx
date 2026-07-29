"""Glue: derive the workspace graph, validate it, and persist a version (C05).

Shared by the ingest auto-trigger, backfill, and API. Builds the graph JSON from
the workspace's entities/relationships, hashes it (idempotent by content), then
validates, normalizes, and stores an immutable version.
"""
from __future__ import annotations

import hashlib
import json
import logging

from psycopg.errors import UniqueViolation

from aryx.graph_intake.build import build_graph_json
from aryx.graph_intake.models import GraphIntakeResult
from aryx.graph_intake.validate import validate_and_normalize
from aryx.store.dataset_store import DatasetStore
from aryx.store.entity_store import EntityStore
from aryx.store.graph_intake_store import GraphIntakeStore

logger = logging.getLogger(__name__)

_VERSION_RETRIES = 5  # concurrent auto-trigger version-collision retries


def _content_hash(graph_json: dict) -> str:
    canonical = json.dumps(graph_json, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_intake(dsn: str, workspace_id: int) -> GraphIntakeResult | None:
    """Auto-derive, validate, and version the workspace's Aryx graph.

    Idempotent: an unchanged graph (same content hash) returns the existing
    version instead of creating a new one. Returns None when the workspace has
    no entities yet.
    """
    estore = EntityStore(dsn, workspace_id)
    try:
        entities = estore.list_entities()
        relationships = estore.list_relationships()
    finally:
        estore.close()
    if not entities:
        return None

    graph_json = build_graph_json(entities, relationships)
    graph_id = f"graph_workspace_{workspace_id}"
    content_hash = _content_hash(graph_json)

    store = GraphIntakeStore(dsn, workspace_id)
    try:
        existing = store.find_by_hash(graph_id, content_hash)
        if existing is not None:
            return existing
        dstore = DatasetStore(dsn, workspace_id)
        try:
            dataset_ids = sorted({v.dataset_id for v in dstore.list_versions(500)})
        finally:
            dstore.close()
        # Concurrent uploads to the same workspace can both auto-trigger
        # run_intake() and compute the same "vN" tag from count_versions();
        # the UNIQUE(workspace, graph_id, version) constraint then rejects the
        # loser. Retry with a bumped tag, mirroring dataset/ingest.py's
        # register_dataset — if a same-hash version appeared meanwhile,
        # return it instead of dropping this graph version.
        for _ in range(_VERSION_RETRIES):
            version = f"v{store.count_versions(graph_id) + 1}"
            result, normalized = validate_and_normalize(graph_json, graph_id, version, dataset_ids)
            result.content_hash = content_hash
            try:
                store.save(result, graph_json, normalized)
            except UniqueViolation:
                dup = store.find_by_hash(graph_id, content_hash)
                if dup is not None:
                    return dup
                continue  # version tag was taken by a concurrent run; bump + retry
            break
        else:
            raise RuntimeError(f"could not assign a version for {graph_id} after "
                               f"{_VERSION_RETRIES} attempts")
    finally:
        store.close()
    logger.info("graph intake ws=%s graph=%s version=%s status=%s entities=%d rels=%d",
                workspace_id, graph_id, version, result.schema_status,
                result.entity_count, result.relationship_count)
    return result

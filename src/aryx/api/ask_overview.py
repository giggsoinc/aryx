"""Workspace overview used by the Ask flow.

A compact text block that ALWAYS rides along in the synthesis prompt so the
model can describe what's in the workspace even when a specific entity isn't
matched. Three blocks: kinds + counts + samples, declared relationship types,
and the workspace aim from the brief.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.config import get_settings
from aryx.graph import GraphReader
from aryx.store.relationship_type_store import RelationshipTypeStore
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)


def build(reader: GraphReader, workspace_id: int) -> str:
    """Return a multi-line overview string. Best-effort; never raises."""
    parts: list[str] = ["WORKSPACE OVERVIEW:"]
    parts.extend(_kinds(reader))
    parts.extend(_relationships(workspace_id))
    parts.extend(_aim(workspace_id))
    return "\n".join(parts)


def _kinds(reader: GraphReader) -> list[str]:
    """Group entities by ontology type; show count + 3 sample names per kind."""
    by_type: dict[str, list[str]] = {}
    try:
        for e in reader.find_entities(limit=500):
            by_type.setdefault(e.get("type", "?"), []).append(e.get("name", ""))
    except Exception as exc:  # noqa: BLE001
        logger.debug("overview kinds skipped: %s", exc)
        return []
    if not by_type:
        return []
    lines = ["Kinds tracked:"]
    for t in sorted(by_type):
        samples = [n for n in by_type[t] if n][:3]
        eg = f"  (e.g. {', '.join(samples)})" if samples else ""
        lines.append(f"  - {t}: {len(by_type[t])} records{eg}")
    return lines


def _relationships(workspace_id: int) -> list[str]:
    """List declared relationship types from the W2 endpoint store."""
    try:
        rels = RelationshipTypeStore(get_settings().rdb_dsn).list(workspace_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("overview rels skipped: %s", exc)
        return []
    if not rels:
        return []
    lines = ["Declared connections:"]
    for r in rels:
        lines.append(f"  - {r['source_type']} -[{r['name']}]-> "
                     f"{r['target_type']}")
    return lines


def _aim(workspace_id: int) -> list[str]:
    """Pull the aim line from the workspace brief, if set."""
    try:
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            for w in store.list_all():
                if int(w.get("id", 0)) == int(workspace_id):
                    brief: dict[str, Any] = w.get("brief") or {}
                    aim = str(brief.get("aim") or "").strip()
                    return [f"Aim: {aim}"] if aim else []
        finally:
            store.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("overview aim skipped: %s", exc)
    return []

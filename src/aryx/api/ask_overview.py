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
from aryx.graph.ask_facts import attribute_breakdown, format_breakdown, type_counts
from aryx.ports.protocols import GraphReaderPort
from aryx.store.relationship_type_store import RelationshipTypeStore
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)


def build(reader: GraphReaderPort, workspace_id: int) -> str:
    """Return a multi-line overview string. Best-effort; never raises."""
    parts: list[str] = ["WORKSPACE OVERVIEW (counts are exact totals from the database):"]
    parts.extend(_kinds(reader, workspace_id))
    parts.extend(_relationships(workspace_id))
    parts.extend(_aim(workspace_id))
    return "\n".join(parts)


def _kinds(reader: GraphReaderPort, workspace_id: int | None = None) -> list[str]:
    """One line per ontology type: exact count, 3 sample names, value breakdowns.

    Counts come from a real ``COUNT`` per type — not from the first 500
    entities — so totals stay right however large the workspace is. Low
    cardinality attributes (status, priority, ...) are added as indented
    ``key: value n`` lines so "how many are open?" can be read straight off.
    """
    try:
        counts, exact = type_counts(reader, workspace_id)
        if not counts:
            return []
        breakdown = attribute_breakdown(reader, workspace_id)
        lines = ["Kinds tracked:"]
        for t in sorted(counts):
            samples = [e.get("name", "") for e in
                       reader.find_entities(ontology_type=t, limit=3)]
            samples = [n for n in samples if n]
            eg = f"  (e.g. {', '.join(samples)})" if samples else ""
            qualifier = "" if exact else "at least "
            lines.append(f"  - {t}: {qualifier}{counts[t]} records{eg}")
            for text in format_breakdown(breakdown.get(t, {})):
                lines.append(f"      {text}")
        return lines
    except Exception as exc:  # noqa: BLE001
        logger.debug("overview kinds skipped: %s", exc)
        return []


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

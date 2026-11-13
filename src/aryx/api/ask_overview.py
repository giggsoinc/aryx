"""Workspace overview used by the Ask flow.

A compact text block that ALWAYS rides along in the synthesis prompt so the
model can describe what's in the workspace even when a specific entity isn't
matched. Three blocks: kinds + counts + samples, declared relationship types,
and the workspace aim from the brief.

It costs several aggregate queries and is the same for every question until the
data changes, so it is built once per request (``build_with_types`` also hands
back the type list, so nothing is counted twice) and cached per workspace for
``ARYX_ASK_OVERVIEW_TTL`` seconds (see ``graph.overview_cache``).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aryx.config import get_settings
from aryx.graph import overview_cache
from aryx.graph.ask_facts import (
    attribute_breakdown, format_breakdown, sample_names, type_counts,
)
from aryx.ports.protocols import GraphReaderPort
from aryx.raven_log_config import log as raven_log
from aryx.store.relationship_type_store import RelationshipTypeStore
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)

_SERVICE = "aryx-api"
_DEFAULT_TTL = 300
_EXACT_HEADER = "WORKSPACE OVERVIEW (counts are exact totals from the database):"
_APPROX_HEADER = ("WORKSPACE OVERVIEW (counts are approximate: only the first "
                  "500 records were counted):")


def _ttl() -> int:
    """Seconds to cache the overview (``ARYX_ASK_OVERVIEW_TTL``; 0 turns it off)."""
    try:
        return int(get_settings().ask_overview_ttl)
    except Exception as exc:  # noqa: BLE001 — a bad setting must not break Ask
        raven_log(
            "WARN", "could not read ARYX_ASK_OVERVIEW_TTL; using the default",
            criticality="P4", service=_SERVICE, error_code="ASK_OVERVIEW_TTL_DEFAULTED",
            context={"object_id": "config", "workspace_id": None,
                     "final_status": "degraded", "result": "fallback",
                     "reason_code": "ASK_OVERVIEW_TTL_DEFAULTED", "stage": "Ask",
                     "detail": str(exc)[:200]})
        return _DEFAULT_TTL


def build_with_types(reader: GraphReaderPort, workspace_id: int) -> tuple[str, list[str]]:
    """Return ``(overview_text, ontology_types)`` from one set of queries.

    Served from the per-workspace cache while it is fresh. The header says
    "exact" only when the counts really are exact. Best-effort; never raises.
    """
    started = time.monotonic()
    ttl = _ttl()
    cached = overview_cache.get(workspace_id, ttl)
    source = "cache"
    if cached is None:
        source = "built"
        lines, types, exact = _kinds_full(reader, workspace_id)
        parts: list[str] = [_EXACT_HEADER if exact else _APPROX_HEADER]
        parts.extend(lines)
        parts.extend(_relationships(workspace_id))
        parts.extend(_aim(workspace_id))
        cached = ("\n".join(parts), types)
        if lines:  # never cache a degraded, kinds-less overview
            overview_cache.put(workspace_id, cached, ttl)
    raven_log(
        "DEBUG", "ask overview served",
        criticality="P4", service=_SERVICE, error_code="ASK_OVERVIEW_SERVED",
        context={"object_id": "overview", "workspace_id": workspace_id,
                 "task_id": f"ask-overview-{workspace_id}",
                 "trace_id": f"ask-overview-{workspace_id}",
                 "dependency_name": "postgres", "operation": "ask_overview",
                 "attempt": 1, "error_class": "",
                 "duration_ms": int((time.monotonic() - started) * 1000),
                 "final_status": "served", "result": source,
                 "reason_code": "ASK_OVERVIEW_SERVED", "stage": "Ask",
                 "impact_scope": "ask_prompt"})
    return cached


def build(reader: GraphReaderPort, workspace_id: int) -> str:
    """Return a multi-line overview string. Best-effort; never raises."""
    return build_with_types(reader, workspace_id)[0]


def _kinds_full(reader: GraphReaderPort, workspace_id: int | None = None
                ) -> tuple[list[str], list[str], bool]:
    """Return ``(lines, types, exact)``: one line per ontology type.

    Counts come from a real ``COUNT`` per type — not from the first 500
    entities — so totals stay right however large the workspace is. Low
    cardinality attributes (status, priority, ...) are added as indented
    ``key: value n`` lines so "how many are open?" can be read straight off.
    """
    try:
        counts, exact = type_counts(reader, workspace_id)
        if not counts:
            return [], [], exact
        types = sorted(counts)
        breakdown = attribute_breakdown(reader, workspace_id, sum(counts.values()))
        samples = sample_names(reader, types, workspace_id)
        lines = ["Kinds tracked:"]
        for t in types:
            names = [n for n in samples.get(t, []) if n][:3]
            eg = f"  (e.g. {', '.join(names)})" if names else ""
            qualifier = "" if exact else "at least "
            lines.append(f"  - {t}: {qualifier}{counts[t]} records{eg}")
            for text in format_breakdown(breakdown.get(t, {})):
                lines.append(f"      {text}")
        return lines, types, exact
    except Exception as exc:  # noqa: BLE001
        raven_log(
            "WARN", "overview kinds unavailable; Ask answers without a workspace overview",
            criticality="P3", service=_SERVICE, error_code="ASK_OVERVIEW_UNAVAILABLE",
            context={"object_id": "overview", "workspace_id": workspace_id,
                     "final_status": "degraded", "result": "fallback",
                     "reason_code": "ASK_OVERVIEW_UNAVAILABLE", "stage": "Ask",
                     "detail": str(exc)[:200]})
        return [], [], True


def _kinds(reader: GraphReaderPort, workspace_id: int | None = None) -> list[str]:
    """The ``Kinds tracked`` lines only (kept for callers and tests)."""
    return _kinds_full(reader, workspace_id)[0]


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

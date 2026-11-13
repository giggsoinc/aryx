"""Exact facts for the Ask flow: real counts, record details, value breakdowns.

Ask used to describe a workspace from the first 500 entities and to show the
model only a record's name and links. That made "how many contracts?" wrong
past 500 entities and "what is ticket T-5's status?" unanswerable. This module
supplies the missing facts straight from the database and formats them as
compact text for the model.

Every fetcher fails soft: Ask must keep answering (with less detail) when a
swapped-in graph adapter lacks these methods or a query fails, and the
fallback is logged so it is visible instead of silent.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from aryx.raven_log_config import log as raven_log

logger = logging.getLogger(__name__)

_SERVICE = "aryx-api"
_SAMPLE_LIMIT = 500        # the old, capped sample — now only a fallback
MAX_ATTRIBUTES = 12        # attributes shown per record
MAX_VALUE_CHARS = 80       # longest attribute value shown
MAX_NEIGHBORS = 25         # linked records listed per entity
MAX_BREAKDOWN_KEYS = 6     # categorical attributes shown per type
MAX_BREAKDOWN_VALUES = 8   # distinct values counted per attribute


def _fallback_log(code: str, message: str, workspace_id: int | None,
                  reason: str) -> None:
    """Record that Ask fell back to less exact data (never raises)."""
    raven_log(
        "WARN", message,
        criticality="P3", service=_SERVICE, error_code=code,
        context={"object_id": "ask", "workspace_id": workspace_id,
                 "final_status": "degraded", "result": "fallback",
                 "reason_code": code, "stage": "Ask", "detail": reason[:200]})


def type_counts(reader: Any, workspace_id: int | None = None) -> tuple[dict[str, int], bool]:
    """Return ``({ontology_type: count}, exact)`` for the workspace.

    ``exact`` is True when the counts come from a real ``COUNT`` query. When
    the adapter has no ``count_by_type`` (or it fails) the counts come from the
    old 500-row sample and ``exact`` is False, so callers can say "at least".
    """
    fn = getattr(reader, "count_by_type", None)
    if fn is not None:
        try:
            return {str(k): int(v) for k, v in fn().items()}, True
        except Exception as exc:  # noqa: BLE001 — fall back, never break Ask
            logger.warning("count_by_type failed, sampling instead: %s", exc)
            _fallback_log("ASK_COUNTS_APPROXIMATE",
                          "type counts query failed; using a sampled count",
                          workspace_id, str(exc))
    else:
        _fallback_log("ASK_COUNTS_APPROXIMATE",
                      "graph adapter has no count_by_type; using a sampled count",
                      workspace_id, "missing count_by_type")
    sample = Counter(str(e.get("type", "?"))
                     for e in reader.find_entities(limit=_SAMPLE_LIMIT))
    return dict(sample), False


def attribute_breakdown(reader: Any, workspace_id: int | None = None
                        ) -> dict[str, dict[str, dict[str, int]]]:
    """Return ``{type: {attribute: {value: count}}}`` or ``{}`` if unavailable."""
    fn = getattr(reader, "attribute_breakdown", None)
    if fn is None:
        return {}
    try:
        return fn(MAX_BREAKDOWN_VALUES)
    except Exception as exc:  # noqa: BLE001 — breakdown is a nice-to-have
        logger.warning("attribute_breakdown failed: %s", exc)
        _fallback_log("ASK_BREAKDOWN_UNAVAILABLE",
                      "attribute breakdown query failed; overview has counts only",
                      workspace_id, str(exc))
        return {}


def entity_attributes(reader: Any, entities: list[Any],
                      workspace_id: int | None = None) -> dict[int, dict[str, Any]]:
    """Return ``{entity_id: attributes}`` for the retrieved entities, or ``{}``."""
    fn = getattr(reader, "entity_attributes", None)
    if fn is None or not entities:
        return {}
    try:
        return fn([e.id for e in entities])
    except Exception as exc:  # noqa: BLE001 — answer without details instead
        logger.warning("entity_attributes failed: %s", exc)
        _fallback_log("ASK_ATTRIBUTES_UNAVAILABLE",
                      "record attributes query failed; answering without them",
                      workspace_id, str(exc))
        return {}


def format_attributes(attrs: dict[str, Any], display_name: str = "") -> str:
    """Render ``key=value`` pairs for one record, or '' when there are none.

    Skips empty values, nested objects/lists, and any value that just repeats
    the record's display name; caps the count and the length of each value.
    """
    parts: list[str] = []
    for key, value in attrs.items():
        if value is None or value == "" or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if not text or text == display_name:
            continue
        if len(text) > MAX_VALUE_CHARS:
            text = text[:MAX_VALUE_CHARS - 1] + "…"
        parts.append(f"{key}={text}")
        if len(parts) >= MAX_ATTRIBUTES:
            break
    return ", ".join(parts)


def summarise_neighbors(neighbors: list[dict[str, Any]]) -> str:
    """Count linked records by relationship, direction and type.

    ``[10 x Contract(CONTRACT_CUSTOMERS in)]`` style, so a small model reads a
    ready-made total instead of counting a long list line by line.
    """
    counts: Counter[tuple[str, str, str]] = Counter(
        (str(n.get("relationship", "")), str(n.get("direction", "")),
         str(n.get("type", ""))) for n in neighbors)
    parts = []
    for (rel, direction, kind), n in sorted(counts.items(),
                                            key=lambda kv: (-kv[1], kv[0])):
        arrow = "->" if direction == "out" else "<-"
        parts.append(f"{n} x {kind} ({arrow} {rel})")
    return ", ".join(parts)


def format_breakdown(by_attribute: dict[str, dict[str, int]]) -> list[str]:
    """Render one type's categorical attributes as ``key: value n, value n`` lines."""
    lines = []
    for key in sorted(by_attribute)[:MAX_BREAKDOWN_KEYS]:
        values = sorted(by_attribute[key].items(), key=lambda kv: (-kv[1], kv[0]))
        lines.append(f"{key}: " + ", ".join(f"{v} {n}" for v, n in values))
    return lines

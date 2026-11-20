"""Edges from a document's own "from / predicate / to" table.

Some documents (a BRD appendix, a data dictionary) list their relationships as
a table: ``R-01 | satisfies | G-02``. Landing that table as entities would
create one junk record per row and no edges, and asking an LLM to rediscover
the same links is slow. Here the table is read as edges directly: each row
becomes one relationship between the two entities it names. No LLM.
"""
from __future__ import annotations

import csv
import io
import logging
import re

from aryx.models import Relationship
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)

_FROM = {"from", "source", "subject", "src", "parent", "start"}
_PRED = {"predicate", "relation", "relationship", "rel", "edge", "verb", "link"}
_TO = {"to", "target", "object", "dst", "child", "end"}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z]", "", header.lower())


def relation_columns(header: list[str]) -> tuple[int, int, int] | None:
    """(from, predicate, to) column indexes when the header is a relation table."""
    names = [_norm(h) for h in header]
    found = []
    for wanted in (_FROM, _PRED, _TO):
        hits = [i for i, n in enumerate(names) if n in wanted]
        if len(hits) != 1:
            return None
        found.append(hits[0])
    return found[0], found[1], found[2]


def relation_rows(csv_bytes: bytes) -> list[tuple[str, str, str]] | None:
    """Rows of a relation table as (from, predicate, to); None for any other CSV."""
    try:
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig", "ignore"))))
    except csv.Error:
        return None
    if len(rows) < 2:
        return None
    cols = relation_columns(rows[0])
    if cols is None:
        return None
    f, p, t = cols
    out = []
    for row in rows[1:]:
        if len(row) <= max(cols):
            continue
        a, b, c = row[f].strip(), row[p].strip(), row[t].strip()
        if a and b and c:
            out.append((a, b, c))
    return out


def edge_name(predicate: str) -> str:
    """'satisfies' / 'depends on' -> 'SATISFIES' / 'DEPENDS_ON'."""
    return re.sub(r"[^A-Z0-9]+", "_", predicate.upper()).strip("_") or "RELATED_TO"


def _index(entities: list[tuple[int, str, object]]) -> dict[str, list[tuple[int, int]]]:
    """value (lower-cased) -> [(entity id, attribute count)] over all short values."""
    index: dict[str, list[tuple[int, int]]] = {}
    for eid, _etype, payload in entities:
        if not isinstance(payload, dict):
            continue
        size = len(payload)
        for value in payload.values():
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                text = str(value).strip().lower()
                if text and len(text) <= 80:
                    index.setdefault(text, []).append((eid, size))
    return index


def _pick(index: dict[str, list[tuple[int, int]]], value: str) -> int | None:
    """The entity a value names. If several rows hold it (an id repeated in a
    catalogue table and in its own table), take the one with the most attributes."""
    hits = index.get(value.strip().lower())
    if not hits:
        return None
    return sorted(hits, key=lambda h: (-h[1], h[0]))[0][0]


def link_relation_rows(
    estore: EntityStore, rows: list[tuple[str, str, str]],
) -> tuple[int, int]:
    """Save one relationship per row whose two ends are both known entities.

    Returns (edges saved, rows skipped because an end matched no entity).
    """
    index = _index(estore.list_entities())
    rels: list[Relationship] = []
    seen: set[tuple[int, int, str]] = set()
    skipped = 0
    for a, predicate, b in rows:
        src, dst = _pick(index, a), _pick(index, b)
        if src is None or dst is None or src == dst:
            skipped += 1
            continue
        name = edge_name(predicate)
        if (src, dst, name) in seen:
            continue
        seen.add((src, dst, name))
        rels.append(Relationship(source_entity_id=src, target_entity_id=dst,
                                 name=name, confidence=1.0))
    if rels:
        estore.save_relationships(rels)
    logger.info("relation-table edges saved=%d skipped=%d of %d rows",
                len(rels), skipped, len(rows))
    return len(rels), skipped

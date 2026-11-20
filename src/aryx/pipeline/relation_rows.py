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


_ID_NAMES = {"id", "key", "code"}


def _is_identifier(key: str) -> bool:
    """A column that identifies a record: ``ID``, ``Emp ID``, ``Key``, ``Code``."""
    k = re.sub(r"[^a-z0-9]", "", key.lower())
    return k in _ID_NAMES or (k.endswith("id") and len(k) > 2)


def _index(entities: list[tuple[int, str, object]], exclude_ids: frozenset[int],
           ) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """(value -> entity ids by identifier column, value -> entity ids by name).

    Only entities created by THIS upload are indexed, and only their identifier
    columns (plus ``name`` as a fallback). Document ids such as R-01 repeat from one
    document to the next, and an ordinary attribute ("Active", "1") is not an id,
    so neither may resolve a link.
    """
    by_id: dict[str, set[int]] = {}
    by_name: dict[str, set[int]] = {}
    for eid, _etype, payload in entities:
        if eid in exclude_ids or not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                continue
            text = str(value).strip().lower()
            if not text or len(text) > 80:
                continue
            if _is_identifier(str(key)):
                by_id.setdefault(text, set()).add(eid)
            elif str(key).lower() == "name":
                by_name.setdefault(text, set()).add(eid)
    return by_id, by_name


def _pick(index: tuple[dict[str, set[int]], dict[str, set[int]]], value: str) -> int | None | str:
    """The one entity a value names, None when none does, "ambiguous" when several do."""
    by_id, by_name = index
    key = value.strip().lower()
    hits = by_id.get(key) or by_name.get(key)
    if not hits:
        return None
    return next(iter(hits)) if len(hits) == 1 else "ambiguous"


def link_relation_rows(
    estore: EntityStore, rows: list[tuple[str, str, str]],
    exclude_ids: frozenset[int] = frozenset(),
) -> tuple[int, int]:
    """Save one relationship per row whose two ends are each exactly one entity.

    ``exclude_ids`` are the entities that already existed before this upload (a
    second document in the same workspace must not link the first one's entities).
    A row is skipped when an end matches no entity or more than one. The edges are
    stored with confidence 1.0: the document states them outright.

    Returns (edges saved, rows skipped).
    """
    index = _index(estore.list_entities(), frozenset(exclude_ids))
    rels: list[Relationship] = []
    seen: set[tuple[int, int, str]] = set()
    skipped = ambiguous = 0
    for a, predicate, b in rows:
        src, dst = _pick(index, a), _pick(index, b)
        if "ambiguous" in (src, dst):
            ambiguous += 1
        if not isinstance(src, int) or not isinstance(dst, int) or src == dst:
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
    logger.info("relation-table edges saved=%d skipped=%d (ambiguous=%d) of %d rows",
                len(rels), skipped, ambiguous, len(rows))
    return len(rels), skipped

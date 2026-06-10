"""FalkorDB writer for the knowledge-graph projection (stage 5d).

The graph is a rebuildable projection of the RDB (the source of truth), so the
writer always wipes and rebuilds. Entity nodes carry their ontology type;
provenance edges link entities to source records; REL edges connect entities.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from falkordb import FalkorDB

logger = logging.getLogger(__name__)

_NAME_KEYS = ("name", "full_name", "title", "label", "ticket_ref", "ref",
              "sku", "code", "email", "username")

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_LABELS = 6  # cap to avoid label-bloat on deep hierarchies


def _safe_labels(labels: list[str] | None) -> list[str]:
    """Filter labels to safe Cypher identifiers and cap depth.

    FalkorDB does not support parameter-bound labels, so the label list is
    spliced into the query string — every entry must be a strict identifier
    or it gets dropped (with a warning) to prevent Cypher injection.
    """
    out: list[str] = []
    for raw in labels or []:
        if not raw:
            continue
        if not _LABEL_RE.match(raw):
            logger.warning("dropping invalid label %r (not a Cypher identifier)", raw)
            continue
        if raw in out:
            continue
        out.append(raw)
        if len(out) >= _MAX_LABELS:
            break
    return out


def _display_name(attributes: dict[str, Any]) -> str:
    """Pick a human label for a node, working across arbitrary entity types.

    Tries common identifying keys, then the first short string value, so a
    ticket shows its ref/issue and a product shows its name — not a blank node.
    """
    for key in _NAME_KEYS:
        value = attributes.get(key)
        if value:
            return str(value)
    for value in attributes.values():
        if isinstance(value, str) and 0 < len(value) <= 80:
            return value
    return ""


class FalkorStore:
    """Writes entity / provenance / relationship graph elements to FalkorDB."""

    def __init__(self, url: str, graph: str = "aryx") -> None:
        """Connect from a redis:// URL and select a named graph.

        Args:
            url: FalkorDB connection URL, e.g. redis://falkordb:6379.
            graph: Graph key to write into.
        """
        parsed = urlparse(url)
        self._db = FalkorDB(host=parsed.hostname or "localhost",
                            port=parsed.port or 6379)
        self._graph = self._db.select_graph(graph)

    def clear(self) -> None:
        """Delete the whole graph for a clean rebuild."""
        try:
            self._graph.delete()
        except Exception:  # graph may not exist yet  # noqa: BLE001
            pass

    def add_entity(self, entity_id: int, ontology_type: str,
                   attributes: dict[str, Any],
                   labels: list[str] | None = None,
                   iri: str | None = None) -> None:
        """Create or update an entity node with its ontology type and ancestor labels.

        Args:
            entity_id: Stable numeric id from EntityStore.
            ontology_type: Canonical type name (also stored as attribute).
            attributes: Golden-record attributes for display-name derivation.
            labels: Optional ancestor type names (rdfs:subClassOf chain) to
                attach as additional Cypher labels. ``ontology_type`` is added
                automatically if it passes label validation.
            iri: Optional stable IRI to write as ``e.iri`` for self-describing
                nodes — frozen for the entity's lifetime (derived from
                workspace_id + entity_id by the projector).
        """
        chain = [ontology_type] + list(labels or [])
        safe = _safe_labels(chain)
        label_clause = "".join(f":{lbl}" for lbl in safe)
        params: dict[str, Any] = {
            "id": entity_id, "type": ontology_type,
            "name": _display_name(attributes) or f"#{entity_id}",
        }
        set_iri = ""
        if iri:
            params["iri"] = iri
            set_iri = ", e.iri = $iri"
        self._graph.query(
            f"MERGE (e:Entity{label_clause} {{id: $id}}) "
            f"SET e.type = $type, e.name = $name{set_iri}",
            params,
        )

    def add_provenance(self, entity_id: int, system: str, dataset: str,
                       record_id: str) -> None:
        """Link an entity to the source record it was discovered in."""
        self._graph.query(
            "MERGE (s:Source {system: $sys, dataset: $ds, record_id: $rid}) "
            "WITH s MATCH (e:Entity {id: $id}) MERGE (e)-[:FROM]->(s)",
            {"sys": system, "ds": dataset, "rid": record_id, "id": entity_id},
        )

    def add_relationship(self, source_id: int, target_id: int, name: str) -> None:
        """Create a typed edge between two entities."""
        self._graph.query(
            "MATCH (a:Entity {id: $src}), (b:Entity {id: $tgt}) "
            "MERGE (a)-[:REL {name: $name}]->(b)",
            {"src": source_id, "tgt": target_id, "name": name},
        )

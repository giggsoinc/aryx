"""Post-resolution enrichment helpers: type ancestors + relate stage."""
from __future__ import annotations

import logging

from aryx.broker import Broker
from aryx.models import Relationship
from aryx.relationships import infer_relationship
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore

logger = logging.getLogger(__name__)


def _build_type_ancestors(dsn: str) -> dict[str, list[str]]:
    """Resolve ancestor chains for every declared type via OntologyStore."""
    ostore = OntologyStore(dsn)
    try:
        types = ostore.list_types()
        out: dict[str, list[str]] = {}
        for t in types:
            if t.parent_type:
                out[t.name] = ostore.ancestors(t.name)
        return out
    except Exception as exc:  # noqa: BLE001 — hierarchy is additive, never block projection
        logger.warning("type ancestors lookup failed; projecting without labels: %s", exc)
        return {}
    finally:
        ostore.close()


def _relate(store: EntityStore, broker: Broker, max_pairs: int) -> int:
    """Infer relationships over candidate entity pairs (frontier tier).

    A naive all-pairs candidate strategy capped at max_pairs; deterministic
    FK/co-occurrence pair selection is a later increment.
    """
    entities = store.list_entities()
    rels: list[Relationship] = []
    pairs = 0
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            if pairs >= max_pairs:
                break
            left, right = entities[i], entities[j]
            name, conf = infer_relationship(left[2], right[2], broker)
            if name:
                rels.append(Relationship(
                    source_entity_id=left[0], target_entity_id=right[0],
                    name=name, confidence=conf))
            pairs += 1
    store.save_relationships(rels)
    return len(rels)

"""Entity resolution orchestration: resolve a run's records into entities."""
from __future__ import annotations

import logging

from aryx.broker import Broker
from aryx.resolution import resolve
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def resolve_run(
    run_id: int,
    ontology_type: str,
    key_attrs: list[str],
    store: EntityStore,
    broker: Broker,
) -> int:
    """Resolve one run's landed records into canonical entities.

    Args:
        run_id: The discovery run to resolve.
        ontology_type: Canonical type the records resolve into.
        key_attrs: Payload keys whose values form the match text.
        store: Open entity store.
        broker: Model broker (embeddings local, adjudication frontier).

    Returns:
        Number of entities created.
    """
    records = store.landed_records(run_id, key_attrs)
    results = resolve(records, broker, ontology_type)
    created = store.save(results)
    logger.info("resolve_run complete run_id=%s entities=%d", run_id, created)
    return created

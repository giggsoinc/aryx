"""Entity resolution orchestration: resolve a run's records into entities."""
from __future__ import annotations

import logging

from aryx.broker import Broker
from aryx.models import EntityMember, ResolvedEntity
from aryx.resolution import resolve
from aryx.resolution.review_queue import StoreReviewSink
from aryx.store.adjudication_store import AdjudicationStore
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def resolve_run(
    run_id: int,
    ontology_type: str,
    key_attrs: list[str],
    store: EntityStore,
    broker: Broker,
    dsn: str,
    workspace_id: int,
) -> int:
    """Resolve one run's landed records into canonical entities.

    Args:
        run_id: The discovery run to resolve.
        ontology_type: Canonical type the records resolve into.
        key_attrs: Payload keys whose values form the match text.
        store: Open entity store.
        broker: Model broker (embeddings local, adjudication frontier).
        dsn: Database DSN for the adjudication queue store.
        workspace_id: Workspace scope for the adjudication queue store.

    Returns:
        Number of entities created.
    """
    records = store.landed_records(run_id, key_attrs)
    review = StoreReviewSink(AdjudicationStore(dsn, workspace_id), run_id)
    results = resolve(records, broker, ontology_type, review=review)
    created = store.save(results)
    logger.info("resolve_run complete run_id=%s entities=%d", run_id, created)
    return created


def materialize_one_per_record(
    run_id: int,
    ontology_type: str,
    key_attrs: list[str],
    store: EntityStore,
) -> int:
    """One entity per landed record — no blocking, scoring, or adjudication.

    For transactional/fact types (a genuine per-row id like order_id, ticket_id):
    every row IS a distinct real-world thing, so treating any pair as a fuzzy
    "maybe duplicate" candidate is wrong by construction, not just noisy —
    two orders sharing a company and status are still two different orders.
    See field_shape.is_row_identifier for the (narrow) trigger condition.

    Confidence is 0.5 (DEC-006's singleton floor), not 1.0 — skipping the
    resolution funnel means no evidence was ever gathered for this row, and
    DEC-006 reserves 1.0 for a claim of certainty this bypass never makes.
    """
    records = store.landed_records(run_id, key_attrs)
    results = [
        (ResolvedEntity(ontology_type=ontology_type, attributes=dict(r.payload),
                        confidence=0.5,
                        provenance={k: r.record_id for k in r.payload}),
         [EntityMember(landed_record_id=r.record_id)])
        for r in records
    ]
    created = store.save(results)
    logger.info("materialize_one_per_record complete run_id=%s entities=%d",
                run_id, created)
    return created

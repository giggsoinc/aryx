"""Human adjudication queue for ambiguous ER pairs (G10).

Every pair entering the review band is persisted — including LLM-decided ones
(status ``auto_llm``) — so the table accumulates labeled (pair, score, verdict)
training data from day one.

``apply_decision`` is the seed of incremental ER: a human approval unions the
two entities post-hoc (merge members, re-merge golden record); a rejection
leaves them separate and records the label.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from aryx.models import ResolutionRecord

logger = logging.getLogger(__name__)


class ReviewSink(Protocol):
    """Anything that can accept a band pair for review (store or test fake)."""

    def offer(self, left: ResolutionRecord, right: ResolutionRecord,
              score: float, llm_verdict: bool | None,
              llm_reason: str | None, status: str) -> None:
        """Queue one scored pair with its (optional) LLM verdict."""
        ...


class StoreReviewSink:
    """ReviewSink that persists pairs via an AdjudicationStore."""

    def __init__(self, store: Any, run_id: int) -> None:
        """Bind the sink to a store and the run being resolved."""
        self._store = store
        self._run_id = run_id

    def offer(self, left: ResolutionRecord, right: ResolutionRecord,
              score: float, llm_verdict: bool | None,
              llm_reason: str | None, status: str) -> None:
        """Persist one band pair (labeled-data row + optional human work item)."""
        self._store.enqueue(self._run_id, left.record_id, right.record_id,
                            score, llm_verdict, llm_reason, status)


def apply_decision(store: Any, adjudication_id: int, approve: bool,
                   decided_by: str) -> dict[str, Any]:
    """Apply a human verdict to a queued pair.

    Approval merges the two records' entities: the surviving entity absorbs
    the other's members and golden records re-merge (first-non-empty across
    the two attribute dicts; policy-aware re-survivorship runs on the next
    full re-resolution). Rejection just records the label.

    Args:
        store: AdjudicationStore (also exposes the entity-merge helpers).
        adjudication_id: Queue row id.
        approve: True merges, False keeps entities separate.
        decided_by: Reviewer identity for the audit trail.

    Returns:
        The updated queue row.
    """
    row = store.decide(adjudication_id, approve, decided_by)
    if approve:
        merged = store.merge_entities_of(row["left_record_id"],
                                         row["right_record_id"])
        logger.info("adjudication %s approved by %s -> merged=%s",
                    adjudication_id, decided_by, merged)
    else:
        logger.info("adjudication %s rejected by %s", adjudication_id, decided_by)
    return row

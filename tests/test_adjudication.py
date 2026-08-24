"""G10: band routing, queue offers, apply_decision merge/reject."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from aryx.models import ResolutionRecord
from aryx.resolution.cluster import UnionFind
from aryx.resolution.review_queue import apply_decision
from aryx.resolution.run import _route_pair, resolve


class FakeSink:
    """Collects offered pairs for assertions."""

    def __init__(self) -> None:
        self.offers: list[dict] = []

    def offer(self, left, right, score, llm_verdict, llm_reason,
              status) -> None:
        self.offers.append({"left": left.record_id, "right": right.record_id,
                            "score": score, "llm_verdict": llm_verdict,
                            "status": status})


def _pair() -> tuple[ResolutionRecord, ResolutionRecord, UnionFind]:
    left = ResolutionRecord(record_id=1, text="a", payload={})
    right = ResolutionRecord(record_id=2, text="b", payload={})
    union = UnionFind()
    union.add(1)
    union.add(2)
    return left, right, union


def _merged(union: UnionFind) -> bool:
    return union.find(1) == union.find(2)


def test_above_auto_merge_merges_without_queue() -> None:
    """score >= 0.95 -> merge, nothing queued."""
    left, right, union = _pair()
    sink = FakeSink()
    _route_pair(left, right, 0.97, MagicMock(), union, sink)
    assert _merged(union) and sink.offers == []


def test_score_exactly_at_auto_merge_boundary_merges() -> None:
    """score == 0.95 (inclusive lower bound) -> auto-merge, no LLM call."""
    left, right, union = _pair()
    sink = FakeSink()
    _route_pair(left, right, 0.95, MagicMock(), union, sink)
    assert _merged(union) and sink.offers == []


def test_score_exactly_at_review_boundary_enters_adjudicate_band() -> None:
    """score == 0.80 (inclusive lower bound) -> LLM adjudicate, not direct queue."""
    left, right, union = _pair()
    sink = FakeSink()
    with patch("aryx.resolution.run.adjudicate", return_value=0.97):
        _route_pair(left, right, 0.80, MagicMock(), union, sink)
    assert _merged(union)
    assert sink.offers[0]["status"] == "auto_llm"


def test_band_llm_rescore_above_auto_merge_merges() -> None:
    """[0.80, 0.95) with LLM rescore >= 0.95 -> merge + auto_llm labeled row."""
    left, right, union = _pair()
    sink = FakeSink()
    with patch("aryx.resolution.run.adjudicate", return_value=0.97):
        _route_pair(left, right, 0.90, MagicMock(), union, sink)
    assert _merged(union)
    assert sink.offers[0]["status"] == "auto_llm"
    assert sink.offers[0]["llm_verdict"] == 0.97


def test_band_llm_rescore_below_auto_merge_queues_pending() -> None:
    """[0.80, 0.95) with LLM rescore < 0.95 -> queue for human, no merge."""
    left, right, union = _pair()
    sink = FakeSink()
    with patch("aryx.resolution.run.adjudicate", return_value=0.85):
        _route_pair(left, right, 0.90, MagicMock(), union, sink)
    assert not _merged(union)
    assert sink.offers[0]["status"] == "pending"
    assert sink.offers[0]["llm_verdict"] == 0.85


def test_band_llm_confident_reject_auto_rejects_no_human_queue() -> None:
    """DEC-010: LLM rescore < AUTO_REJECT (0.05) -> auto_reject, not pending.

    Regression: microsoft.com vs amazon.com-style pairs where the LLM
    itself says "not a match" (rescore ~0.00) used to land in the human
    queue exactly like a genuine 0.90 close call — no floor distinguished
    "ambiguous" from "confidently wrong".
    """
    left, right, union = _pair()
    sink = FakeSink()
    with patch("aryx.resolution.run.adjudicate", return_value=0.0):
        _route_pair(left, right, 0.90, MagicMock(), union, sink)
    assert not _merged(union)
    assert sink.offers[0]["status"] == "auto_reject"
    assert sink.offers[0]["llm_verdict"] == 0.0


def test_band_llm_failure_queues_pending_no_merge() -> None:
    """LLM down -> fail-to-human: pending row, conservative non-merge."""
    left, right, union = _pair()
    sink = FakeSink()
    with patch("aryx.resolution.run.adjudicate",
               side_effect=RuntimeError("llm down")):
        _route_pair(left, right, 0.90, MagicMock(), union, sink)
    assert not _merged(union)
    assert sink.offers[0]["status"] == "pending"


def test_below_review_queues_pending_directly() -> None:
    """score < 0.80 -> straight to human queue, no LLM call, no merge."""
    left, right, union = _pair()
    sink = FakeSink()
    _route_pair(left, right, 0.60, MagicMock(), union, sink)
    assert not _merged(union)
    assert sink.offers[0]["status"] == "pending"
    assert sink.offers[0]["llm_verdict"] is None


def test_no_sink_band_pair_skipped_quietly() -> None:
    """review=None (queue not wired) keeps the funnel working."""
    left, right, union = _pair()
    _route_pair(left, right, 0.60, MagicMock(), union, None)
    assert not _merged(union)


def test_llm_approved_merge_keeps_confidence_signal() -> None:
    """Regression: an LLM-approved merge must not report the 0.5 floor.

    _materialize's adjudicate_threshold used to be `auto` (0.95, the band's
    UPPER bound). cluster_edges filters the raw pre-rescore score by
    `score >= threshold`, so a pair merged via a successful LLM rescore
    (raw score below 0.95) was filtered out of its own cluster's edge list,
    flooring cluster_confidence to 0.5 -- indistinguishable from an
    unconfirmed singleton. Fixed by passing `rev` (0.80, the band's lower
    bound) instead, restoring the invariant that any pair which caused a
    union has its raw score counted as an edge.
    """
    left = ResolutionRecord(record_id=1, text="Acme Robotics LLC",
                            payload={"name": "Acme Robotics LLC"})
    right = ResolutionRecord(record_id=2, text="Acme Robtcs LLC",
                             payload={"name": "Acme Robtcs LLC"})
    with patch("aryx.resolution.run.adjudicate", return_value=0.97), \
         patch.dict("os.environ", {"ARYX_ER_MAX_ADJUDICATIONS": "5"}):
        results = resolve([left, right], MagicMock(), "Company")
    assert len(results) == 1
    entity, members = results[0]
    assert len(members) == 2
    assert entity.confidence > 0.5, (
        f"expected the raw in-band score to count as an edge, got floored "
        f"confidence={entity.confidence}"
    )


def test_apply_decision_approve_merges_entities() -> None:
    """Human approval unions the two records' entities."""
    store = MagicMock()
    store.decide.return_value = {"id": 7, "left_record_id": 1,
                                 "right_record_id": 2}
    store.pending_duplicates_of.return_value = []
    row = apply_decision(store, 7, approve=True, decided_by="ravi")
    store.decide.assert_called_once_with(7, True, "ravi")
    store.merge_entities_of.assert_called_once_with(1, 2, None)
    assert row["id"] == 7


def test_apply_decision_reject_leaves_separate() -> None:
    """Rejection records the label; entities stay separate."""
    store = MagicMock()
    store.decide.return_value = {"id": 8, "left_record_id": 1,
                                 "right_record_id": 2}
    store.pending_duplicates_of.return_value = []
    apply_decision(store, 8, approve=False, decided_by="ravi")
    store.merge_entities_of.assert_not_called()


def test_resolve_excludes_auto_rejected_pair_from_cluster_confidence() -> None:
    """End-to-end regression (raven-review finding): A-C auto-merges by
    score alone, B-C is LLM-approved, A-B is LLM auto-rejected (never
    unioned) — but A/B/C still land in ONE cluster via the A-C/B-C chain.
    A-B's raw score (0.82, the LOWEST of the three) must not be an eligible
    merge-edge just because it was never excluded: without the fix,
    confidence wrongly floors to 0.82; with the fix, it's 0.85 (the
    genuine weakest APPROVED edge)."""
    a = ResolutionRecord(record_id=1, text="A", payload={"name": "A"})
    b = ResolutionRecord(record_id=2, text="B", payload={"name": "B"})
    c = ResolutionRecord(record_id=3, text="C", payload={"name": "C"})

    def fake_score_pair(left_text, right_text, *_args, **_kwargs):
        return {"AC": 0.96, "BC": 0.85, "AB": 0.82}["".join(sorted((left_text, right_text)))]

    def fake_adjudicate(left, right, _broker):
        pair = frozenset((left.record_id, right.record_id))
        return 0.97 if pair == {2, 3} else 0.02  # B-C approved, A-B rejected

    with patch("aryx.resolution.run.block", return_value={"blk": [a, b, c]}), \
         patch("aryx.resolution.run.score_pair", side_effect=fake_score_pair), \
         patch("aryx.resolution.run.adjudicate", side_effect=fake_adjudicate):
        results = resolve([a, b, c], MagicMock(), "Thing")

    assert len(results) == 1, "A/B/C must land in one cluster via the A-C/B-C chain"
    entity, members = results[0]
    assert {m.landed_record_id for m in members} == {1, 2, 3}
    assert entity.confidence == 0.85, (
        "A-B's rejected 0.82 must be excluded — the real floor is B-C's 0.85")


def test_apply_decision_closes_duplicate_pending_rows() -> None:
    """A pair that already collapsed to the same entities as another
    pending row must get that row auto-resolved too, not left dangling."""
    store = MagicMock()
    store.decide.return_value = {"id": 7, "left_record_id": 1,
                                 "right_record_id": 2}
    store.pending_duplicates_of.return_value = [9, 10]
    row = apply_decision(store, 7, approve=True, decided_by="ravi")
    store.pending_duplicates_of.assert_called_once_with(7, 1, 2)
    assert store.decide.call_args_list[1:] == [
        call(9, True, "ravi (duplicate of #7)"),
        call(10, True, "ravi (duplicate of #7)"),
    ]
    assert row["duplicates_closed"] == [9, 10]

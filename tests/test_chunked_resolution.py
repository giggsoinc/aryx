"""G1+G5: chunked-path equivalence with resolve(), and kill-and-resume."""
from __future__ import annotations

from collections import defaultdict

import pytest
from unittest.mock import MagicMock

from aryx.models import ResolutionRecord
from aryx.resolution.chunked import resolve_chunked
from aryx.resolution.run import resolve


class InMemoryBackend:
    """Dict-backed ChunkBackend — exact protocol, no Postgres."""

    def __init__(self, records: list[ResolutionRecord]) -> None:
        self._records = {r.record_id: r for r in records}
        self.members: dict[str, list[int]] = defaultdict(list)
        self.done: set[str] = set()
        self.match_edges: list[tuple[int, int, float]] = []
        self.blocks_scored = 0

    def has_keys(self, run_id: int) -> bool:
        return bool(self.members)

    def add_members(self, run_id: int, rows) -> None:
        for key, rid in rows:
            self.members[key].append(rid)

    def todo_blocks(self, run_id: int):
        for key in sorted(self.members):
            if key not in self.done:
                yield key

    def block_record_ids(self, run_id: int, key: str) -> list[int]:
        return self.members[key]

    def load_records(self, ids) -> list[ResolutionRecord]:
        return [self._records[i] for i in ids]

    def add_edges(self, run_id: int, edges) -> None:
        self.match_edges.extend(edges)

    def mark_done(self, run_id: int, key: str) -> None:
        self.done.add(key)
        self.blocks_scored += 1

    def edges(self, run_id: int):
        return list(self.match_edges)


def _fixture(n_clusters: int = 20, size: int = 5) -> list[ResolutionRecord]:
    names = [f"unique{c:02d} fixture entity" for c in range(n_clusters)]
    records, rid = [], 0
    for name in names:
        for _ in range(size):
            records.append(ResolutionRecord(record_id=rid, text=name,
                                            payload={"name": name}))
            rid += 1
    return records


def _cluster_sets(results) -> set[frozenset]:
    return {frozenset(m.landed_record_id for m in members)
            for _, members in results}


def test_equivalence_with_in_memory_resolve() -> None:
    """Chunked and legacy paths produce identical cluster sets."""
    records = _fixture()
    broker = MagicMock()
    broker.embed.side_effect = RuntimeError("no embeddings")
    legacy = _cluster_sets(resolve(records, broker, "Thing"))
    backend = InMemoryBackend(records)
    chunked = _cluster_sets(list(resolve_chunked(
        1, records, [r.record_id for r in records], backend, "Thing")))
    assert chunked == legacy


def test_kill_and_resume_identical_clusters() -> None:
    """Abort after N blocks, resume, final clusters match uninterrupted."""
    records = _fixture()
    uninterrupted = InMemoryBackend(records)
    expected = _cluster_sets(list(resolve_chunked(
        1, records, [r.record_id for r in records], uninterrupted, "Thing")))

    crashing = InMemoryBackend(records)
    original = crashing.mark_done
    calls = {"n": 0}

    def dying_mark_done(run_id: int, key: str) -> None:
        calls["n"] += 1
        if calls["n"] == 10:
            raise RuntimeError("simulated crash")
        original(run_id, key)

    crashing.mark_done = dying_mark_done
    with pytest.raises(RuntimeError):
        list(resolve_chunked(1, records, [r.record_id for r in records],
                             crashing, "Thing"))
    crashing.mark_done = original  # process restarts
    resumed = _cluster_sets(list(resolve_chunked(
        1, records, [r.record_id for r in records], crashing, "Thing")))
    assert resumed == expected


def test_resume_skips_key_pass() -> None:
    """Second invocation never re-keys (has_keys guard)."""
    records = _fixture(5)
    backend = InMemoryBackend(records)
    list(resolve_chunked(1, records, [r.record_id for r in records],
                         backend, "Thing"))
    member_count = sum(len(v) for v in backend.members.values())
    list(resolve_chunked(1, records, [r.record_id for r in records],
                         backend, "Thing"))
    assert sum(len(v) for v in backend.members.values()) == member_count


def test_oversized_block_skipped_with_done_marker() -> None:
    """Blocks over MAX_BLOCK are skipped but still marked done."""
    records = _fixture(1, size=3)
    backend = InMemoryBackend(records)
    backend.add_members(1, [("prefix:huge", r.record_id)
                            for r in records] * 2000)
    list(resolve_chunked(1, records, [r.record_id for r in records],
                         backend, "Thing"))
    assert "prefix:huge" in backend.done


class _CapturingReview:
    """ReviewSink stand-in that records every offer() call."""

    def __init__(self) -> None:
        self.offers: list[dict] = []

    def offer(self, left, right, score, llm_verdict, llm_reason, status) -> None:
        self.offers.append({
            "pair": frozenset((left.record_id, right.record_id)),
            "score": score, "llm_verdict": llm_verdict,
            "llm_reason": llm_reason, "status": status,
        })


def _paired_backend(records: list[ResolutionRecord]) -> InMemoryBackend:
    """A backend with both records pre-seeded into one block — bypasses
    real blocking-key derivation so band tests control the pair directly."""
    backend = InMemoryBackend(records)
    backend.add_members(1, [("block", r.record_id) for r in records])
    return backend


def test_score_pass_without_broker_drops_band_pairs_unchanged(monkeypatch) -> None:
    """Backward compatibility: omitting broker/review keeps the pre-fix
    behaviour — a pair that doesn't clear AUTO_MERGE is simply dropped,
    no edge, no review offer."""
    from aryx.resolution import chunked as chunked_mod

    monkeypatch.setattr(chunked_mod, "score_pair", lambda a, b: 0.85)
    records = [ResolutionRecord(record_id=1, text="a", payload={}),
               ResolutionRecord(record_id=2, text="b", payload={})]
    backend = _paired_backend(records)

    list(resolve_chunked(1, records, [1, 2], backend, "Thing"))

    assert backend.match_edges == []


def test_resolve_chunked_auto_rejects_confident_llm_non_match(monkeypatch) -> None:
    """Regression: the chunked resolver had NO DEC-009/DEC-010 band routing
    at all — every non-auto-merge pair was silently dropped, not even
    queued for human review. With broker+review supplied, a band pair whose
    LLM rescore is confidently below AUTO_REJECT now reaches review as
    auto_reject, exactly like the in-memory resolver."""
    from aryx.resolution import chunked as chunked_mod

    monkeypatch.setattr(chunked_mod, "score_pair", lambda a, b: 0.85)
    monkeypatch.setattr("aryx.resolution.run.adjudicate", lambda l, r, b: 0.02)
    records = [ResolutionRecord(record_id=1, text="a", payload={}),
               ResolutionRecord(record_id=2, text="b", payload={})]
    backend = _paired_backend(records)
    review = _CapturingReview()

    list(resolve_chunked(1, records, [1, 2], backend, "Thing",
                         broker=MagicMock(), review=review))

    assert backend.match_edges == []
    assert len(review.offers) == 1
    assert review.offers[0]["status"] == "auto_reject"
    assert review.offers[0]["llm_verdict"] == 0.02


def test_resolve_chunked_merges_via_llm_rescore(monkeypatch) -> None:
    """A band pair whose LLM rescore clears AUTO_MERGE becomes an edge, same
    as the in-memory resolver's auto_llm outcome — and is NOT also queued."""
    from aryx.resolution import chunked as chunked_mod

    monkeypatch.setattr(chunked_mod, "score_pair", lambda a, b: 0.85)
    monkeypatch.setattr("aryx.resolution.run.adjudicate", lambda l, r, b: 0.97)
    records = [ResolutionRecord(record_id=1, text="a", payload={}),
               ResolutionRecord(record_id=2, text="b", payload={})]
    backend = _paired_backend(records)
    review = _CapturingReview()

    list(resolve_chunked(1, records, [1, 2], backend, "Thing",
                         broker=MagicMock(), review=review))

    assert backend.match_edges == [(1, 2, 0.97)]
    assert review.offers == []

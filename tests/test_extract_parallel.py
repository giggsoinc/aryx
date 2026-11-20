"""Text extraction reads chunks in parallel, retries a failed chunk, and reports progress."""
from __future__ import annotations

import threading
import time

import pytest

from aryx.models import DocumentChunk, SourceRef
from aryx.ontology import extract


def _chunks(n: int) -> list[DocumentChunk]:
    src = SourceRef(system="document", dataset="d", record_id="doc")
    return [DocumentChunk(doc_id="d" * 64, chunk_index=i, text=f"Ada works at Acme {i}",
                          source=src) for i in range(n)]


def _mention(i: int) -> dict:
    return {"mentions": [{"type": "Person", "name": "Ada", "span": "Ada works at Acme"}]}


def test_chunks_are_read_in_parallel_but_returned_in_order(monkeypatch):
    monkeypatch.setattr(extract, "_WORKERS", 3)
    seen_threads: set[int] = set()

    def fake(_broker, _tier, _system, user, _schema):
        seen_threads.add(threading.get_ident())
        time.sleep(0.15)                      # a slow model
        return _mention(0)

    monkeypatch.setattr(extract, "complete_json", fake)
    began = time.monotonic()
    records = extract.extract_mentions(_chunks(6), broker=None)
    took = time.monotonic() - began
    assert len(records) == 6 and len(seen_threads) > 1
    assert took < 0.6, f"6 chunks x 0.15s should overlap, took {took:.2f}s"
    assert [r.payload["chunk_index"] for r in records] == [0, 1, 2, 3, 4, 5]
    assert [r.source.record_id.split(":")[1] for r in records] == ["0", "1", "2", "3", "4", "5"]


def test_a_timed_out_chunk_is_retried_and_its_entities_are_kept(monkeypatch):
    monkeypatch.setattr(extract, "_WORKERS", 1)
    monkeypatch.setattr(extract, "_ATTEMPTS", 2)
    monkeypatch.setattr(extract.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky(*_a):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("The read operation timed out")
        return _mention(0)

    monkeypatch.setattr(extract, "complete_json", flaky)
    records = extract.extract_mentions(_chunks(1), broker=None)
    assert calls["n"] == 2 and len(records) == 1          # not lost


def test_a_chunk_that_always_fails_is_skipped_without_stopping_the_rest(monkeypatch):
    monkeypatch.setattr(extract, "_WORKERS", 1)
    monkeypatch.setattr(extract, "_ATTEMPTS", 2)
    monkeypatch.setattr(extract.time, "sleep", lambda _s: None)

    def fake(_b, _t, _s, user, _schema):
        if '"chunk_index": 1' in user:
            raise TimeoutError("down")
        return _mention(0)

    monkeypatch.setattr(extract, "complete_json", fake)
    records = extract.extract_mentions(_chunks(3), broker=None)
    assert [r.payload["chunk_index"] for r in records] == [0, 2]


def test_progress_is_reported_after_every_chunk(monkeypatch):
    monkeypatch.setattr(extract, "_WORKERS", 2)
    monkeypatch.setattr(extract, "complete_json", lambda *_a: _mention(0))
    events: list[tuple[int, int, int]] = []
    extract.extract_mentions(_chunks(4), broker=None,
                             on_progress=lambda d, t, f: events.append((d, t, f)))
    assert [e[0] for e in events] == [1, 2, 3, 4]
    assert all(e[1] == 4 for e in events) and events[-1][2] == 4


def test_the_verbatim_span_gate_still_drops_invented_names(monkeypatch):
    monkeypatch.setattr(extract, "complete_json", lambda *_a: {"mentions": [
        {"type": "Person", "name": "Grace", "span": "Ada works at Acme"}]})
    assert extract.extract_mentions(_chunks(1), broker=None) == []
